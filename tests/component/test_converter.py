from __future__ import annotations

from pathlib import Path

from src.converter import html_to_markdown, save_article_markdown, save_articles, slugify
from src.models import Article


def test_tc_c03_preserves_structure_links_code_and_strips_noise() -> None:
    html = """
    <nav class="breadcrumb">Home > Docs</nav>
    <style>.promo { color: red; }</style>
    <!-- internal comment -->
    <div class="cookie-banner">Accept cookies</div>
    <div class="article-body">
        <h1>How to add a YouTube video</h1>
        <h2>Step 1</h2>
        <p>Use <a href="/hc/en-us/articles/123-other">this guide</a>.</p>
        <ul>
            <li>Open Assets</li>
            <li>Select YouTube
                <ul><li>Paste URL</li></ul>
            </li>
        </ul>
        <pre><code class="language-json">{"type": "youtube"}</code></pre>
        <iframe src="https://www.youtube.com/embed/dQw4w9WgXcQ"></iframe>
    </div>
    <div class="related-articles">Other links</div>
    <script>console.log("tracker")</script>
    <footer>Copyright OptiSigns</footer>
    """
    md_text = html_to_markdown(
        html,
        article_url="https://support.optisigns.com/hc/en-us/articles/360016-How-to-add-a-YouTube-video",
        title="How to add a YouTube video",
    )

    assert md_text.startswith("# How to add a YouTube video\n\nArticle URL: https://support.optisigns.com/hc/en-us/articles/360016-How-to-add-a-YouTube-video\n")
    # Duplicate H1 matching title is deduplicated
    assert md_text.count("# How to add a YouTube video") == 1
    assert "## Step 1" in md_text
    assert "[this guide](/hc/en-us/articles/123-other)" in md_text
    assert "```json\n{\"type\": \"youtube\"}\n```" in md_text
    assert "[Embedded Video](https://www.youtube.com/embed/dQw4w9WgXcQ)" in md_text

    for noise in ("Breadcrumb", "Home > Docs", "Accept cookies", "tracker", "Copyright", "related-articles", "<script", "<style", "<nav"):
        assert noise not in md_text


def test_tc_c04_save_article_markdown_naming_and_collisions(tmp_path: Path) -> None:
    a1 = Article(
        id=101,
        title="Setup Guide",
        slug="setup-guide",
        html_url="https://support.optisigns.com/hc/en-us/articles/101-setup-guide",
        updated_at="2026-01-01T00:00:00Z",
        body_html="<p>First guide</p>",
    )
    a2 = Article(
        id=202,
        title="Setup Guide",
        slug="setup-guide",
        html_url="https://support.optisigns.com/hc/en-us/articles/202-setup-guide",
        updated_at="2026-01-02T00:00:00Z",
        body_html="<p>Second guide</p>",
    )

    saved = save_articles([a1, a2], output_dir=tmp_path)
    assert len(saved) == 2
    assert saved[0].file_path == tmp_path / "setup-guide.md"
    assert saved[1].file_path == tmp_path / "setup-guide-202.md"
    assert saved[0].file_path.exists()
    assert saved[1].file_path.exists()
    assert len(saved[0].content_hash) == 64
    assert saved[0].content_hash != saved[1].content_hash

    # Deterministic re-save
    again = save_article_markdown(a1, output_dir=tmp_path)
    assert again.content_hash == saved[0].content_hash


def test_tc_c05_malformed_and_empty_html_graceful() -> None:
    malformed = "<h2>Unclosed heading<p>Paragraph without close<a href=''>Empty link</a>"
    md_malformed = html_to_markdown(malformed, article_url="https://example.com/a", title="Malformed")
    assert "# Malformed" in md_malformed
    assert "Article URL: https://example.com/a" in md_malformed
    assert "Paragraph without close" in md_malformed

    md_empty = html_to_markdown(None, article_url="https://example.com/b", title="   ")
    assert "# Untitled Article" in md_empty
    assert "Article URL: https://example.com/b" in md_empty

    assert slugify("Café & Résumé: 100%!") == "cafe-resume-100"
    assert slugify("!!!", fallback="article-7") == "article-7"
