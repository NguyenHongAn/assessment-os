from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
    "You are {assistant_name}, the customer-support bot for {brand_name}.\n"
    "• Tone: helpful, factual, concise.\n"
    "• Only answer using the uploaded docs.\n"
    "• Max 5 bullet points; else link to the doc.\n"
    '• Cite up to 3 "Article URL:" lines per reply.'
)

_BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+\.)\s+")
_ARTICLE_URL_RE = re.compile(r"^\s*Article URL:\s*https?://\S+", re.IGNORECASE)
_HTTP_URL_RE = re.compile(r"https?://\S+")


def build_system_prompt(
    assistant_name: str = "SupportBot",
    brand_name: str = "Example.com",
    custom_prompt: Optional[str] = None,
) -> str:
    """Build the assistant system prompt from persona settings or an explicit override."""
    if custom_prompt and custom_prompt.strip():
        return custom_prompt.strip()
    return DEFAULT_SYSTEM_PROMPT_TEMPLATE.format(
        assistant_name=assistant_name.strip() or "SupportBot",
        brand_name=brand_name.strip() or "Example.com",
    )


def validate_assistant_response(
    response_text: str,
    max_bullets: int = 5,
    max_citations: int = 3,
) -> list[str]:
    """Validate an assistant reply against bullet-count and citation rules."""
    text = (response_text or "").strip()
    if not text:
        return ["Response text is empty."]

    violations: list[str] = []
    lines = text.splitlines()

    bullet_count = sum(1 for line in lines if _BULLET_RE.match(line))
    has_doc_link = bool(_HTTP_URL_RE.search(text))
    if bullet_count > max_bullets and not has_doc_link:
        violations.append(
            f"Found {bullet_count} bullet points (max {max_bullets}) without a documentation link."
        )

    citation_count = sum(1 for line in lines if _ARTICLE_URL_RE.match(line))
    if citation_count == 0:
        violations.append('Missing required "Article URL:" citation line.')
    elif citation_count > max_citations:
        violations.append(
            f'Found {citation_count} "Article URL:" lines (max {max_citations}).'
        )

    return violations


@dataclass(frozen=True)
class Article:
    """Raw Help Center article fetched from a knowledge base source."""

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


@dataclass(frozen=True)
class SyncStateEntry:
    """Persisted sync state for a single knowledge base article."""

    article_id: int
    slug: str
    content_hash: str
    updated_at: str
    html_url: str
    remote_doc_name: Optional[str] = None


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
