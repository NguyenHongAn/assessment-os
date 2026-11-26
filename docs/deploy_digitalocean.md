# Deploying the Daily Sync Job on DigitalOcean App Platform

This repository includes a `Dockerfile` and a DigitalOcean App Platform spec at [`.do/app.yaml`](../.do/app.yaml) configured as a `SCHEDULED` job (`0 2 * * *` UTC).

Because the container is ephemeral, `SyncPipeline` automatically hydrates previous article hashes and document IDs from the Gemini File Search Store's `customMetadata` (`list_remote_state()`) on startup, ensuring daily runs only upload **new or updated** articles.

---

## Option A — Deploy via `doctl` CLI

1. Install and authenticate `doctl`:
   ```bash
   doctl auth init
   ```
2. Create the scheduled job app from the spec:
   ```bash
   doctl apps create --spec .do/app.yaml
   ```
3. In the DigitalOcean Control Panel (**Apps → `kb-daily-sync` → Settings → `kb-sync-job` → Environment Variables**), set:
   - `API_KEY` (Secret): your Gemini API key
   - `ZENDESK_BASE_URL`: your target Help Center URL
   - `SYSTEM_PROMPT`: your assistant system prompt (single-line `\n`-escaped or multi-line)
   - `MAX_ARTICLES` (optional): e.g. `45`
4. Trigger an immediate manual run from **Apps → `kb-daily-sync` → `kb-sync-job` → Run Now** (or `doctl apps create-deployment <app-id>`).

---

## Option B — Deploy via DigitalOcean Web UI

1. Go to **DigitalOcean → App Platform → Create App → GitHub**.
2. Select `NguyenHongAn/assessment-os` (`main` branch).
3. DigitalOcean will detect `.do/app.yaml` / `Dockerfile`. Ensure the component type is **Job (Scheduled)** with cron `0 2 * * *` (UTC).
4. Add `API_KEY` (encrypted), `ZENDESK_BASE_URL`, and `SYSTEM_PROMPT` under **Environment Variables**.
5. Deploy and click **Run Now** to verify the first execution.

---

## Viewing & Sharing Job Logs

1. Open **DigitalOcean → Apps → `kb-daily-sync` → Activity / Runtime Logs** for `kb-sync-job`.
2. Verify the summary line in the logs:
   ```text
   Run summary: added=... updated=... skipped=... failed=0 files_embedded=... chunks_embedded=...
   ```
3. Copy the job run log URL (or export/save the run log output) and link it in `README.md`.
