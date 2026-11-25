from __future__ import annotations

from typing import Optional

from src.models import DeltaClassification, UploadResult


class GeminiVectorStoreClient:
    """Wrapper around google-genai File Search Store operations."""

    def __init__(
        self,
        api_key: str,
        store_name: str = "optisigns-support-kb",
        model: str = "gemini-2.5-flash",
    ) -> None:
        self.api_key = api_key
        self.store_name = store_name
        self.model = model

    def ensure_store(self) -> str:
        """Return existing File Search Store resource name or create a new one."""
        raise NotImplementedError("ensure_store is implemented in Sprint 3.")

    def sync_delta(
        self,
        delta: DeltaClassification,
        existing_doc_map: Optional[dict[int, str]] = None,
    ) -> UploadResult:
        """Upload added and updated articles to the File Search Store."""
        raise NotImplementedError("sync_delta is implemented in Sprint 3.")

    def query(self, question: str) -> str:
        """Query the File Search Store using the verbatim OptiBot system prompt."""
        raise NotImplementedError("query is implemented in Sprint 3.")
