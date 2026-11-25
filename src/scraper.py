from __future__ import annotations

from typing import Optional

from src.models import Article


class ZendeskScraper:
    """Client for fetching published Help Center articles from Zendesk."""

    def __init__(
        self,
        base_url: str = "https://support.optisigns.com",
        locale: str = "en-us",
        timeout: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.locale = locale
        self.timeout = timeout
        self.max_retries = max_retries

    def fetch_articles(
        self,
        min_articles: int = 30,
        max_articles: Optional[int] = None,
    ) -> list[Article]:
        """Fetch published Help Center articles across paginated Zendesk responses."""
        raise NotImplementedError("ZendeskScraper.fetch_articles is implemented in Sprint 2.")
