from __future__ import annotations

import json
from pathlib import Path
from typing import Mapping, Optional

from src.converter import HtmlToMarkdownConverter
from src.delta import JsonStateStore
from src.models import Article, DeltaClassification, SyncStateEntry, UploadResult
from src.pipeline import SyncPipeline


class _FakeSource:
    def __init__(self, articles: list[Article]) -> None:
        self.articles = articles

    def fetch_articles(
        self,
        min_articles: int = 30,
        max_articles: Optional[int] = None,
    ) -> list[Article]:
        return self.articles[:max_articles] if max_articles else list(self.articles)


class _FakeVectorStore:
    def __init__(
        self,
        remote_state: Optional[dict[int, SyncStateEntry]] = None,
        fail_ids: Optional[set[int]] = None,
    ) -> None:
        self.remote_state = remote_state or {}
        self.fail_ids = fail_ids or set()
        self.sync_calls: list[DeltaClassification] = []

    def ensure_store(self) -> str:
        return "fileSearchStores/fake"

    def list_remote_state(self) -> dict[int, SyncStateEntry]:
        return dict(self.remote_state)

    def sync_delta(
        self,
        delta: DeltaClassification,
        existing_doc_map: Optional[dict[int, str]] = None,
    ) -> UploadResult:
        self.sync_calls.append(delta)
        uploaded = 0
        chunks = 0
        failed: list[int] = []
        doc_map: dict[int, str] = {}
        for item in [*delta.updated, *delta.added]:
            if item.id in self.fail_ids:
                failed.append(item.id)
            else:
                uploaded += 1
                chunks += 2
                doc_map[item.id] = f"fileSearchStores/fake/documents/{item.slug}"
        return UploadResult(
            files_uploaded=uploaded,
            chunks_embedded=chunks,
            failed_ids=failed,
            remote_doc_map=doc_map,
        )

    def query(self, question: str) -> str:
        return "Article URL: https://support.example.com/1"


def _sample_article(idx: int, body: str = "<p>Body</p>") -> Article:
    return Article(
        id=idx,
        title=f"Article {idx}",
        slug=f"article-{idx}",
        html_url=f"https://support.example.com/hc/en-us/articles/{idx}",
        updated_at="2026-01-15T10:00:00Z",
        body_html=body,
    )


def test_pipeline_cold_start_repeat_and_summary_artifact(tmp_path: Path) -> None:
    articles = [_sample_article(1), _sample_article(2)]
    source = _FakeSource(articles)
    state_store = JsonStateStore(tmp_path / "state.json")
    vector_store = _FakeVectorStore()
    summary_file = tmp_path / "last_run.json"

    pipeline = SyncPipeline(
        source=source,
        converter=HtmlToMarkdownConverter(),
        state_store=state_store,
        vector_store=vector_store,
        articles_dir=tmp_path / "articles",
        min_articles=1,
        summary_file=summary_file,
    )

    s1 = pipeline.run()
    assert (s1.added, s1.updated, s1.skipped, s1.failed) == (2, 0, 0, 0)
    assert (s1.files_embedded, s1.chunks_embedded) == (2, 4)
    assert summary_file.exists()
    artifact = json.loads(summary_file.read_text(encoding="utf-8"))
    assert artifact["added"] == 2
    assert "timestamp_utc" in artifact

    # Repeat run skips unchanged articles
    s2 = pipeline.run()
    assert (s2.added, s2.updated, s2.skipped, s2.files_embedded) == (0, 0, 2, 0)


def test_pipeline_hydrates_from_remote_state_when_local_missing(tmp_path: Path) -> None:
    article = _sample_article(1)
    converter = HtmlToMarkdownConverter()
    md_text = converter.convert(article)
    from src.utils import compute_content_hash

    remote_entry = SyncStateEntry(
        article_id=1,
        slug="article-1",
        content_hash=compute_content_hash(md_text),
        updated_at=article.updated_at,
        html_url=article.html_url,
        remote_doc_name="fileSearchStores/fake/documents/article-1",
    )
    vector_store = _FakeVectorStore(remote_state={1: remote_entry})
    pipeline = SyncPipeline(
        source=_FakeSource([article]),
        converter=converter,
        state_store=JsonStateStore(tmp_path / "missing_state.json"),
        vector_store=vector_store,
        articles_dir=tmp_path / "articles",
        min_articles=1,
    )

    summary = pipeline.run()
    assert (summary.added, summary.updated, summary.skipped) == (0, 0, 1)
    assert summary.files_embedded == 0


def test_pipeline_dry_run_and_partial_failure(tmp_path: Path) -> None:
    articles = [_sample_article(1), _sample_article(2)]
    state_file = tmp_path / "state.json"
    summary_file = tmp_path / "last_run.json"
    vector_store = _FakeVectorStore(fail_ids={2})

    pipeline = SyncPipeline(
        source=_FakeSource(articles),
        converter=HtmlToMarkdownConverter(),
        state_store=JsonStateStore(state_file),
        vector_store=vector_store,
        articles_dir=tmp_path / "articles",
        min_articles=1,
        summary_file=summary_file,
    )

    dry = pipeline.run(dry_run=True)
    assert (dry.added, dry.files_embedded) == (2, 0)
    assert not state_file.exists()
    assert not summary_file.exists()
    assert vector_store.sync_calls == []

    real = pipeline.run(dry_run=False)
    assert (real.added, real.failed, real.files_embedded) == (2, 1, 1)
    saved_state = JsonStateStore(state_file).load()
    assert 1 in saved_state and 2 not in saved_state
