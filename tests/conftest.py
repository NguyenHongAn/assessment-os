from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def zendesk_sample_payload() -> dict[str, Any]:
    """Load the sample Zendesk Help Center API JSON payload."""
    with (FIXTURES_DIR / "zendesk_sample.json").open("r", encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """Create a temporary data directory for articles and state files."""
    data_dir = tmp_path / "data"
    (data_dir / "articles").mkdir(parents=True, exist_ok=True)
    return data_dir


@pytest.fixture
def valid_env(tmp_data_dir: Path) -> dict[str, str]:
    """Return a valid minimal environment mapping for load_settings."""
    return {
        "API_KEY": "test-dummy-api-key-12345",
        "ZENDESK_BASE_URL": "https://support.example.com",
        "GEMINI_FILE_SEARCH_STORE_NAME": "test-store",
        "GEMINI_MODEL": "gemini-2.5-flash",
        "ARTICLES_DIR": str(tmp_data_dir / "articles"),
        "STATE_FILE": str(tmp_data_dir / "state.json"),
    }
