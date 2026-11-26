from __future__ import annotations

import argparse
import sys
from typing import Optional

from src.chunking import ChunkingConfig
from src.config import ConfigError, Settings, load_settings
from src.converter import HtmlToMarkdownConverter
from src.delta import JsonStateStore, StateError
from src.logging_config import configure_logging
from src.pipeline import SyncPipeline
from src.scraper import ScraperError, ZendeskScraper
from src.vector_store import GeminiVectorStoreClient, VectorStoreError


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI flags for the one-shot sync job."""
    parser = argparse.ArgumentParser(
        description="One-shot Help Center scraper and Gemini File Search sync job."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Scrape, convert, and compute delta without uploading to Gemini or writing state.",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Query the configured Gemini File Search Store and print the answer.",
    )
    return parser.parse_args(argv)


def build_vector_store(settings: Settings) -> GeminiVectorStoreClient:
    """Instantiate the Gemini File Search Store client from settings."""
    return GeminiVectorStoreClient(
        api_key=settings.api_key,
        store_name=settings.store_name,
        model=settings.gemini_model,
        system_prompt=settings.system_prompt,
        chunking_config=ChunkingConfig(
            max_tokens=settings.chunk_max_tokens,
            overlap_tokens=settings.chunk_overlap_tokens,
        ),
    )


def build_pipeline(settings: Settings) -> SyncPipeline:
    """Wire scraper, converter, state store, and vector store into SyncPipeline."""
    source = ZendeskScraper(
        base_url=settings.zendesk_base_url,
        locale=settings.zendesk_locale,
    )
    converter = HtmlToMarkdownConverter()
    state_store = JsonStateStore(settings.state_file)
    vector_store = build_vector_store(settings)
    return SyncPipeline(
        source=source,
        converter=converter,
        state_store=state_store,
        vector_store=vector_store,
        articles_dir=settings.articles_dir,
        min_articles=settings.min_articles,
        max_articles=settings.max_articles,
        summary_file=settings.summary_file,
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Run the one-shot scrape-and-sync job."""
    args = parse_args(argv)
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(level=settings.log_level, secrets=[settings.api_key])

    try:
        if args.query:
            answer = build_vector_store(settings).query(args.query)
            print(answer)
            return 0

        summary = build_pipeline(settings).run(dry_run=args.dry_run)
        return 0 if summary.failed == 0 else 1
    except (ScraperError, VectorStoreError, StateError) as exc:
        logger.error("Job failed: %s", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
