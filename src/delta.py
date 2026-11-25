from __future__ import annotations

from pathlib import Path

from src.models import DeltaClassification, NormalizedArticle


def compute_content_hash(markdown: str) -> str:
    """Compute a deterministic SHA-256 hash of normalized Markdown content."""
    raise NotImplementedError("compute_content_hash is implemented in Sprint 3.")


def classify_delta(
    articles: list[NormalizedArticle],
    state_file: Path,
) -> DeltaClassification:
    """Classify articles into added, updated, or skipped against persisted state."""
    raise NotImplementedError("classify_delta is implemented in Sprint 3.")
