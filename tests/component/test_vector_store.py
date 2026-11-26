from __future__ import annotations

import io
import json

import httpx
import pytest

from src.chunking import ChunkingConfig
from src.interfaces import VectorStoreClient
from src.logging_config import configure_logging
from src.models import DeltaClassification, NormalizedArticle, validate_assistant_response
from src.utils import compute_content_hash
from src.vector_store import GeminiVectorStoreClient


def _make_norm(idx: int, body: str = "Some content here") -> NormalizedArticle:
    md_text = f"# Title {idx}\n\nArticle URL: https://support.example.com/hc/en-us/articles/{idx}\n\n{body}\n"
    return NormalizedArticle(
        id=idx,
        title=f"Title {idx}",
        slug=f"title-{idx}",
        html_url=f"https://support.example.com/hc/en-us/articles/{idx}",
        updated_at="2026-01-15T10:00:00Z",
        markdown=md_text,
        content_hash=compute_content_hash(md_text),
    )


def test_tc_c10_ensure_store_creates_and_reuses() -> None:
    calls: list[tuple[str, str]] = []
    stores: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, str(request.url)))
        assert request.headers.get("x-goog-api-key") == "secret-key"
        assert "secret-key" not in str(request.url)

        if request.method == "GET" and request.url.path == "/v1beta/fileSearchStores":
            return httpx.Response(200, json={"fileSearchStores": stores})
        if request.method == "POST" and request.url.path == "/v1beta/fileSearchStores":
            payload = json.loads(request.content)
            created = {"name": "fileSearchStores/store-1", "displayName": payload["displayName"]}
            stores.append(created)
            return httpx.Response(200, json=created)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client1 = GeminiVectorStoreClient(
        api_key="secret-key",
        store_name="support-kb",
        transport=transport,
        sleep_fn=lambda _: None,
    )
    assert isinstance(client1, VectorStoreClient)
    assert client1.ensure_store() == "fileSearchStores/store-1"
    # Second call uses cache
    assert client1.ensure_store() == "fileSearchStores/store-1"
    assert len(calls) == 2

    # Fresh client finds existing store without creating a duplicate
    client2 = GeminiVectorStoreClient(
        api_key="secret-key",
        store_name="support-kb",
        transport=transport,
        sleep_fn=lambda _: None,
    )
    assert client2.ensure_store() == "fileSearchStores/store-1"
    assert len([c for c in calls if c[0] == "POST"]) == 1


def test_tc_c10_sync_delta_empty_makes_zero_calls() -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={})

    client = GeminiVectorStoreClient(
        api_key="k",
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    res = client.sync_delta(DeltaClassification())
    assert res.files_uploaded == 0
    assert res.chunks_embedded == 0
    assert calls == []


def test_tc_c10_sync_delta_upload_replace_poll_and_error_isolation() -> None:
    deleted_docs: list[str] = []
    deleted_temp_files: list[str] = []
    poll_counts: dict[str, int] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/v1beta/fileSearchStores":
            return httpx.Response(
                200,
                json={"fileSearchStores": [{"name": "fileSearchStores/s1", "displayName": "support-kb"}]},
            )
        if request.method == "DELETE" and "/documents/" in path:
            assert request.url.params.get("force") == "true"
            deleted_docs.append(path.replace("/v1beta/", ""))
            return httpx.Response(200, json={})
        if request.method == "POST" and path == "/upload/v1beta/files":
            meta = json.loads(request.content)
            display = meta["file"]["displayName"]
            return httpx.Response(
                200,
                headers={"x-goog-upload-url": f"https://generativelanguage.googleapis.com/upload-session/{display}"},
            )
        if request.method == "POST" and path.startswith("/upload-session/"):
            slug = path.rsplit("/", 1)[-1].replace(".md", "")
            return httpx.Response(200, json={"file": {"name": f"files/{slug}"}})
        if request.method == "POST" and path == "/v1beta/fileSearchStores/s1:importFile":
            body = json.loads(request.content)
            file_name = body["fileName"]
            if file_name == "files/title-3":
                return httpx.Response(500, text="simulated import failure")
            op_name = f"fileSearchStores/s1/operations/op-{file_name.split('/')[-1]}"
            poll_counts[op_name] = 0
            return httpx.Response(200, json={"name": op_name, "done": False})
        if request.method == "GET" and "/operations/" in path:
            op_name = path.replace("/v1beta/", "")
            poll_counts[op_name] += 1
            if poll_counts[op_name] < 2:
                return httpx.Response(200, json={"name": op_name, "done": False})
            slug = op_name.rsplit("op-", 1)[-1]
            return httpx.Response(
                200,
                json={"name": op_name, "done": True, "response": {"documentName": f"fileSearchStores/s1/documents/{slug}"}},
            )
        if request.method == "DELETE" and path.startswith("/v1beta/files/"):
            deleted_temp_files.append(path.replace("/v1beta/", ""))
            return httpx.Response(200, json={})
        return httpx.Response(404)

    stream = io.StringIO()
    logger = configure_logging(level="INFO", secrets=["secret-key"])
    logger.handlers[0].stream = stream

    client = GeminiVectorStoreClient(
        api_key="secret-key",
        chunking_config=ChunkingConfig(max_tokens=100, overlap_tokens=10),
        poll_interval_seconds=0.0,
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )

    a1 = _make_norm(1, body="Updated doc")
    a2 = _make_norm(2, body="New doc")
    a3 = _make_norm(3, body="Failing doc")

    delta = DeltaClassification(added=[a2, a3], updated=[a1])
    res = client.sync_delta(delta, existing_doc_map={1: "fileSearchStores/s1/documents/old-1"})

    assert deleted_docs == ["fileSearchStores/s1/documents/old-1"]
    assert res.files_uploaded == 2
    assert res.chunks_embedded == 2
    assert res.failed_ids == [3]
    assert res.remote_doc_map == {
        1: "fileSearchStores/s1/documents/title-1",
        2: "fileSearchStores/s1/documents/title-2",
    }
    # Temp files cleaned up even for failed import
    assert set(deleted_temp_files) == {"files/title-1", "files/title-2", "files/title-3"}
    assert "files_embedded=2 chunks_embedded=2 failed=1" in stream.getvalue()


def test_tc_c10_list_remote_state_and_query() -> None:
    captured_query: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "GET" and path == "/v1beta/fileSearchStores":
            return httpx.Response(
                200,
                json={"fileSearchStores": [{"name": "fileSearchStores/s1", "displayName": "support-kb"}]},
            )
        if request.method == "GET" and path == "/v1beta/fileSearchStores/s1/documents":
            return httpx.Response(
                200,
                json={
                    "documents": [
                        {
                            "name": "fileSearchStores/s1/documents/d1",
                            "customMetadata": [
                                {"key": "article_id", "stringValue": "10"},
                                {"key": "slug", "stringValue": "youtube-guide"},
                                {"key": "content_hash", "stringValue": "hash10"},
                                {"key": "updated_at", "stringValue": "2026-01-01T00:00:00Z"},
                                {"key": "html_url", "stringValue": "https://support.example.com/10"},
                            ],
                        }
                    ]
                },
            )
        if request.method == "POST" and path.endswith(":generateContent"):
            captured_query.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": (
                                            "- Open Assets\n"
                                            "- Select Video\n\n"
                                            "Article URL: https://support.example.com/10"
                                        )
                                    }
                                ]
                            }
                        }
                    ]
                },
            )
        return httpx.Response(404)

    client = GeminiVectorStoreClient(
        api_key="k",
        system_prompt="Custom System Prompt",
        transport=httpx.MockTransport(handler),
        sleep_fn=lambda _: None,
    )
    remote_state = client.list_remote_state()
    assert 10 in remote_state
    assert remote_state[10].content_hash == "hash10"
    assert remote_state[10].remote_doc_name == "fileSearchStores/s1/documents/d1"

    answer = client.query("How do I add a video?")
    assert "Article URL: https://support.example.com/10" in answer
    assert captured_query["systemInstruction"]["parts"][0]["text"] == "Custom System Prompt"
    assert captured_query["tools"] == [
        {"fileSearch": {"fileSearchStoreNames": ["fileSearchStores/s1"]}}
    ]


def test_tc_c12_validate_assistant_response() -> None:
    good = (
        "- Step 1\n"
        "- Step 2\n\n"
        "Article URL: https://support.example.com/hc/en-us/articles/1"
    )
    assert validate_assistant_response(good) == []

    too_many_bullets_no_link = "\n".join(f"- Bullet {i}" for i in range(6))
    violations = validate_assistant_response(too_many_bullets_no_link)
    assert len(violations) == 2

    too_many_citations = (
        "- Step 1\n"
        "Article URL: https://support.example.com/1\n"
        "Article URL: https://support.example.com/2\n"
        "Article URL: https://support.example.com/3\n"
        "Article URL: https://support.example.com/4\n"
    )
    assert any("max 3" in v for v in validate_assistant_response(too_many_citations))
