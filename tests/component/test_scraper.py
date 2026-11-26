from __future__ import annotations

import json

import httpx
import pytest

from src.scraper import ScraperError, ZendeskScraper, extract_slug


def _make_article(idx: int, *, draft: bool = False, body: str = "<p>Hello</p>") -> dict:
    return {
        "id": 1000 + idx,
        "title": f"Article {idx}",
        "html_url": f"https://support.optisigns.com/hc/en-us/articles/{1000 + idx}-Article-{idx}",
        "updated_at": "2026-01-15T10:00:00Z",
        "section_id": 42,
        "draft": draft,
        "body": body,
    }


def test_tc_c01_paginated_fetch_and_max_articles() -> None:
    page1_articles = [_make_article(i) for i in range(1, 21)]
    page2_articles = [_make_article(i) for i in range(21, 41)]

    def handler(request: httpx.Request) -> httpx.Response:
        if "page=2" in str(request.url):
            return httpx.Response(
                200,
                json={"articles": page2_articles, "next_page": None},
            )
        return httpx.Response(
            200,
            json={
                "articles": page1_articles,
                "next_page": "https://support.optisigns.com/api/v2/help_center/en-us/articles.json?page=2",
            },
        )

    scraper = ZendeskScraper(transport=httpx.MockTransport(handler))
    articles = scraper.fetch_articles(min_articles=30)

    assert len(articles) == 40
    assert articles[0].id == 1001
    assert articles[0].slug == "article-1"
    assert articles[-1].id == 1040

    capped = scraper.fetch_articles(min_articles=30, max_articles=32)
    assert len(capped) == 32


def test_tc_c02_filters_drafts_and_empty_bodies() -> None:
    payload = {
        "articles": [
            _make_article(1, draft=False, body="<p>Valid body</p>"),
            _make_article(2, draft=True, body="<p>Draft body</p>"),
            _make_article(3, draft=False, body="   \n\t "),
            _make_article(4, draft=False, body=""),
        ],
        "next_page": None,
    }

    scraper = ZendeskScraper(
        transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload))
    )
    articles = scraper.fetch_articles(min_articles=1)

    assert [a.id for a in articles] == [1001]


def test_tc_c02_retries_on_429_and_503_then_succeeds() -> None:
    attempts = 0
    sleeps: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return httpx.Response(429, headers={"Retry-After": "2"})
        if attempts == 2:
            return httpx.Response(503)
        return httpx.Response(
            200,
            json={"articles": [_make_article(1)], "next_page": None},
        )

    scraper = ZendeskScraper(
        max_retries=3,
        backoff_seconds=0.25,
        transport=httpx.MockTransport(handler),
        sleep_fn=sleeps.append,
    )
    articles = scraper.fetch_articles(min_articles=1)

    assert len(articles) == 1
    assert attempts == 3
    assert sleeps == [2.0, 0.5]


def test_tc_c02_fails_after_max_retries_and_immediately_on_404() -> None:
    sleep_calls: list[float] = []
    scraper_500 = ZendeskScraper(
        max_retries=2,
        backoff_seconds=0.1,
        transport=httpx.MockTransport(lambda req: httpx.Response(500)),
        sleep_fn=sleep_calls.append,
    )
    with pytest.raises(ScraperError, match="HTTP 500"):
        scraper_500.fetch_articles(min_articles=1)
    assert len(sleep_calls) == 2

    attempts_404 = 0

    def handler_404(request: httpx.Request) -> httpx.Response:
        nonlocal attempts_404
        attempts_404 += 1
        return httpx.Response(404)

    scraper_404 = ZendeskScraper(
        max_retries=3,
        transport=httpx.MockTransport(handler_404),
        sleep_fn=lambda _: None,
    )
    with pytest.raises(ScraperError, match="Non-retryable HTTP 404"):
        scraper_404.fetch_articles(min_articles=1)
    assert attempts_404 == 1


def test_extract_slug_fallbacks() -> None:
    assert (
        extract_slug(
            {
                "id": 99,
                "title": "Some Title",
                "html_url": "https://support.optisigns.com/hc/en-us/articles/360016-How-To-Use",
            }
        )
        == "how-to-use"
    )
    assert extract_slug({"id": 99, "title": "Fallback Title!", "html_url": ""}) == "fallback-title"
    assert extract_slug({"id": 99, "title": "", "html_url": ""}) == "article-99"
