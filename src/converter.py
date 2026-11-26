from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, Optional

from bs4 import BeautifulSoup, Comment, Tag
from markdownify import markdownify as md

from src.interfaces import ArticleConverter
from src.models import Article, NormalizedArticle
from src.utils import compute_content_hash, slugify

__all__ = [
    "DEFAULT_NOISE_TAGS",
    "DEFAULT_NOISE_TOKENS",
    "DEFAULT_VIDEO_EMBED_HOSTS",
    "HtmlToMarkdownConverter",
    "html_to_markdown",
    "save_article_markdown",
    "save_articles",
    "slugify",
]

DEFAULT_NOISE_TAGS: tuple[str, ...] = (
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

DEFAULT_NOISE_TOKENS: frozenset[str] = frozenset(
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

DEFAULT_VIDEO_EMBED_HOSTS: tuple[str, ...] = ("youtube.com", "youtu.be", "vimeo.com")


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


class HtmlToMarkdownConverter:
    """Configurable HTML-to-Markdown converter for Help Center articles."""

    def __init__(
        self,
        noise_tags: Iterable[str] = DEFAULT_NOISE_TAGS,
        noise_tokens: Iterable[str] = DEFAULT_NOISE_TOKENS,
        video_embed_hosts: Iterable[str] = DEFAULT_VIDEO_EMBED_HOSTS,
        heading_style: str = "ATX",
        bullets: str = "-",
        citation_label: str = "Article URL",
    ) -> None:
        self.noise_tags = tuple(noise_tags)
        self.noise_tokens = frozenset(t.lower() for t in noise_tokens)
        self.video_embed_hosts = tuple(h.lower() for h in video_embed_hosts)
        self.heading_style = heading_style
        self.bullets = bullets
        self.citation_label = citation_label

    def _has_noise_token(self, value: str) -> bool:
        lower = value.lower()
        if lower in self.noise_tokens:
            return True
        parts = re.split(r"[-_\s]+", lower)
        return any(part in self.noise_tokens for part in parts if part)

    def _strip_noise(self, soup: BeautifulSoup) -> None:
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

        for iframe in list(soup.find_all("iframe")):
            src = (iframe.get("src") or "").strip()
            if any(host in src.lower() for host in self.video_embed_hosts):
                link_p = soup.new_tag("p")
                link = soup.new_tag("a", href=src)
                link.string = "Embedded Video"
                link_p.append(link)
                iframe.replace_with(link_p)
            else:
                iframe.decompose()

        for tag_name in self.noise_tags:
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
            if any(self._has_noise_token(str(tok)) for tok in tokens if tok):
                el.decompose()

    def convert_html(self, html: Optional[str], article_url: str, title: str) -> str:
        """Convert raw HTML into clean, citation-ready Markdown."""
        clean_title = (title or "").strip() or "Untitled Article"
        clean_url = (article_url or "").strip()

        soup = BeautifulSoup(html or "", "html.parser")
        self._strip_noise(soup)

        raw_md = md(
            str(soup),
            heading_style=self.heading_style,
            bullets=self.bullets,
            code_language_callback=_extract_code_language,
        )
        body_md = _normalize_whitespace(raw_md)

        if body_md:
            first_line, *rest = body_md.splitlines()
            if first_line.startswith("# "):
                heading_text = first_line[2:].strip()
                if heading_text.lower() == clean_title.lower():
                    body_md = "\n".join(rest).lstrip()

        header_lines = [f"# {clean_title}", "", f"{self.citation_label}: {clean_url}"]
        if body_md:
            return "\n".join([*header_lines, "", body_md]) + "\n"
        return "\n".join(header_lines) + "\n"

    def convert(self, article: Article) -> str:
        """Convert an ``Article`` instance to normalized Markdown."""
        return self.convert_html(
            article.body_html,
            article_url=article.html_url,
            title=article.title,
        )


_DEFAULT_CONVERTER = HtmlToMarkdownConverter()


def html_to_markdown(
    html: Optional[str],
    article_url: str,
    title: str,
    converter: Optional[HtmlToMarkdownConverter] = None,
) -> str:
    """Convert Help Center HTML into clean, citation-ready Markdown."""
    active = converter or _DEFAULT_CONVERTER
    return active.convert_html(html, article_url=article_url, title=title)


def save_article_markdown(
    article: Article,
    output_dir: Path,
    used_slugs: Optional[set[str]] = None,
    converter: Optional[ArticleConverter] = None,
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

    active_converter = converter or _DEFAULT_CONVERTER
    markdown = active_converter.convert(article)
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


def save_articles(
    articles: list[Article],
    output_dir: Path,
    converter: Optional[ArticleConverter] = None,
) -> list[NormalizedArticle]:
    """Normalize and save a list of articles with collision-safe slugs."""
    used_slugs: set[str] = set()
    return [
        save_article_markdown(
            article,
            output_dir=output_dir,
            used_slugs=used_slugs,
            converter=converter,
        )
        for article in articles
    ]
