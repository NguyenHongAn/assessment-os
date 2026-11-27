# Deploying the Daily Sync Job with GitHub Actions

This repository runs the containerized one-shot sync job daily (`0 2 * * *` UTC) via [`.github/workflows/daily-sync.yml`](../.github/workflows/daily-sync.yml).

Because each GitHub Actions runner is ephemeral, `SyncPipeline` hydrates prior article hashes and document IDs from the Gemini File Search Store's `customMetadata` (`list_remote_state()`) on startup, ensuring daily runs only upload **new or updated** articles.

---

## 1. Configure Repository Secrets

In GitHub, open **Settings → Secrets and variables → Actions → Repository secrets** and add:

- `API_KEY`: Your Gemini API key
- `ZENDESK_BASE_URL`: Your target Help Center URL (e.g. `https://support.example.com`)
- `SYSTEM_PROMPT`: Your assistant system prompt (multi-line or `\n`-escaped)

### Optional Repository Variables (**Variables** tab)

- `GEMINI_FILE_SEARCH_STORE_NAME` (default: `support-kb`)
- `GEMINI_MODEL` (default: `gemini-3.5-flash-lite`)
- `MIN_ARTICLES` (default: `30`)
- `MAX_ARTICLES` (default: unset / all articles)
- `CHUNK_MAX_TOKENS` (default: `512`)
- `CHUNK_OVERLAP_TOKENS` (default: `64`)
- `LOG_LEVEL` (default: `INFO`)

---

## 2. Trigger & Verify a Run

1. Push to `main`:
   ```bash
   git push origin main
   ```
2. Open **Actions → Daily KB Sync → Run workflow** to trigger an immediate run (set `dry_run: true` for a safe preview or `false` for a full sync).
3. Each run logs `Run summary: added=... updated=... skipped=... failed=0 files_embedded=... chunks_embedded=...`, renders a **Daily KB Sync Summary** table on the run page, and uploads `last-run-summary` (`data/last_run.json`) as an artifact.

---

## 3. Shareable Logs Link

On a public repository, anyone can view the daily run history, stdout logs, and Job Summary without logging in at:

`https://github.com/NguyenHongAn/assessment-os/actions/workflows/daily-sync.yml`
