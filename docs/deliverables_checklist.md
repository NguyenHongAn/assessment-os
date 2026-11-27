# Deliverables & Requirements Audit (`assessment-os`)

## 1. Deliverables Table Audit

| Deliverable | Must-Have Criteria | Status | Evidence & File Paths |
| :--- | :--- | :--- | :--- |
| **GitHub Repo** | Non-obvious/cryptic repo name; clear commit history; no hard-coded keys; `.env.sample` provided | **DONE** | Repo `NguyenHongAn/assessment-os`; 12 clean commits; [.env.sample](file:///Users/hongan/Documents/interviewAssignment/optisigns/.env.sample); [.gitignore](file:///Users/hongan/Documents/interviewAssignment/optisigns/.gitignore); `0` secret matches (`AIza...`) and `0` brand matches in tracked files. |
| **Dockerfile** | `docker run -e API_KEY=... main.py` runs once and exits `0` | **DONE** | Multi-stage [Dockerfile](file:///Users/hongan/Documents/interviewAssignment/optisigns/Dockerfile) (`builder` → `runtime`, `267MB`, non-root `appuser`, `ENTRYPOINT ["python", "main.py"]`); [.dockerignore](file:///Users/hongan/Documents/interviewAssignment/optisigns/.dockerignore); verified locally with `docker build` + `docker run --dry-run` (exit `0`). |
| **README (`<= 1 page`)** | Setup, chunking strategy, local & Docker run commands, link to daily job logs, assistant screenshot | **DONE** *(needs screenshot file)* | [README.md](file:///Users/hongan/Documents/interviewAssignment/optisigns/README.md) (60 lines); documents setup, `512`/`64` whitespace chunking, local + Docker commands, tests, and GitHub Actions logs link. |
| **Daily Job Logs** | Scheduled once per day; re-scrapes; detects delta; uploads only delta; logs `added`, `updated`, `skipped`; shareable log link | **ACTION NEEDED** *(trigger 1st GH run)* | [`.github/workflows/daily-sync.yml`](file:///Users/hongan/Documents/interviewAssignment/optisigns/.github/workflows/daily-sync.yml) (`cron: "0 2 * * *"`, `workflow_dispatch`, `$GITHUB_STEP_SUMMARY`, `last-run-summary` artifact); setup guide in [docs/deploy_github_actions.md](file:///Users/hongan/Documents/interviewAssignment/optisigns/docs/deploy_github_actions.md). Requires adding GitHub Secrets and triggering one run. |
| **Screenshot** | Assistant answers `"How do I add a YouTube video?"` accurately from uploaded docs with `Article URL:` citations | **ACTION NEEDED** *(save PNG)* | Placeholder path `docs/assets/assistant_screenshot.png` linked in `README.md`; [docs/assets/.gitkeep](file:///Users/hongan/Documents/interviewAssignment/optisigns/docs/assets/.gitkeep) ready. Capture in Google AI Studio (or CLI) and save PNG. |

---

## 2. Full Requirement & Grading Rubric Matrix (70 pts + 5 Bonus)

| Area | Weight | Implemented Behavior | Verification Evidence |
| :--- | :--- | :--- | :--- |
| **1. Scrape & Clean Markdown** | **25 pts** | `ZendeskScraper` paginates `/api/v2/help_center/{locale}/articles.json`, skips drafts/empty bodies, retries `429`/`5xx`. `HtmlToMarkdownConverter` strips `<nav>`, `<footer>`, `<script>`, `<style>`, ads, and cookie banners while preserving headings, fenced code blocks, relative links, and `Article URL:` metadata. | [src/scraper.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/scraper.py), [src/converter.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/converter.py); live test `TC-I01` scraped `>= 30` articles; live sync processed `45` articles cleanly. |
| **2. API Vector Store Upload & Assistant** | **20 pts** | Programmatic `GeminiVectorStoreClient` via Gemini `v1beta` File Search REST API (resumable upload → `:importFile` with `whiteSpaceConfig` + `customMetadata` → LRO polling → temp file cleanup). Logs `files_embedded` and `chunks_embedded`. | [src/vector_store.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/vector_store.py), [src/chunking.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/chunking.py), [src/models.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/models.py); live `TC-I04` passed; live `main.py` embedded `16` new files / `50` chunks (`skipped=29`). |
| **3. Daily Scheduled Job & Delta Sync** | **15 pts** | `SyncPipeline` + `JsonStateStore` + `classify_delta` detect `added`, `updated`, `skipped` via SHA-256 hash + `updated_at`, hydrate state from Gemini `customMetadata` on ephemeral runners, write `data/last_run.json`, and exit `0` via `main.py` inside Docker + GitHub Actions. | [src/pipeline.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/pipeline.py), [src/delta.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/delta.py), [main.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/main.py), [`.github/workflows/daily-sync.yml`](file:///Users/hongan/Documents/interviewAssignment/optisigns/.github/workflows/daily-sync.yml). |
| **4. Code Clarity + README** | **10 pts** | Protocol-driven modular design (`ArticleSource`, `ArticleConverter`, `StateStore`, `VectorStoreClient`), secret-redacting logging, zero brand coupling, concise 60-line `README.md`. | [src/interfaces.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/interfaces.py), [src/utils.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/utils.py), [src/logging_config.py](file:///Users/hongan/Documents/interviewAssignment/optisigns/src/logging_config.py), [README.md](file:///Users/hongan/Documents/interviewAssignment/optisigns/README.md). |
| **5. Automated Tests (Bonus)** | **+5 pts** | Component and integration test suites covering config, scraper, converter, chunking, delta idempotency/partial-failure retry, vector store API, pipeline, CLI, and Docker/CI specs. | `tests/component/` + `tests/integration/`: **43 offline tests passed** (`89%` coverage on `src/`) + **2 live tests passed**. |

---

## 3. Remaining Manual Actions Before Submission

1. **Trigger First GitHub Actions Run (Public Job Logs)**:
   - Open **GitHub → Settings → Secrets and variables → Actions → Repository secrets** and add `API_KEY`, `ZENDESK_BASE_URL`, and `SYSTEM_PROMPT`.
   - Open **Actions → Daily KB Sync → Run workflow** (`https://github.com/NguyenHongAn/assessment-os/actions/workflows/daily-sync.yml`) and run once.
   - Confirm the run turns green and shows the **Daily KB Sync Summary** table + stdout logs (`added`, `updated`, `skipped`, `files_embedded`, `chunks_embedded`).

2. **Capture Assistant Screenshot**:
   - Ensure the standard YouTube guide is indexed (clear `MAX_ARTICLES=` in `.env` / GitHub Variables if capped at `45`, then run `main.py`).
   - Open [Google AI Studio](https://aistudio.google.com), set your verbatim `SYSTEM_PROMPT` in **System Instructions**, select `gemini-3.5-flash-lite`, enable **File Search** in **Tools**, and attach your `support-kb` store.
   - Ask `"How do I add a YouTube video?"`, verify the answer includes `<= 5` bullets and `Article URL:` citations, save the screenshot to `docs/assets/assistant_screenshot.png`, then commit and push:
     ```bash
     git add docs/assets/assistant_screenshot.png
     git commit -m "docs: add assistant sanity check screenshot"
     git push origin main
     ```
