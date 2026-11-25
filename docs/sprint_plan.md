# Sprint Plan — OptiSigns Support Bot (`assessment-os`)

**Stack Locked In**:
- **AI Provider**: Google Gemini (`google-genai` File Search Store + AI Studio)
- **Daily Job Hosting**: DigitalOcean (Dockerized one-shot job)

---

## Sprint 1 — Architecture, Configuration & Test Harness Foundation
- **Goal**: Establish a clean, modular Python project layout, secure environment configuration, and the `pytest` component/integration test harness.
- **Feature Requirements**:
  - Package layout (`src/scraper.py`, `src/converter.py`, `src/delta.py`, `src/vector_store.py`, `src/config.py`, `src/models.py`, `src/logging_config.py`, `main.py`).
  - `.env.sample` with documented env vars (no hard-coded secrets).
  - `requirements.txt`, `requirements-dev.txt`, `pyproject.toml` dependencies and `pytest` configuration.
  - `tests/` structure with shared fixtures (`tests/component/`, `tests/integration/`, `tests/fixtures/`).
- **Tests Covered**: `TC-C11`, `TC-C12` (prompt contract), env bootstrap integration test.
- **End-of-Sprint Summary**: Repo has clean module boundaries, `.env.sample`, installed `.venv` dependencies, and a green baseline `pytest` suite.
- **Next Sprint Will Do**: Build the Zendesk Help Center scraper and HTML-to-Markdown normalizer to pull and clean `>= 30` OptiSigns support articles.

---

## Sprint 2 — Scrape & Clean Markdown Pipeline (25 pts)
- **Goal**: Pull `>= 30` articles from `support.optisigns.com` via the Zendesk Help Center API and save clean, citation-ready `<slug>.md` files.
- **Feature Requirements**:
  - Zendesk API client (`GET /api/v2/help_center/en-us/articles.json`) with pagination, draft filtering, and retry/backoff.
  - HTML cleaner stripping navigation, ads, scripts, styles, and boilerplate while preserving headings, fenced code blocks, and relative links.
  - Deterministic `<slug>.md` output including `Article URL:` metadata so downstream RAG citations are accurate.
- **Tests Covered**: `TC-C01`–`TC-C05`, `TC-I01`.
- **End-of-Sprint Summary**: Verified `>= 30` clean `.md` articles generated locally, zero nav/script noise, relative links/code blocks intact, and all scraper/converter tests passing.
- **Next Sprint Will Do**: Implement content-hash delta detection, chunking/embedding telemetry, programmatic Gemini File Search Store API upload, and OptiBot verification.

---

## Sprint 3 — Delta Engine, Gemini File Search Upload & OptiBot Setup (20 pts)
- **Goal**: Programmatically upload Markdown docs to the Gemini File Search Store via API with delta-only updates, log files/chunks embedded, and verify OptiBot answers with citations.
- **Feature Requirements**:
  - Delta detection engine comparing SHA-256 content hash & `updated_at` against persisted state.
  - Documented chunking strategy + logging of `files_embedded`, `chunks_embedded`, `added`, `updated`, and `skipped`.
  - Programmatic `google-genai` File Search Store uploader supporting upload, update-replace, and async indexing polling.
  - Configure OptiBot with the verbatim system prompt; run the sanity check (`"How do I add a YouTube video?"`) and capture the screenshot with `Article URL:` citations.
- **Tests Covered**: `TC-C06`–`TC-C12`, `TC-I02`, `TC-I04`.
- **End-of-Sprint Summary**: Working API-only upload pipeline with verified idempotent delta updates, embedding count logs, passing component/integration tests, and verified OptiBot screenshot.
- **Next Sprint Will Do**: Wrap everything into the one-shot `main.py` runner, Dockerize it, and deploy the scheduled daily job on DigitalOcean with accessible logs.

---

## Sprint 4 — One-Shot Job (`main.py`), Dockerization & DigitalOcean Daily Job (15 pts)
- **Goal**: Package the scraper-uploader into a `Dockerfile` that runs once and exits `0`, and schedule it daily on DigitalOcean with viewable job logs/artifacts.
- **Feature Requirements**:
  - `main.py` entry point wiring scrape → normalize → delta → upload → summary logging (`added`, `updated`, `skipped`, `files`, `chunks`) and clean exit `0`.
  - `Dockerfile` (Python slim image) verified with `docker run -e API_KEY=... <image>` exiting `0`.
  - Daily cron deployment on DigitalOcean with a shareable link to job logs / latest run artifact.
- **Tests Covered**: `TC-I03`, `TC-I05`.
- **End-of-Sprint Summary**: Containerized one-shot job passing locally and running on a daily DigitalOcean schedule with a verified log URL showing delta counts.
- **Next Sprint Will Do**: Write the concise `<= 1 page` `README.md`, embed the screenshot and job log link, run full test & rubric audit, and push clean commits.

---

## Sprint 5 — Documentation, Final Verification & Delivery (10 pts + 5 Bonus pts)
- **Goal**: Finalize deliverables, ensure all automated tests pass, and audit every item against the 70+5 pt grading rubric.
- **Feature Requirements**:
  - Concise `README.md` (`<= 1 page`) covering: setup, chunking strategy, local run command, Docker run command, daily job logs link, and OptiBot screenshot.
  - Security & hygiene check: zero hard-coded keys, clean `.env.sample`, cryptic repo name (`assessment-os`), clear commit history.
  - Full `pytest` suite covering component + integration tests for the +5 bonus points.
- **End-of-Sprint Summary**: All deliverables complete, tests passing, repo pushed to `origin`, ready for submission.
- **Next Sprint Will Do**: None — project complete.
