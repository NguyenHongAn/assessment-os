from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Mapping, Union

from src.models import (
    DeltaClassification,
    NormalizedArticle,
    SyncStateEntry,
    UploadResult,
)
from src.utils import compute_content_hash

__all__ = [
    "JsonStateStore",
    "StateError",
    "build_updated_state",
    "classify_delta",
    "compute_content_hash",
]


class StateError(RuntimeError):
    """Raised when persisted sync state cannot be parsed or validated."""


class JsonStateStore:
    """Atomic JSON file store for persisted article sync state."""

    def __init__(self, state_file: Path) -> None:
        self.state_file = state_file

    def load(self) -> dict[int, SyncStateEntry]:
        """Load state entries keyed by ``article_id``; returns ``{}`` if missing."""
        if not self.state_file.exists():
            return {}

        try:
            raw = json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise StateError(f"Failed to read state file {self.state_file}: {exc}") from exc

        if not isinstance(raw, dict):
            raise StateError(f"Expected JSON object in state file {self.state_file}")

        entries: dict[int, SyncStateEntry] = {}
        for key, item in raw.items():
            if not isinstance(item, dict):
                raise StateError(f"Invalid state entry for key {key!r}")
            try:
                article_id = int(item.get("article_id", key))
                entries[article_id] = SyncStateEntry(
                    article_id=article_id,
                    slug=str(item["slug"]),
                    content_hash=str(item["content_hash"]),
                    updated_at=str(item.get("updated_at") or ""),
                    html_url=str(item.get("html_url") or ""),
                    remote_doc_name=item.get("remote_doc_name"),
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise StateError(f"Malformed state entry for key {key!r}: {exc}") from exc

        return entries

    def save(self, state: Mapping[int, SyncStateEntry]) -> None:
        """Atomically persist state entries to ``self.state_file``."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        serializable = {
            str(article_id): asdict(entry)
            for article_id, entry in sorted(state.items(), key=lambda kv: kv[0])
        }
        payload = json.dumps(serializable, indent=2, sort_keys=True) + "\n"

        fd, tmp_path_str = tempfile.mkstemp(
            dir=str(self.state_file.parent),
            prefix=f".{self.state_file.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.chmod(tmp_path, 0o644)
            tmp_path.replace(self.state_file)
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink()
            raise


def classify_delta(
    articles: list[NormalizedArticle],
    previous_state: Union[Mapping[int, SyncStateEntry], Path],
) -> DeltaClassification:
    """Classify articles into added, updated, or skipped against persisted state."""
    state_map = (
        JsonStateStore(previous_state).load()
        if isinstance(previous_state, Path)
        else previous_state
    )

    result = DeltaClassification()
    for article in articles:
        existing = state_map.get(article.id)
        if existing is None:
            result.added.append(article)
        elif existing.content_hash != article.content_hash or (
            bool(article.updated_at)
            and bool(existing.updated_at)
            and existing.updated_at != article.updated_at
        ):
            result.updated.append(article)
        else:
            result.skipped.append(article)

    return result


def build_updated_state(
    previous_state: Mapping[int, SyncStateEntry],
    delta: DeltaClassification,
    upload_result: UploadResult,
) -> dict[int, SyncStateEntry]:
    """Merge successful uploads into ``previous_state`` while preserving failed items for retry."""
    next_state: dict[int, SyncStateEntry] = dict(previous_state)
    failed_ids = set(upload_result.failed_ids)

    for article in [*delta.added, *delta.updated]:
        if article.id in failed_ids:
            continue
        next_state[article.id] = SyncStateEntry(
            article_id=article.id,
            slug=article.slug,
            content_hash=article.content_hash,
            updated_at=article.updated_at,
            html_url=article.html_url,
            remote_doc_name=upload_result.remote_doc_map.get(article.id),
        )

    return next_state
