from __future__ import annotations

import hashlib
import re
import unicodedata


def slugify(text: str, fallback: str = "article") -> str:
    """Convert text into a lowercase ASCII URL/filename-safe slug."""
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or fallback


def compute_content_hash(markdown: str) -> str:
    """Compute a deterministic SHA-256 hash of normalized Markdown content."""
    return hashlib.sha256(markdown.encode("utf-8")).hexdigest()
