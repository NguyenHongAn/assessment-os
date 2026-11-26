from __future__ import annotations

import re
import unicodedata
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup, Comment, Tag
from markdownify import markdownify as md

from src.delta import compute_content_hash
from src.models import Article, NormalizedArticle

_NOISE_TAGS = (
    "script",
    "style",
    "nav",
    "footer",
    "header",
    "aside",
    "noscript",
    "iframe",
    "form",
    "button",
    "svg",
)

_NOISE_TOKENS = frozenset(
    {
        "nav",
        "navbar",
        "breadcrumb",
        "breadcrumbs",
        "sidebar",
        "footer",
        "cookie",
        "consent",
        "banner",
        "promo",
        "ad",
        "ads",
        "advert",
        "advertisement",
        "social-share",
        "share-buttons",
        "related-articles",
        "article-votes",
        "article-comments",
    }
)

_VIDEO_EMBED_HOSTS = ("youtube.com", "youtu.be", "vimeo.com")


def slugify(text: str, fallback: str = "article") -> str:
    """Convert text into a lowercase ASCII URL/filename-safe slug."""
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or fallback


def _has_noise_token(value: str) -> bool:
    """Check whether an element class/id string matches a known noise token."""
    lower = value.lower()
    if lower in _NOISE_TOKENS:
        return True
    parts = re.split(r"[-_\s]+", lower)
    return any(part in _NOISE_TOKENS for part in parts if part)


def _strip_noise(soup: BeautifulSoup) -> None:
    """Remove navigation, scripts, styles, ads, comments, and boilerplate."""
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    for iframe in list(soup.find_all("iframe")):
        src = (iframe.get("src") or "").strip()
        if any(host in src.lower() for host in _VIDEO_EMBED_HOSTS):
            link_p = soup.new_tag("p")
            link = soup.new_tag("a", href=src)
            link.string = "Embedded Video"
            link_p.append(link)
            iframe.replace_with(link_p)
        else:
            iframe.decompose()

    for tag_name in _NOISE_TAGS:
        for el in list(soup.find_all(tag_name)):
            el.decompose()

    for el in list(soup.find_all(True)):
        if el.attrs is None:
            continue
        classes = el.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        el_id = el.get("id") or ""
        tokens = [*classes, el_id] if el_id else list(classes)
        if any(_has_noise_token(str(tok)) for tok in tokens if tok):
            el.decompose()


def _extract_code_language(el: Tag) -> str:
    """Extract language identifier from <pre> or its child <code> class."""
    candidates: list[Tag] = [el]
    code_child = el.find("code")
    if isinstance(code_child, Tag):
        candidates.append(code_child)

    for node in candidates:
        classes = node.get("class") or []
        if isinstance(classes, str):
            classes = [classes]
        for cls in classes:
            match = re.match(r"^(?:language|lang)-([a-zA-Z0-9_+-]+)$", str(cls))
            if match:
                return match.group(1).lower()
    return ""


def _normalize_whitespace(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    collapsed = re.sub(r"\n{3,}", "\n\n", "\n".join(lines))
    return collapsed.strip()


def html_to_markdown(html: Optional[str], article_url: str, title: str) -> str:
    """Convert Zendesk article HTML into clean, citation-ready Markdown."""
    clean_title = (title or "").strip() or "Untitled Article"
    clean_url = (article_url or "").strip()

    soup = BeautifulSoup(html or "", "html.parser")
    _strip_noise(soup)

    raw_md = md(
        str(soup),
        heading_style="ATX",
        bullets="-",
        code_language_callback=_extract_code_language,
    )
    body_md = _normalize_whitespace(raw_md)

    if body_md:
        first_line, *rest = body_md.splitlines()
        if first_line.startswith("# "):
            heading_text = first_line[2:].strip()
            if heading_text.lower() == clean_title.lower():
                body_md = "\n".join(rest).lstrip()

    header_lines = [f"# {clean_title}", "", f"Article URL: {clean_url}"]
    if body_md:
        return "\n".join([*header_lines, "", body_md]) + "\n"
    return "\n".join(header_lines) + "\n"


def save_article_markdown(
    article: Article,
    output_dir: Path,
    used_slugs: Optional[set[str]] = None,
) -> NormalizedArticle:
    """Normalize an article to Markdown and write it to ``<slug>.md``."""
    output_dir.mkdir(parents=True, exist_ok=True)
    base_slug = slugify(
        article.slug or article.title,
        fallback=f"article-{article.id}",
    )

    if used_slugs is not None:
        final_slug = f"{base_slug}-{article.id}" if base_slug in used_slugs else base_slug
        used_slugs.add(final_slug)
    else:
        final_slug = base_slug

    markdown = html_to_markdown(
        article.body_html,
        article_url=article.html_url,
        title=article.title,
    )
    content_hash = compute_content_hash(markdown)
    file_path = output_dir / f"{final_slug}.md"
    file_path.write_text(markdown, encoding="utf-8")

    return NormalizedArticle(
        id=article.id,
        title=article.title,
        slug=final_slug,
        html_url=article.html_url,
        updated_at=article.updated_at,
        markdown=markdown,
        content_hash=content_hash,
        file_path=file_path,
    )


def save_articles(articles: list[Article], output_dir: Path) -> list[NormalizedArticle]:
    """Normalize and save a list of articles with collision-safe slugs."""
    used_slugs: set[str] = set()
    return [
        save_article_markdown(article, output_dir=output_dir, used_slugs=used_slugs)
        for article in articles
    ]
