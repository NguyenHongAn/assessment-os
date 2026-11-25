from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

OPTIBOT_SYSTEM_PROMPT = (
    "You are OptiBot, the customer-support bot for OptiSigns.com.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    '• Cite up to 3 "Article URL:" lines per reply.'
)


@dataclass(frozen=True)
class Article:
    """Raw Help Center article fetched from Zendesk."""

    id: int
    title: str
    slug: str
    html_url: str
    updated_at: str
    body_html: str
    section_id: Optional[int] = None
    draft: bool = False


@dataclass(frozen=True)
class NormalizedArticle:
    """Cleaned Markdown article with deterministic content hash."""

    id: int
    title: str
    slug: str
    html_url: str
    updated_at: str
    markdown: str
    content_hash: str
    file_path: Optional[Path] = None


@dataclass
class DeltaClassification:
    """Result of comparing scraped articles against persisted sync state."""

    added: list[NormalizedArticle] = field(default_factory=list)
    updated: list[NormalizedArticle] = field(default_factory=list)
    skipped: list[NormalizedArticle] = field(default_factory=list)


@dataclass
class UploadResult:
    """Outcome of syncing delta articles to the Gemini File Search Store."""

    files_uploaded: int = 0
    chunks_embedded: int = 0
    failed_ids: list[int] = field(default_factory=list)
    remote_doc_map: dict[int, str] = field(default_factory=dict)


@dataclass(frozen=True)
class RunSummary:
    """End-of-run telemetry summary for daily job logging."""

    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    files_embedded: int = 0
    chunks_embedded: int = 0
