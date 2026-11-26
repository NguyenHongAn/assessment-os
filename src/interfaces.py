from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from src.models import Article, DeltaClassification, UploadResult


@runtime_checkable
class ArticleSource(Protocol):
    """Protocol for fetching articles from a knowledge base source."""

    def fetch_articles(
        self,
        min_articles: int = 30,
        max_articles: Optional[int] = None,
    ) -> list[Article]:
        """Fetch published articles from the source."""
        ...


@runtime_checkable
class ArticleConverter(Protocol):
    """Protocol for converting raw articles into clean Markdown."""

    def convert(self, article: Article) -> str:
        """Convert an Article into normalized Markdown text."""
        ...


@runtime_checkable
class VectorStoreClient(Protocol):
    """Protocol for syncing normalized articles to a vector store."""

    def ensure_store(self) -> str:
        """Return an existing store identifier or create a new one."""
        ...

    def sync_delta(
        self,
        delta: DeltaClassification,
        existing_doc_map: Optional[dict[int, str]] = None,
    ) -> UploadResult:
        """Upload added and updated articles to the vector store."""
        ...

    def query(self, question: str) -> str:
        """Query the vector store using the configured assistant prompt."""
        ...
