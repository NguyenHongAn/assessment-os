from __future__ import annotations

import sys

from src.config import ConfigError, load_settings
from src.logging_config import configure_logging


def main() -> int:
    """Run the one-shot OptiSigns scrape-and-sync job."""
    try:
        settings = load_settings()
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 1

    logger = configure_logging(level=settings.log_level, secrets=[settings.api_key])
    logger.info("Initialized configuration: %r", settings)
    logger.info("Pipeline execution will be wired in Sprint 4.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
