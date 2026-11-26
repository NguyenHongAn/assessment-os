from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional

import httpx

from src.chunking import ChunkingConfig, estimate_chunk_count
from src.logging_config import LOGGER_NAME
from src.models import (
    DeltaClassification,
    NormalizedArticle,
    SyncStateEntry,
    UploadResult,
    build_system_prompt,
)

logger = logging.getLogger(LOGGER_NAME)


class VectorStoreError(RuntimeError):
    """Raised when a Gemini File Search Store API operation fails."""


def _extract_custom_metadata(items: list[dict[str, Any]]) -> dict[str, str]:
    """Normalize Gemini ``customMetadata`` list into a flat string dict."""
    parsed: dict[str, str] = {}
    for entry in items or []:
        key = str(entry.get("key") or "").strip()
        if not key:
            continue
        if "stringValue" in entry:
            parsed[key] = str(entry["stringValue"])
        elif isinstance(entry.get("value"), dict) and "stringValue" in entry["value"]:
            parsed[key] = str(entry["value"]["stringValue"])
        elif "numericValue" in entry:
            parsed[key] = str(entry["numericValue"])
    return parsed


class GeminiVectorStoreClient:
    """Client for Gemini File Search Store ingestion, delta sync, and RAG queries."""

    def __init__(
        self,
        api_key: str,
        store_name: str = "support-kb",
        model: str = "gemini-2.5-flash",
        system_prompt: Optional[str] = None,
        chunking_config: Optional[ChunkingConfig] = None,
        api_base_url: str = "https://generativelanguage.googleapis.com",
        timeout: float = 60.0,
        poll_interval_seconds: float = 2.0,
        max_poll_attempts: int = 60,
        transport: Optional[httpx.BaseTransport] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        cleaned_key = (api_key or "").strip()
        if not cleaned_key:
            raise ValueError("api_key must be non-empty.")
        cleaned_store = (store_name or "").strip()
        if not cleaned_store:
            raise ValueError("store_name must be non-empty.")

        self.api_key = cleaned_key
        self.store_name = cleaned_store
        self.model = model
        self.system_prompt = system_prompt or build_system_prompt()
        self.chunking_config = chunking_config or ChunkingConfig()
        self.api_base_url = api_base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval_seconds = poll_interval_seconds
        self.max_poll_attempts = max_poll_attempts
        self.transport = transport
        self._sleep = sleep_fn or time.sleep
        self._store_resource_name: Optional[str] = None

    def _build_client(self) -> httpx.Client:
        return httpx.Client(
            timeout=self.timeout,
            transport=self.transport,
            headers={"x-goog-api-key": self.api_key},
        )

    def _request_json(
        self,
        client: httpx.Client,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError as exc:
            raise VectorStoreError(f"Transport error calling {method} {url}: {exc}") from exc

        if response.status_code >= 400:
            raise VectorStoreError(
                f"Gemini API error {response.status_code} on {method} {url}: {response.text[:300]}"
            )

        if not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as exc:
            raise VectorStoreError(f"Invalid JSON response from {method} {url}: {exc}") from exc
        if not isinstance(data, dict):
            raise VectorStoreError(f"Expected JSON object from {method} {url}")
        return data

    def ensure_store(self) -> str:
        """Return existing File Search Store resource name or create a new one."""
        if self._store_resource_name:
            return self._store_resource_name

        with self._build_client() as client:
            page_token: Optional[str] = None
            while True:
                params = {"pageSize": 20}
                if page_token:
                    params["pageToken"] = page_token
                payload = self._request_json(
                    client,
                    "GET",
                    f"{self.api_base_url}/v1beta/fileSearchStores",
                    params=params,
                )
                for store in payload.get("fileSearchStores") or []:
                    if store.get("displayName") == self.store_name and store.get("name"):
                        self._store_resource_name = str(store["name"])
                        return self._store_resource_name
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

            created = self._request_json(
                client,
                "POST",
                f"{self.api_base_url}/v1beta/fileSearchStores",
                json={"displayName": self.store_name},
            )
            name = str(created.get("name") or "").strip()
            if not name:
                raise VectorStoreError("File Search Store creation returned no resource name.")
            self._store_resource_name = name
            return name

    def list_remote_state(self) -> dict[int, SyncStateEntry]:
        """Reconstruct article sync state from remote File Search Store document metadata."""
        store_resource = self.ensure_store()
        entries: dict[int, SyncStateEntry] = {}

        with self._build_client() as client:
            page_token: Optional[str] = None
            while True:
                params = {"pageSize": 20}
                if page_token:
                    params["pageToken"] = page_token
                payload = self._request_json(
                    client,
                    "GET",
                    f"{self.api_base_url}/v1beta/{store_resource}/documents",
                    params=params,
                )
                for doc in payload.get("documents") or []:
                    doc_name = str(doc.get("name") or "").strip()
                    meta = _extract_custom_metadata(doc.get("customMetadata") or [])
                    raw_id = meta.get("article_id")
                    if not raw_id or not raw_id.isdigit():
                        continue
                    article_id = int(raw_id)
                    entries[article_id] = SyncStateEntry(
                        article_id=article_id,
                        slug=meta.get("slug", f"article-{article_id}"),
                        content_hash=meta.get("content_hash", ""),
                        updated_at=meta.get("updated_at", ""),
                        html_url=meta.get("html_url", ""),
                        remote_doc_name=doc_name or None,
                    )
                page_token = payload.get("nextPageToken")
                if not page_token:
                    break

        return entries

    def _upload_temp_file(self, client: httpx.Client, article: NormalizedArticle) -> str:
        content_bytes = article.markdown.encode("utf-8")
        try:
            start_resp = client.post(
                f"{self.api_base_url}/upload/v1beta/files",
                headers={
                    "X-Goog-Upload-Protocol": "resumable",
                    "X-Goog-Upload-Command": "start",
                    "X-Goog-Upload-Header-Content-Length": str(len(content_bytes)),
                    "X-Goog-Upload-Header-Content-Type": "text/markdown",
                    "Content-Type": "application/json",
                },
                json={"file": {"displayName": f"{article.slug}.md"}},
            )
        except httpx.TransportError as exc:
            raise VectorStoreError(f"Transport error starting file upload: {exc}") from exc

        if start_resp.status_code >= 400:
            raise VectorStoreError(
                f"Failed starting resumable upload ({start_resp.status_code}): {start_resp.text[:300]}"
            )

        upload_url = start_resp.headers.get("x-goog-upload-url")
        if not upload_url:
            raise VectorStoreError("Missing x-goog-upload-url header from Gemini Files API.")

        try:
            finalize_resp = client.post(
                upload_url,
                headers={
                    "X-Goog-Upload-Offset": "0",
                    "X-Goog-Upload-Command": "upload, finalize",
                    "Content-Type": "text/markdown",
                },
                content=content_bytes,
            )
        except httpx.TransportError as exc:
            raise VectorStoreError(f"Transport error finalizing file upload: {exc}") from exc

        if finalize_resp.status_code >= 400:
            raise VectorStoreError(
                f"Failed finalizing file upload ({finalize_resp.status_code}): {finalize_resp.text[:300]}"
            )

        file_name = str(finalize_resp.json().get("file", {}).get("name") or "").strip()
        if not file_name:
            raise VectorStoreError("Files API upload returned no file resource name.")
        return file_name

    def _import_file(
        self,
        client: httpx.Client,
        store_resource: str,
        file_name: str,
        article: NormalizedArticle,
    ) -> dict[str, Any]:
        body = {
            "fileName": file_name,
            "chunkingConfig": self.chunking_config.to_gemini_payload(),
            "customMetadata": [
                {"key": "article_id", "stringValue": str(article.id)},
                {"key": "slug", "stringValue": article.slug},
                {"key": "content_hash", "stringValue": article.content_hash},
                {"key": "updated_at", "stringValue": article.updated_at},
                {"key": "html_url", "stringValue": article.html_url},
            ],
        }
        return self._request_json(
            client,
            "POST",
            f"{self.api_base_url}/v1beta/{store_resource}:importFile",
            json=body,
        )

    def _poll_operation(self, client: httpx.Client, operation: dict[str, Any]) -> dict[str, Any]:
        current = operation
        for _ in range(self.max_poll_attempts):
            if current.get("done"):
                if current.get("error"):
                    raise VectorStoreError(f"Indexing operation failed: {current['error']}")
                return current

            op_name = str(current.get("name") or "").strip()
            if not op_name:
                raise VectorStoreError("Long-running operation missing 'name' field.")

            self._sleep(self.poll_interval_seconds)
            current = self._request_json(
                client,
                "GET",
                f"{self.api_base_url}/v1beta/{op_name}",
            )

        if current.get("done"):
            if current.get("error"):
                raise VectorStoreError(f"Indexing operation failed: {current['error']}")
            return current

        raise VectorStoreError(
            f"Indexing operation timed out after {self.max_poll_attempts} attempts."
        )

    def _delete_temp_file(self, client: httpx.Client, file_name: str) -> None:
        try:
            resp = client.delete(f"{self.api_base_url}/v1beta/{file_name}")
            if resp.status_code >= 400 and resp.status_code != 404:
                logger.debug("Temp file cleanup %s returned %s", file_name, resp.status_code)
        except httpx.TransportError as exc:
            logger.debug("Temp file cleanup %s failed: %s", file_name, exc)

    def delete_document(self, document_name: str) -> None:
        """Delete a document (and its chunks) from the File Search Store."""
        with self._build_client() as client:
            try:
                resp = client.delete(
                    f"{self.api_base_url}/v1beta/{document_name}",
                    params={"force": "true"},
                )
            except httpx.TransportError as exc:
                raise VectorStoreError(f"Transport error deleting {document_name}: {exc}") from exc

            if resp.status_code == 404:
                return
            if resp.status_code >= 400:
                raise VectorStoreError(
                    f"Failed deleting document {document_name} ({resp.status_code}): {resp.text[:300]}"
                )

    def delete_store(self, store_resource: Optional[str] = None, force: bool = True) -> None:
        """Delete a File Search Store (used primarily in test cleanup)."""
        target = store_resource or self._store_resource_name
        if not target:
            return
        with self._build_client() as client:
            resp = client.delete(
                f"{self.api_base_url}/v1beta/{target}",
                params={"force": "true" if force else "false"},
            )
            if resp.status_code >= 400 and resp.status_code != 404:
                raise VectorStoreError(
                    f"Failed deleting store {target} ({resp.status_code}): {resp.text[:300]}"
                )
        if target == self._store_resource_name:
            self._store_resource_name = None

    def sync_delta(
        self,
        delta: DeltaClassification,
        existing_doc_map: Optional[dict[int, str]] = None,
    ) -> UploadResult:
        """Upload added and updated articles to the File Search Store."""
        if not delta.added and not delta.updated:
            logger.info("No delta changes to upload.")
            return UploadResult()

        store_resource = self.ensure_store()
        result = UploadResult()
        doc_map = existing_doc_map or {}

        work_items: list[tuple[str, NormalizedArticle]] = [
            ("updated", article) for article in delta.updated
        ] + [("added", article) for article in delta.added]

        with self._build_client() as client:
            for change_kind, article in work_items:
                try:
                    if change_kind == "updated" and article.id in doc_map:
                        self.delete_document(doc_map[article.id])

                    temp_file = self._upload_temp_file(client, article)
                    try:
                        op = self._import_file(client, store_resource, temp_file, article)
                        completed = self._poll_operation(client, op)
                    finally:
                        self._delete_temp_file(client, temp_file)

                    doc_name = str(
                        completed.get("response", {}).get("documentName")
                        or f"{store_resource}/documents/{article.slug}"
                    )
                    result.remote_doc_map[article.id] = doc_name
                    result.files_uploaded += 1
                    result.chunks_embedded += estimate_chunk_count(
                        article.markdown, self.chunking_config
                    )
                except Exception as exc:
                    logger.error(
                        "Failed uploading %s article %d (%s): %s",
                        change_kind,
                        article.id,
                        article.slug,
                        exc,
                    )
                    result.failed_ids.append(article.id)

        logger.info(
            "Embedding summary: files_embedded=%d chunks_embedded=%d failed=%d",
            result.files_uploaded,
            result.chunks_embedded,
            len(result.failed_ids),
        )
        return result

    def query(self, question: str) -> str:
        """Query the File Search Store using the configured assistant system prompt."""
        store_resource = self.ensure_store()
        payload = {
            "systemInstruction": {"parts": [{"text": self.system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": question}]}],
            "tools": [{"fileSearch": {"fileSearchStoreNames": [store_resource]}}],
        }
        with self._build_client() as client:
            data = self._request_json(
                client,
                "POST",
                f"{self.api_base_url}/v1beta/models/{self.model}:generateContent",
                json=payload,
            )

        candidates = data.get("candidates") or []
        if not candidates:
            raise VectorStoreError("Gemini generateContent returned no candidates.")
        parts = candidates[0].get("content", {}).get("parts") or []
        text_chunks = [str(p.get("text")) for p in parts if p.get("text")]
        answer = "\n".join(text_chunks).strip()
        if not answer:
            raise VectorStoreError("Gemini generateContent returned empty text.")
        return answer
