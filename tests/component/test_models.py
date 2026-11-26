from __future__ import annotations

from pathlib import Path

from src.models import (
    Article,
    DeltaClassification,
    NormalizedArticle,
    RunSummary,
    UploadResult,
)


def test_article_and_normalized_defaults() -> None:
    article = Article(
        id=1,
        title="Sample",
        slug="sample",
        html_url="https://support.example.com/hc/en-us/articles/1-sample",
        updated_at="2026-01-01T00:00:00Z",
        body_html="<p>Hi</p>",
    )
    assert article.draft is False
    assert article.section_id is None

    normalized = NormalizedArticle(
        id=1,
        title="Sample",
        slug="sample",
        html_url=article.html_url,
        updated_at=article.updated_at,
        markdown="# Sample\n",
        content_hash="abc123",
        file_path=Path("data/articles/sample.md"),
    )
    assert normalized.file_path == Path("data/articles/sample.md")


def test_delta_upload_and_summary_defaults() -> None:
    delta = DeltaClassification()
    assert delta.added == []
    assert delta.updated == []
    assert delta.skipped == []

    upload = UploadResult()
    assert upload.files_uploaded == 0
    assert upload.chunks_embedded == 0
    assert upload.failed_ids == []
    assert upload.remote_doc_map == {}

    summary = RunSummary(added=2, updated=1, skipped=27, files_embedded=3, chunks_embedded=12)
    assert summary.failed == 0
    assert summary.files_embedded == 3
