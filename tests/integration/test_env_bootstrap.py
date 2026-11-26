from __future__ import annotations

import io
from pathlib import Path

from dotenv import dotenv_values

from src.config import load_settings
from src.logging_config import configure_logging


def test_env_sample_bootstrap_and_logging() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    sample_env = dotenv_values(repo_root / ".env.sample")

    env = {k: (v or "") for k, v in sample_env.items()}
    dummy_secret = "dummy-integration-key-xyz"
    env["API_KEY"] = dummy_secret

    settings = load_settings(env=env, load_dotenv_file=False)
    assert settings.api_key == dummy_secret
    assert settings.store_name == "support-kb"
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.zendesk_base_url == "https://support.example.com"
    assert settings.assistant_name == "SupportBot"
    assert settings.brand_name == "Example.com"
    assert settings.min_articles == 30
    assert settings.max_articles is None
    assert settings.chunk_max_tokens == 512
    assert settings.chunk_overlap_tokens == 64

    stream = io.StringIO()
    logger = configure_logging(level=settings.log_level, secrets=[settings.api_key])
    logger.handlers[0].stream = stream
    logger.info("Bootstrapped settings: %r", settings)

    log_output = stream.getvalue()
    assert dummy_secret not in log_output
    assert "***REDACTED***" in log_output
