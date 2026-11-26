from __future__ import annotations

import os
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values

from src.converter import save_articles
from src.scraper import ZendeskScraper

BASE_URL = "https://support.example.com"


def _build_mock_article(idx: int, *, draft: bool = False) -> dict:
    return {
        "id": 5000 + idx,
        "title": f"Support Feature {idx}",
        "html_url": f"{BASE_URL}/hc/en-us/articles/{5000 + idx}-support-feature-{idx}",
        "updated_at": "2026-01-20T12:00:00Z",
        "section_id": 100,
        "draft": draft,
        "body": (
            "<nav>Top Nav</nav>"
            "<style>.hidden{display:none;}</style>"
            f"<h2>Overview {idx}</h2>"
            f'<p>See <a href="/hc/en-us/articles/5001-support-feature-1">related doc</a>.</p>'
            '<pre><code class="language-bash">echo "ok"</code></pre>'
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
                "next_page": f"{BASE_URL}/api/v2/help_center/en-us/articles.json?page=2",
            },
        )

    scraper = ZendeskScraper(base_url=BASE_URL, transport=httpx.MockTransport(handler))
    articles = scraper.fetch_articles(min_articles=30)
    saved = save_articles(articles, output_dir=tmp_path)

    assert len(saved) >= 30
    assert len(saved) == 35

    for item in saved:
        assert item.file_path is not None and item.file_path.exists()
        content = item.file_path.read_text(encoding="utf-8")
        assert f"Article URL: {BASE_URL}/" in content
        assert content.startswith("# ")
        assert "## Overview" in content
        assert "(/hc/en-us/articles/5001-support-feature-1)" in content
        assert "```bash" in content
        for forbidden in ("<script", "<style", "<nav", "Top Nav", "track()"):
            assert forbidden not in content


@pytest.mark.live
def test_tc_i01_live_help_center_scrape_and_normalize(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    dotenv_map = dotenv_values(repo_root / ".env") if (repo_root / ".env").exists() else {}
    target_url = (
        os.environ.get("ZENDESK_BASE_URL")
        or dotenv_map.get("ZENDESK_BASE_URL")
        or ""
    ).strip()

    if not target_url or "example.com" in target_url:
        pytest.skip("Set ZENDESK_BASE_URL in environment or .env to run live scraper test")

    scraper = ZendeskScraper(base_url=target_url, locale="en-us")
    articles = scraper.fetch_articles(min_articles=30, max_articles=35)
    saved = save_articles(articles, output_dir=tmp_path)

    assert len(saved) >= 30
    for item in saved:
        assert item.file_path is not None and item.file_path.exists()
        content = item.file_path.read_text(encoding="utf-8")
        assert content.startswith("# ")
        assert f"Article URL: {target_url.rstrip('/')}/" in content
        assert "<script" not in content.lower()
        assert "<style" not in content.lower()
        assert "<nav" not in content.lower()
