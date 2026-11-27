from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.converter import save_articles
from src.delta import build_updated_state, classify_delta
from src.interfaces import ArticleConverter, ArticleSource, StateStore, VectorStoreClient
from src.logging_config import LOGGER_NAME
from src.models import RunSummary, UploadResult

logger = logging.getLogger(LOGGER_NAME)


def _write_summary_artifact(summary_file: Path, summary: RunSummary) -> None:
    summary_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        **asdict(summary),
    }
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_path_str = tempfile.mkstemp(
        dir=str(summary_file.parent),
        prefix=f".{summary_file.name}.",
        suffix=".tmp",
    )
    tmp_path = Path(tmp_path_str)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp_path, 0o644)
        tmp_path.replace(summary_file)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


class SyncPipeline:
    """Orchestrates scraping, Markdown normalization, delta detection, and vector sync."""

    def __init__(
        self,
        source: ArticleSource,
        converter: ArticleConverter,
        state_store: StateStore,
        vector_store: VectorStoreClient,
        articles_dir: Path,
        min_articles: int = 30,
        max_articles: Optional[int] = None,
        summary_file: Optional[Path] = None,
    ) -> None:
        self.source = source
        self.converter = converter
        self.state_store = state_store
        self.vector_store = vector_store
        self.articles_dir = articles_dir
        self.min_articles = min_articles
        self.max_articles = max_articles
        self.summary_file = summary_file

    def run(self, dry_run: bool = False) -> RunSummary:
        """Execute a single scrape-normalize-delta-upload cycle."""
        raw_articles = self.source.fetch_articles(
            min_articles=self.min_articles,
            max_articles=self.max_articles,
        )
        normalized = save_articles(
            raw_articles,
            output_dir=self.articles_dir,
            converter=self.converter,
        )

        previous_state = self.state_store.load()
        if (
            not previous_state
            and not dry_run
            and hasattr(self.vector_store, "list_remote_state")
        ):
            logger.info("Local state empty; hydrating sync state from remote File Search Store.")
            previous_state = self.vector_store.list_remote_state()

        delta = classify_delta(normalized, previous_state)

        if dry_run:
            logger.info(
                "Dry run complete: would add=%d update=%d skip=%d",
                len(delta.added),
                len(delta.updated),
                len(delta.skipped),
            )
            upload_result = UploadResult()
        else:
            existing_doc_map = {
                article_id: entry.remote_doc_name
                for article_id, entry in previous_state.items()
                if entry.remote_doc_name
            }
            upload_result = self.vector_store.sync_delta(
                delta,
                existing_doc_map=existing_doc_map,
            )
            updated_state = build_updated_state(previous_state, delta, upload_result)
            self.state_store.save(updated_state)

        summary = RunSummary(
            added=len(delta.added),
            updated=len(delta.updated),
            skipped=len(delta.skipped),
            failed=len(upload_result.failed_ids),
            files_embedded=upload_result.files_uploaded,
            chunks_embedded=upload_result.chunks_embedded,
        )
        logger.info(
            "Run summary: added=%d updated=%d skipped=%d failed=%d files_embedded=%d chunks_embedded=%d",
            summary.added,
            summary.updated,
            summary.skipped,
            summary.failed,
            summary.files_embedded,
            summary.chunks_embedded,
        )

        if self.summary_file is not None and not dry_run:
            _write_summary_artifact(self.summary_file, summary)

        return summary
