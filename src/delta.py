from __future__ import annotations

from pathlib import Path

from src.models import DeltaClassification, NormalizedArticle
from src.utils import compute_content_hash

__all__ = ["compute_content_hash", "classify_delta"]


def classify_delta(
    articles: list[NormalizedArticle],
    state_file: Path,
) -> DeltaClassification:
    """Classify articles into added, updated, or skipped against persisted state."""
    raise NotImplementedError("classify_delta is implemented in Sprint 3.")
