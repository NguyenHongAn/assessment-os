from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Optional

from dotenv import load_dotenv


class ConfigError(ValueError):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    """Application runtime configuration loaded from environment variables."""

    api_key: str
    store_name: str
    gemini_model: str
    zendesk_base_url: str
    zendesk_locale: str
    min_articles: int
    max_articles: Optional[int]
    articles_dir: Path
    state_file: Path
    chunk_max_tokens: int
    chunk_overlap_tokens: int
    log_level: str

    def __repr__(self) -> str:
        return (
            "Settings("
            f"api_key='***REDACTED***', "
            f"store_name={self.store_name!r}, "
            f"gemini_model={self.gemini_model!r}, "
            f"zendesk_base_url={self.zendesk_base_url!r}, "
            f"zendesk_locale={self.zendesk_locale!r}, "
            f"min_articles={self.min_articles!r}, "
            f"max_articles={self.max_articles!r}, "
            f"articles_dir={self.articles_dir!r}, "
            f"state_file={self.state_file!r}, "
            f"chunk_max_tokens={self.chunk_max_tokens!r}, "
            f"chunk_overlap_tokens={self.chunk_overlap_tokens!r}, "
            f"log_level={self.log_level!r}"
            ")"
        )


def _parse_int(raw: Optional[str], name: str, default: int) -> int:
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}: {raw!r}") from exc


def _parse_optional_int(raw: Optional[str], name: str) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(raw.strip())
    except ValueError as exc:
        raise ConfigError(f"Invalid integer for {name}: {raw!r}") from exc


def load_settings(
    env: Optional[Mapping[str, str]] = None,
    load_dotenv_file: bool = True,
) -> Settings:
    """Load and validate application settings from environment variables.

    Resolves the Gemini API key from ``API_KEY`` first, falling back to
    ``GEMINI_API_KEY``.
    """
    if env is None:
        if load_dotenv_file:
            load_dotenv(override=False)
        source: Mapping[str, str] = os.environ
    else:
        source = env

    api_key = (source.get("API_KEY") or source.get("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise ConfigError(
            "Missing Gemini API key: set API_KEY or GEMINI_API_KEY in the environment."
        )

    store_name = (
        source.get("GEMINI_FILE_SEARCH_STORE_NAME") or "optisigns-support-kb"
    ).strip()
    gemini_model = (source.get("GEMINI_MODEL") or "gemini-2.5-flash").strip()
    zendesk_base_url = (
        source.get("ZENDESK_BASE_URL") or "https://support.optisigns.com"
    ).strip().rstrip("/")
    zendesk_locale = (source.get("ZENDESK_LOCALE") or "en-us").strip()

    min_articles = _parse_int(source.get("MIN_ARTICLES"), "MIN_ARTICLES", 30)
    if min_articles < 1:
        raise ConfigError("MIN_ARTICLES must be >= 1.")

    max_articles = _parse_optional_int(source.get("MAX_ARTICLES"), "MAX_ARTICLES")
    if max_articles is not None and max_articles < 1:
        raise ConfigError("MAX_ARTICLES must be >= 1 when specified.")

    articles_dir = Path((source.get("ARTICLES_DIR") or "data/articles").strip())
    state_file = Path((source.get("STATE_FILE") or "data/state.json").strip())

    chunk_max_tokens = _parse_int(
        source.get("CHUNK_MAX_TOKENS"), "CHUNK_MAX_TOKENS", 512
    )
    if chunk_max_tokens <= 0:
        raise ConfigError("CHUNK_MAX_TOKENS must be > 0.")

    chunk_overlap_tokens = _parse_int(
        source.get("CHUNK_OVERLAP_TOKENS"), "CHUNK_OVERLAP_TOKENS", 64
    )
    if chunk_overlap_tokens < 0 or chunk_overlap_tokens >= chunk_max_tokens:
        raise ConfigError(
            "CHUNK_OVERLAP_TOKENS must be >= 0 and < CHUNK_MAX_TOKENS."
        )

    log_level = (source.get("LOG_LEVEL") or "INFO").strip().upper()

    return Settings(
        api_key=api_key,
        store_name=store_name,
        gemini_model=gemini_model,
        zendesk_base_url=zendesk_base_url,
        zendesk_locale=zendesk_locale,
        min_articles=min_articles,
        max_articles=max_articles,
        articles_dir=articles_dir,
        state_file=state_file,
        chunk_max_tokens=chunk_max_tokens,
        chunk_overlap_tokens=chunk_overlap_tokens,
        log_level=log_level,
    )
