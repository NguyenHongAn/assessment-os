# Test Cases — Component & Integration

## 1. Component Tests (Isolated, Mocked Network & AI SDK)

| ID | Component | Scenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-C01** | Zendesk Scraper | Paginated fetch across multiple pages (`/api/v2/help_center/en-us/articles.json`) | Follows `next_page` until `null` or target count (`>= 30`) is met; returns normalized article records (`id`, `title`, `slug`, `html_url`, `updated_at`, `body_html`). |
| **TC-C02** | Zendesk Scraper | Filtering & retry behavior | Skips `draft: true` or empty-body articles; retries on HTTP `429`/`5xx` with backoff and fails cleanly after max retries. |
| **TC-C03** | HTML → Markdown Converter | Clean conversion of rich Zendesk HTML | Preserves headings (`#`–`######`), fenced code blocks (` ``` `), lists, and relative links; removes `<nav>`, `<footer>`, `<script>`, `<style>`, ads, and cookie/banner blocks. |
| **TC-C04** | Markdown Writer | File naming & citation metadata | Saves files as `<slug>.md` (sanitized, collision-safe) and embeds canonical `Article URL: <html_url>` header/frontmatter so the Support Assistant can cite exact URLs. |
| **TC-C05** | HTML → Markdown Converter | Malformed or missing HTML edge cases | Handles unclosed tags, broken links, or `None`/blank body gracefully without crashing the batch. |
| **TC-C06** | Delta Detector | First run vs. unchanged vs. modified vs. new articles | Computes deterministic SHA-256 content hash + `updated_at` diff against stored state; classifies each article accurately into `added`, `updated`, or `skipped`. |
| **TC-C07** | Delta Detector | Idempotency on repeat runs | Re-running with identical articles produces `added=0, updated=0, skipped=N` and triggers `0` upload calls. |
| **TC-C08** | Delta Detector | Partial upload failure resilience | If uploading article `k` fails, state records only succeeded articles so the next run retries `k` instead of silently skipping it. |
| **TC-C09** | Chunking & Telemetry | Chunk strategy calculation & logging | Splits/measures Markdown according to the documented chunking config (heading-aware + max-token/overlap limits) and logs exact `files_embedded` and `chunks_embedded` counts. |
| **TC-C10** | Vector Store Client | API upload, update-replace, and indexing poll | Uploads `added` files via API, deletes/replaces old document before re-uploading `updated` files, and polls async indexing until complete. |
| **TC-C11** | Config & Secrets Loader | Missing `API_KEY`, missing `ZENDESK_BASE_URL`, or invalid env vars | Fails fast with a clear error message, exits non-zero, and never prints API keys in stdout/logs. |
| **TC-C12** | Assistant Prompt & Output Validator | Prompt template + override + response contract check | Confirms configured system prompt is built/passed cleanly and validates sample output has `<= 5` bullet points (or doc link) and `1–3` `Article URL:` citations. |

## 2. Integration Tests (Multi-Component & End-to-End)

| ID | Scope | Scenario | Expected Result |
| :--- | :--- | :--- | :--- |
| **TC-I01** | Scraper + Converter + File Storage | Scrape `>= 30` articles from `ZENDESK_BASE_URL` (recorded HTTP fixtures or live env URL) | Writes `>= 30` non-empty `<slug>.md` files; every file contains `Article URL: https://...`, valid Markdown headings, zero raw `<script>`/`<style>`/`<nav>` tags, and preserved relative links/code blocks. |
| **TC-I02** | Full Pipeline + Mocked Vector Store | 3-run lifecycle: (1) Cold start (`N` articles), (2) No changes, (3) 1 edited + 1 new article | Run 1: `added=N, updated=0, skipped=0`; Run 2: `added=0, updated=0, skipped=N` (0 API uploads); Run 3: `added=1, updated=1, skipped=N-1` (only 2 files uploaded, old version replaced). |
| **TC-I03** | CLI Job (`main.py`) | Execute `python main.py` end-to-end as a one-shot job | Completes scrape → normalize → delta → upload, emits structured summary log (`added`, `updated`, `skipped`, `files_embedded`, `chunks_embedded`), and exits with code `0`. |
| **TC-I04** | Live Vector Store + Assistant (`@pytest.mark.live`) | Upload small article subset via real Gemini API and query sample question | Indexing succeeds via API, assistant returns a grounded, concise answer referencing uploaded docs with valid `Article URL:` citation(s), and test cleans up temporary resources. |
| **TC-I05** | Docker Container One-Shot Job | `docker build` + `docker run --rm -e API_KEY=... <image>` | Container executes `main.py` once, prints delta & embedding logs, and exits with status code `0`. |
