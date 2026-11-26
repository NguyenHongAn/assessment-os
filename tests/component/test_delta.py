from __future__ import annotations

from pathlib import Path

import pytest

from src.delta import JsonStateStore, StateError, build_updated_state, classify_delta
from src.interfaces import StateStore
from src.models import NormalizedArticle, SyncStateEntry, UploadResult
from src.utils import compute_content_hash


def _norm_article(idx: int, body: str = "Body text", updated_at: str = "2026-01-01T00:00:00Z") -> NormalizedArticle:
    md_text = f"# Article {idx}\n\nArticle URL: https://support.example.com/hc/en-us/articles/{idx}\n\n{body}\n"
    return NormalizedArticle(
        id=idx,
        title=f"Article {idx}",
        slug=f"article-{idx}",
        html_url=f"https://support.example.com/hc/en-us/articles/{idx}",
        updated_at=updated_at,
        markdown=md_text,
        content_hash=compute_content_hash(md_text),
    )


def test_tc_c06_tc_c07_delta_classification_and_idempotency(tmp_path: Path) -> None:
    state_file = tmp_path / "state.json"
    store = JsonStateStore(state_file)
    assert isinstance(store, StateStore)

    a1 = _norm_article(1, body="First")
    a2 = _norm_article(2, body="Second")

    # Cold start -> all added
    delta1 = classify_delta([a1, a2], state_file)
    assert [a.id for a in delta1.added] == [1, 2]
    assert delta1.updated == []
    assert delta1.skipped == []

    state1 = build_updated_state(
        {},
        delta1,
        UploadResult(
            files_uploaded=2,
            chunks_embedded=2,
            remote_doc_map={1: "fileSearchStores/s1/documents/d1", 2: "fileSearchStores/s1/documents/d2"},
        ),
    )
    store.save(state1)

    # Repeat unchanged -> all skipped (idempotent)
    delta2 = classify_delta([a1, a2], state_file)
    assert delta2.added == []
    assert delta2.updated == []
    assert [a.id for a in delta2.skipped] == [1, 2]

    # Edit a2 content + add a3 -> 1 added, 1 updated, 1 skipped
    a2_edited = _norm_article(2, body="Second edited")
    a3 = _norm_article(3, body="Third")
    delta3 = classify_delta([a1, a2_edited, a3], store.load())
    assert [a.id for a in delta3.added] == [3]
    assert [a.id for a in delta3.updated] == [2]
    assert [a.id for a in delta3.skipped] == [1]

    # Timestamp change alone also triggers update
    a1_touched = _norm_article(1, body="First", updated_at="2026-02-01T00:00:00Z")
    delta4 = classify_delta([a1_touched], state1)
    assert [a.id for a in delta4.updated] == [1]


def test_tc_c08_partial_upload_failure_retries_on_next_run() -> None:
    a1 = _norm_article(1, body="Old 1")
    prev_state = {
        1: SyncStateEntry(
            article_id=1,
            slug=a1.slug,
            content_hash=a1.content_hash,
            updated_at=a1.updated_at,
            html_url=a1.html_url,
            remote_doc_name="fileSearchStores/s1/documents/d1",
        )
    }

    a1_new = _norm_article(1, body="New 1")
    a2_new = _norm_article(2, body="New 2")
    delta = classify_delta([a1_new, a2_new], prev_state)

    # Article 1 succeeds, Article 2 fails
    upload_res = UploadResult(
        files_uploaded=1,
        chunks_embedded=1,
        failed_ids=[2],
        remote_doc_map={1: "fileSearchStores/s1/documents/d1-v2"},
    )
    next_state = build_updated_state(prev_state, delta, upload_res)
    assert 1 in next_state
    assert next_state[1].content_hash == a1_new.content_hash
    assert 2 not in next_state

    # Next run skips 1 and retries 2
    retry_delta = classify_delta([a1_new, a2_new], next_state)
    assert [a.id for a in retry_delta.added] == [2]
    assert [a.id for a in retry_delta.skipped] == [1]


def test_state_store_corrupted_json_raises_state_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "bad_state.json"
    bad_file.write_text("{not valid json", encoding="utf-8")
    with pytest.raises(StateError):
        JsonStateStore(bad_file).load()
