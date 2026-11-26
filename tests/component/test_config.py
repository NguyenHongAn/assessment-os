from __future__ import annotations

import io
import logging

import pytest

from src.config import ConfigError, load_settings
from src.logging_config import SecretRedactingFilter, configure_logging
from src.models import build_system_prompt


def test_tc_c11_missing_api_key_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Missing Gemini API key"):
        load_settings(
            env={"ZENDESK_BASE_URL": "https://support.example.com"},
            load_dotenv_file=False,
        )


def test_tc_c11_whitespace_api_key_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="Missing Gemini API key"):
        load_settings(
            env={
                "API_KEY": "   ",
                "GEMINI_API_KEY": "\t\n",
                "ZENDESK_BASE_URL": "https://support.example.com",
            },
            load_dotenv_file=False,
        )


def test_tc_c11_missing_or_invalid_zendesk_url_raises_config_error() -> None:
    with pytest.raises(ConfigError, match="ZENDESK_BASE_URL"):
        load_settings(env={"API_KEY": "k"}, load_dotenv_file=False)

    with pytest.raises(ConfigError, match="ZENDESK_BASE_URL"):
        load_settings(
            env={"API_KEY": "k", "ZENDESK_BASE_URL": "ftp://support.example.com"},
            load_dotenv_file=False,
        )


def test_tc_c11_api_key_precedence_and_fallback() -> None:
    settings_primary = load_settings(
        env={
            "API_KEY": "primary-key",
            "GEMINI_API_KEY": "fallback-key",
            "ZENDESK_BASE_URL": "https://support.example.com/",
        },
        load_dotenv_file=False,
    )
    assert settings_primary.api_key == "primary-key"
    assert settings_primary.zendesk_base_url == "https://support.example.com"

    settings_fallback = load_settings(
        env={
            "GEMINI_API_KEY": "fallback-key",
            "ZENDESK_BASE_URL": "https://support.example.com",
        },
        load_dotenv_file=False,
    )
    assert settings_fallback.api_key == "fallback-key"


@pytest.mark.parametrize(
    "bad_env",
    [
        {"API_KEY": "k", "ZENDESK_BASE_URL": "https://support.example.com", "MIN_ARTICLES": "0"},
        {"API_KEY": "k", "ZENDESK_BASE_URL": "https://support.example.com", "MIN_ARTICLES": "abc"},
        {"API_KEY": "k", "ZENDESK_BASE_URL": "https://support.example.com", "MAX_ARTICLES": "0"},
        {"API_KEY": "k", "ZENDESK_BASE_URL": "https://support.example.com", "CHUNK_MAX_TOKENS": "0"},
        {
            "API_KEY": "k",
            "ZENDESK_BASE_URL": "https://support.example.com",
            "CHUNK_MAX_TOKENS": "100",
            "CHUNK_OVERLAP_TOKENS": "100",
        },
        {
            "API_KEY": "k",
            "ZENDESK_BASE_URL": "https://support.example.com",
            "CHUNK_MAX_TOKENS": "100",
            "CHUNK_OVERLAP_TOKENS": "-1",
        },
    ],
)
def test_tc_c11_invalid_numeric_configs_raise_config_error(bad_env: dict[str, str]) -> None:
    with pytest.raises(ConfigError):
        load_settings(env=bad_env, load_dotenv_file=False)


def test_tc_c11_repr_and_logging_redact_secrets() -> None:
    secret = "super-secret-gemini-key-999"
    settings = load_settings(
        env={"API_KEY": secret, "ZENDESK_BASE_URL": "https://support.example.com"},
        load_dotenv_file=False,
    )

    assert secret not in repr(settings)
    assert "***REDACTED***" in repr(settings)

    stream = io.StringIO()
    logger = configure_logging(level="INFO", secrets=[secret])
    logger.handlers[0].stream = stream
    logger.info("Using key %s for store %s", secret, "test-store")
    logger.info(f"Direct interpolated {secret}")

    output = stream.getvalue()
    assert secret not in output
    assert "***REDACTED***" in output


def test_tc_c11_secret_redacting_filter_handles_dict_args() -> None:
    secret = "dict-secret-value"
    flt = SecretRedactingFilter(secrets=[secret])
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="Payload %(key)s",
        args=({"key": secret},),
        exc_info=None,
    )
    assert isinstance(record.args, dict)
    assert flt.filter(record) is True
    assert record.args["key"] == "***REDACTED***"


def test_tc_c12_system_prompt_template_and_override() -> None:
    default_prompt = build_system_prompt()
    assert default_prompt == (
        "You are SupportBot, the customer-support bot for Example.com.\n"
        "• Tone: helpful, factual, concise.\n"
        "• Only answer using the uploaded docs.\n"
        "• Max 5 bullet points; else link to the doc.\n"
        '• Cite up to 3 "Article URL:" lines per reply.'
    )

    custom_persona = build_system_prompt(assistant_name="HelpBot", brand_name="Acme.io")
    assert "You are HelpBot, the customer-support bot for Acme.io." in custom_persona

    overridden = build_system_prompt(custom_prompt="Custom prompt line")
    assert overridden == "Custom prompt line"
