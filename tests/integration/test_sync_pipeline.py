from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from src.chunking import ChunkingConfig
from src.converter import save_articles
from src.delta import JsonStateStore, build_updated_state, classify_delta
from src.models import NormalizedArticle
from src.scraper import ZendeskScraper
from src.utils import compute_content_hash
from src.vector_store import GeminiVectorStoreClient


class _StatefulMockGeminiTransport(httpx.BaseTransport):
    """In-memory mock Gemini File Search Store server for TC-I02."""

    def __init__(self) -> None:
        self.stores: dict[str, dict] = {}
        self.temp_files: dict[str, bytes] = {}
        self.documents: dict[str, dict] = {}
        self.upload_count = 0
        self.delete_count = 0
        self._seq = 0

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/v1beta/fileSearchStores":
            return httpx.Response(200, json={"fileSearchStores": list(self.stores.values())})

        if request.method == "POST" and path == "/v1beta/fileSearchStores":
            self._seq += 1
            body = json.loads(request.content)
            name = f"fileSearchStores/mock-{self._seq}"
            self.stores[name] = {"name": name, "displayName": body["displayName"]}
            return httpx.Response(200, json=self.stores[name])

        if request.method == "GET" and path.endswith("/documents"):
            store_prefix = path.replace("/v1beta/", "").rsplit("/documents", 1)[0]
            docs = [d for d in self.documents.values() if d["name"].startswith(store_prefix)]
            return httpx.Response(200, json={"documents": docs})

        if request.method == "DELETE" and "/documents/" in path:
            doc_name = path.replace("/v1beta/", "")
            self.documents.pop(doc_name, None)
            self.delete_count += 1
            return httpx.Response(200, json={})

        if request.method == "POST" and path == "/upload/v1beta/files":
            self._seq += 1
            return httpx.Response(
                200,
                headers={
                    "x-goog-upload-url": f"https://generativelanguage.googleapis.com/upload-session/{self._seq}"
                },
            )

        if request.method == "POST" and path.startswith("/upload-session/"):
            self._seq += 1
            file_name = f"files/tmp-{self._seq}"
            self.temp_files[file_name] = request.content
            return httpx.Response(200, json={"file": {"name": file_name}})

        if request.method == "POST" and path.endswith(":importFile"):
            self._seq += 1
            store_name = path.replace("/v1beta/", "").split(":importFile", 1)[0]
            body = json.loads(request.content)
            doc_name = f"{store_name}/documents/doc-{self._seq}"
            self.documents[doc_name] = {
                "name": doc_name,
                "customMetadata": body["customMetadata"],
            }
            self.upload_count += 1
            return httpx.Response(
                200,
                json={
                    "name": f"{store_name}/operations/op-{self._seq}",
                    "done": True,
                    "response": {"documentName": doc_name},
                },
            )

        if request.method == "DELETE" and path.startswith("/v1beta/files/"):
            self.temp_files.pop(path.replace("/v1beta/", ""), None)
            return httpx.Response(200, json={})

        return httpx.Response(404)


def test_tc_i02_full_delta_sync_lifecycle(tmp_path: Path) -> None:
    base_url = "https://support.example.com"
    zendesk_articles = [
        {
            "id": 1,
            "title": "Doc One",
            "html_url": f"{base_url}/hc/en-us/articles/1-doc-one",
            "updated_at": "2026-01-01T00:00:00Z",
            "body": "<p>Original body 1</p>",
            "draft": False,
        },
        {
            "id": 2,
            "title": "Doc Two",
            "html_url": f"{base_url}/hc/en-us/articles/2-doc-two",
            "updated_at": "2026-01-01T00:00:00Z",
            "body": "<p>Original body 2</p>",
            "draft": False,
        },
        {
            "id": 3,
            "title": "Doc Three",
            "html_url": f"{base_url}/hc/en-us/articles/3-doc-three",
            "updated_at": "2026-01-01T00:00:00Z",
            "body": "<p>Original body 3</p>",
            "draft": False,
        },
    ]

    def zendesk_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"articles": zendesk_articles, "next_page": None})

    gemini_transport = _StatefulMockGeminiTransport()
    scraper = ZendeskScraper(base_url=base_url, transport=httpx.MockTransport(zendesk_handler))
    client = GeminiVectorStoreClient(
        api_key="dummy-key",
        store_name="test-kb",
        chunking_config=ChunkingConfig(max_tokens=128, overlap_tokens=16),
        transport=gemini_transport,
        sleep_fn=lambda _: None,
    )
    state_store = JsonStateStore(tmp_path / "state.json")
    articles_dir = tmp_path / "articles"

    # Run 1: Cold start (3 added)
    norm1 = save_articles(scraper.fetch_articles(min_articles=1), articles_dir)
    prev1 = state_store.load()
    delta1 = classify_delta(norm1, prev1)
    assert (len(delta1.added), len(delta1.updated), len(delta1.skipped)) == (3, 0, 0)
    up1 = client.sync_delta(delta1, existing_doc_map={k: v.remote_doc_name for k, v in prev1.items() if v.remote_doc_name})
    state_store.save(build_updated_state(prev1, delta1, up1))
    assert up1.files_uploaded == 3
    assert up1.chunks_embedded >= 3

    # Run 2: No changes (3 skipped, 0 uploads)
    norm2 = save_articles(scraper.fetch_articles(min_articles=1), articles_dir)
    prev2 = state_store.load()
    delta2 = classify_delta(norm2, prev2)
    assert (len(delta2.added), len(delta2.updated), len(delta2.skipped)) == (0, 0, 3)
    up2 = client.sync_delta(delta2)
    assert up2.files_uploaded == 0
    assert gemini_transport.upload_count == 3

    # Run 3: 1 edited + 1 added -> 1 added, 1 updated, 2 skipped
    zendesk_articles[1]["body"] = "<p>Updated body 2</p>"
    zendesk_articles[1]["updated_at"] = "2026-01-05T00:00:00Z"
    zendesk_articles.append(
        {
            "id": 4,
            "title": "Doc Four",
            "html_url": f"{base_url}/hc/en-us/articles/4-doc-four",
            "updated_at": "2026-01-05T00:00:00Z",
            "body": "<p>New body 4</p>",
            "draft": False,
        }
    )
    norm3 = save_articles(scraper.fetch_articles(min_articles=1), articles_dir)
    prev3 = state_store.load()
    delta3 = classify_delta(norm3, prev3)
    assert (len(delta3.added), len(delta3.updated), len(delta3.skipped)) == (1, 1, 2)
    up3 = client.sync_delta(delta3, existing_doc_map={k: v.remote_doc_name for k, v in prev3.items() if v.remote_doc_name})
    state_store.save(build_updated_state(prev3, delta3, up3))
    assert up3.files_uploaded == 2
    assert gemini_transport.delete_count == 1
    assert gemini_transport.upload_count == 5

    # Run 4: Stateless container simulation (reconstruct from remote metadata)
    remote_state = client.list_remote_state()
    delta4 = classify_delta(norm3, remote_state)
    assert (len(delta4.added), len(delta4.updated), len(delta4.skipped)) == (0, 0, 4)


@pytest.mark.live
def test_tc_i04_live_gemini_file_search_upload_and_query(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dotenv_map = dotenv_values(repo_root / ".env") if (repo_root / ".env").exists() else {}
    api_key = (
        os.environ.get("API_KEY")
        or os.environ.get("GEMINI_API_KEY")
        or dotenv_map.get("API_KEY")
        or dotenv_map.get("GEMINI_API_KEY")
        or ""
    ).strip()

    if not api_key:
        pytest.skip("Set API_KEY or GEMINI_API_KEY in environment or .env to run live Gemini test")

    store_name = f"kb-sync-live-test-{uuid.uuid4().hex[:8]}"
    client = GeminiVectorStoreClient(
        api_key=api_key,
        store_name=store_name,
        model="gemini-2.5-flash",
    )

    md_youtube = (
        "# How to add a YouTube video\n\n"
        "Article URL: https://support.example.com/hc/en-us/articles/1001-youtube\n\n"
        "1. Open Files/Assets in your dashboard.\n"
        "2. Click Apps and select YouTube.\n"
        "3. Paste the YouTube video URL and click Save.\n"
    )
    article = NormalizedArticle(
        id=1001,
        title="How to add a YouTube video",
        slug="how-to-add-a-youtube-video",
        html_url="https://support.example.com/hc/en-us/articles/1001-youtube",
        updated_at="2026-01-15T10:00:00Z",
        markdown=md_youtube,
        content_hash=compute_content_hash(md_youtube),
        file_path=tmp_path / "how-to-add-a-youtube-video.md",
    )

    try:
        upload_res = client.sync_delta(DeltaClassification(added=[article]))
        assert upload_res.files_uploaded == 1
        assert upload_res.failed_ids == []

        answer = client.query("How do I add a YouTube video?")
        assert "YouTube" in answer or "youtube" in answer.lower()
        assert "Article URL:" in answer
    finally:
        client.delete_store(force=True)
