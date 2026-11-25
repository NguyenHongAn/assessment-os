from __future__ import annotations

import logging
import sys
from typing import Optional

REDACTED = "***REDACTED***"


class SecretRedactingFilter(logging.Filter):
    """Logging filter that scrubs configured secret strings from log records."""

    def __init__(self, secrets: Optional[list[str]] = None) -> None:
        super().__init__()
        self._secrets = [s for s in (secrets or []) if s]

    def _redact(self, text: str) -> str:
        for secret in self._secrets:
            if secret in text:
                text = text.replace(secret, REDACTED)
        return text

    def filter(self, record: logging.LogRecord) -> bool:
        if self._secrets:
            if isinstance(record.msg, str):
                record.msg = self._redact(record.msg)
            if record.args:
                if isinstance(record.args, tuple):
                    record.args = tuple(
                        self._redact(arg) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
                elif isinstance(record.args, dict):
                    record.args = {
                        k: self._redact(v) if isinstance(v, str) else v
                        for k, v in record.args.items()
                    }
        return True


def configure_logging(
    level: str = "INFO",
    secrets: Optional[list[str]] = None,
) -> logging.Logger:
    """Configure and return the application logger with secret redaction."""
    logger = logging.getLogger("optisigns_sync")
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    logger.setLevel(numeric_level)
    logger.propagate = False

    logger.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(numeric_level)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    handler.addFilter(SecretRedactingFilter(secrets=secrets))
    logger.addHandler(handler)
    return logger
