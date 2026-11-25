from __future__ import annotations

from pathlib import Path

from src.models import Article, NormalizedArticle


def html_to_markdown(html: str, article_url: str, title: str) -> str:
    """Convert Zendesk article HTML into clean, citation-ready Markdown."""
    raise NotImplementedError("html_to_markdown is implemented in Sprint 2.")


def save_article_markdown(
    article: Article,
    output_dir: Path,
) -> NormalizedArticle:
    """Normalize an article to Markdown and write it to ``<slug>.md``."""
    raise NotImplementedError("save_article_markdown is implemented in Sprint 2.")
