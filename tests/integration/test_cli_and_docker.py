from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import main as cli_main
from src.models import RunSummary


def test_tc_i03_cli_main_success_and_logging(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("API_KEY", "dummy-cli-key-123")
    monkeypatch.setenv("ZENDESK_BASE_URL", "https://support.example.com")
    monkeypatch.setenv("ARTICLES_DIR", str(tmp_path / "articles"))
    monkeypatch.setenv("STATE_FILE", str(tmp_path / "state.json"))
    monkeypatch.setenv("SUMMARY_FILE", str(tmp_path / "last_run.json"))

    class _DummyPipeline:
        def run(self, dry_run: bool = False) -> RunSummary:
            assert dry_run is False
            return RunSummary(
                added=30,
                updated=0,
                skipped=0,
                failed=0,
                files_embedded=30,
                chunks_embedded=45,
            )

    monkeypatch.setattr(cli_main, "build_pipeline", lambda settings: _DummyPipeline())
    exit_code = cli_main.main([])
    assert exit_code == 0

    class _FailingPipeline:
        def run(self, dry_run: bool = False) -> RunSummary:
            return RunSummary(added=2, failed=1, files_embedded=1, chunks_embedded=2)

    monkeypatch.setattr(cli_main, "build_pipeline", lambda settings: _FailingPipeline())
    assert cli_main.main([]) == 1

    class _DummyStore:
        def query(self, question: str) -> str:
            return f"Answer for: {question}\nArticle URL: https://support.example.com/1"

    monkeypatch.setattr(cli_main, "build_vector_store", lambda settings: _DummyStore())
    assert cli_main.main(["--query", "How do I start?"]) == 0
    captured = capsys.readouterr()
    assert "Article URL: https://support.example.com/1" in captured.out


def test_tc_i03_cli_missing_api_key_returns_nonzero(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.delenv("API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    real_load_settings = cli_main.load_settings
    monkeypatch.setattr(
        cli_main,
        "load_settings",
        lambda: real_load_settings(env={}, load_dotenv_file=False),
    )

    exit_code = cli_main.main([])
    assert exit_code == 1
    assert "Configuration error" in capsys.readouterr().err


def test_tc_i05_docker_and_github_actions_workflow() -> None:
    repo_root = Path(__file__).resolve().parents[2]

    dockerfile = (repo_root / "Dockerfile").read_text(encoding="utf-8")
    assert "FROM python:3.11-slim AS builder" in dockerfile
    assert "FROM python:3.11-slim AS runtime" in dockerfile
    assert "COPY --from=builder" in dockerfile
    assert 'ENTRYPOINT ["python", "main.py"]' in dockerfile
    assert "USER appuser" in dockerfile

    dockerignore = (repo_root / ".dockerignore").read_text(encoding="utf-8")
    assert ".env" in dockerignore
    assert ".venv" in dockerignore
    assert "data" in dockerignore

    workflow = (repo_root / ".github" / "workflows" / "daily-sync.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "0 2 * * *"' in workflow
    assert "workflow_dispatch:" in workflow
    assert "docker build" in workflow
    assert "docker run" in workflow
    assert "secrets.API_KEY" in workflow
    assert "SYSTEM_PROMPT: ${{ secrets.SYSTEM_PROMPT }}" in workflow
    assert "-e SYSTEM_PROMPT \\" in workflow
    assert "GITHUB_STEP_SUMMARY" in workflow
    assert "actions/checkout@v6" in workflow
    assert "actions/upload-artifact@v7" in workflow
    assert "if-no-files-found: ignore" in workflow
    assert "hashFiles(" not in workflow
