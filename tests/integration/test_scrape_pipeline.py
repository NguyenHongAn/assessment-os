from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from src.converter import save_articles
from src.scraper import ZendeskScraper


def _build_mock_article(idx: int, *, draft: bool = False) -> dict:
    return {
        "id": 5000 + idx,
        "title": f"OptiSigns Feature {idx}",
        "html_url": f"https://support.optisigns.com/hc/en-us/articles/{5000 + idx}-optisigns-feature-{idx}",
        "updated_at": "2026-01-20T12:00:00Z",
        "section_id": 100,
        "draft": draft,
        "body": (
            "<nav>Top Nav</nav>"
            "<style>.hidden{display:none;}</style>"
            f"<h2>Overview {idx}</h2>"
            f"<p>See <a href=\"/hc/en-us/articles/5001-optisigns-feature-1\">related doc</a>.</p>"
            "<pre><code class=\"language-bash\">echo \"ok\"</code></pre>"
            "<script>track()</script>"
        ),
    }


def test_tc_i01_offline_scrape_and_markdown_pipeline(tmp_path: Path) -> None:
    page1 = [_build_mock_article(i) for i in range(1, 21)]
    page2 = [_build_mock_article(i) for i in range(21, 36)] + [
        _build_mock_article(998, draft=True),
        _build_mock_article(999, draft=True),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(200, json={"articles": page2, "next_page": None})
        return httpx.Response(
            200,
            json={
                "articles": page1,
                "next_page": "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?page=2",
            },
        )

    scraper = ZendeskScraper(transport=httpx.MockTransport(handler))
    articles = scraper.fetch_articles(min_articles=30)
    saved = save_articles(articles, output_dir=tmp_path)

    assert len(saved) >= 30
    assert len(saved) == 35

    for item in saved:
        assert item.file_path is not None and item.file_path.exists()
        content = item.file_path.read_text(encoding="utf-8")
        assert "Article URL: https://support.optisigns.com/" in content
        assert content.startswith("# ")
        assert "## Overview" in content
        assert "(/hc/en-us/articles/5001-optisigns-feature-1)" in content
        assert "```bash" in content
        for forbidden in ("<script", "<style", "<nav", "Top Nav", "track()"):
            assert forbidden not in content


@pytest.mark.live
def test_tc_i01_live_optisigns_scrape_and_normalize(tmp_path: Path) -> None:
    scraper = ZendeskScraper(base_url="https://support.optisigns.com", locale="en-us")
    articles = scraper.fetch_articles(min_articles=30, max_articles=35)
    saved = save_articles(articles, output_dir=tmp_path)

    assert len(saved) >= 30
    for item in saved:
        assert item.file_path is not None and item.file_path.exists()
        content = item.file_path.read_text(encoding="utf-8")
        assert content.startswith("# ")
        assert "Article URL: https://support.optisigns.com/" in content
        assert "<script" not in content.lower()
        assert "<style" not in content.lower()
        assert "<nav" not in content.lower()
