from __future__ import annotations

import logging
import re
import time
from typing import Any, Callable, Optional
from urllib.parse import urlparse

import httpx

from src.logging_config import LOGGER_NAME
from src.models import Article
from src.utils import slugify

logger = logging.getLogger(LOGGER_NAME)


class ScraperError(RuntimeError):
    """Raised when fetching Help Center articles fails."""


def extract_slug(article_data: dict[str, Any]) -> str:
    """Extract a clean slug from a Zendesk article payload."""
    article_id = article_data.get("id", "unknown")
    html_url = str(article_data.get("html_url") or "").strip()
    if html_url:
        tail = urlparse(html_url).path.rstrip("/").rsplit("/", 1)[-1]
        tail_without_id = re.sub(r"^\d+-", "", tail)
        if tail_without_id:
            return slugify(tail_without_id, fallback=f"article-{article_id}")

    title = str(article_data.get("title") or "").strip()
    if title:
        return slugify(title, fallback=f"article-{article_id}")
    return f"article-{article_id}"


class ZendeskScraper:
    """Client for fetching published Help Center articles from Zendesk."""

    def __init__(
        self,
        base_url: str,
        locale: str = "en-us",
        timeout: float = 30.0,
        max_retries: int = 3,
        backoff_seconds: float = 0.5,
        user_agent: str = "HelpCenter-KB-Sync/1.0",
        transport: Optional[httpx.BaseTransport] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        cleaned_url = (base_url or "").strip().rstrip("/")
        if not cleaned_url or not (
            cleaned_url.startswith("http://") or cleaned_url.startswith("https://")
        ):
            raise ValueError("base_url must be a non-empty http:// or https:// URL.")
        self.base_url = cleaned_url
        self.locale = locale
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self.user_agent = user_agent
        self.transport = transport
        self._sleep = sleep_fn or time.sleep

    def _get_json_with_retry(self, client: httpx.Client, url: str) -> dict[str, Any]:
        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                response = client.get(url)
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self._sleep(self.backoff_seconds * (2**attempt))
                    continue
                raise ScraperError(
                    f"Transport error fetching {url} after {self.max_retries + 1} attempts: {exc}"
                ) from exc

            status = response.status_code
            if status == 200:
                try:
                    data = response.json()
                except ValueError as exc:
                    raise ScraperError(f"Invalid JSON from {url}: {exc}") from exc
                if not isinstance(data, dict):
                    raise ScraperError(f"Unexpected JSON payload type from {url}")
                return data

            if status == 429 or 500 <= status < 600:
                last_error = ScraperError(f"HTTP {status} from {url}")
                if attempt < self.max_retries:
                    retry_after = response.headers.get("Retry-After")
                    delay = self.backoff_seconds * (2**attempt)
                    if retry_after and retry_after.strip().isdigit():
                        delay = float(retry_after.strip())
                    self._sleep(delay)
                    continue
                raise ScraperError(
                    f"HTTP {status} from {url} after {self.max_retries + 1} attempts"
                )

            raise ScraperError(f"Non-retryable HTTP {status} fetching {url}")

        raise ScraperError(f"Failed fetching {url}: {last_error}")

    def fetch_articles(
        self,
        min_articles: int = 30,
        max_articles: Optional[int] = None,
        per_page: int = 100,
    ) -> list[Article]:
        """Fetch published Help Center articles across paginated Zendesk responses."""
        clamped_per_page = max(1, min(100, per_page))
        next_url: Optional[str] = (
            f"{self.base_url}/api/v2/help_center/{self.locale}/articles.json"
            f"?per_page={clamped_per_page}"
        )

        articles: list[Article] = []
        seen_urls: set[str] = set()

        with httpx.Client(
            timeout=self.timeout,
            follow_redirects=True,
            transport=self.transport,
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        ) as client:
            while next_url:
                if next_url in seen_urls:
                    logger.warning("Pagination loop detected at %s; stopping.", next_url)
                    break
                seen_urls.add(next_url)

                payload = self._get_json_with_retry(client, next_url)
                for item in payload.get("articles") or []:
                    if item.get("draft"):
                        continue
                    body_html = str(item.get("body") or "")
                    if not body_html.strip():
                        continue

                    articles.append(
                        Article(
                            id=int(item["id"]),
                            title=str(item.get("title") or "").strip(),
                            slug=extract_slug(item),
                            html_url=str(item.get("html_url") or "").strip(),
                            updated_at=str(item.get("updated_at") or ""),
                            body_html=body_html,
                            section_id=item.get("section_id"),
                            draft=False,
                        )
                    )
                    if max_articles is not None and len(articles) >= max_articles:
                        return articles[:max_articles]

                next_url = payload.get("next_page") or None

        if len(articles) < min_articles:
            logger.warning(
                "Fetched %d published articles, below min_articles=%d",
                len(articles),
                min_articles,
            )
        return articles
