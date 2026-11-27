# assessment-os

Modular Help Center scraper, HTML-to-Markdown normalizer, and daily Gemini File Search Store delta-sync job.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.sample .env
```

Set `API_KEY` (Gemini API key), `ZENDESK_BASE_URL` (target Help Center), and `SYSTEM_PROMPT` in `.env`.

## Chunking Strategy

- **Gemini `whiteSpaceConfig`**: `CHUNK_MAX_TOKENS=512`, `CHUNK_OVERLAP_TOKENS=64`.
- 512-word chunks keep full support procedures and fenced code blocks intact, while 64-word overlap preserves step context across chunk boundaries.
- Each normalized `<slug>.md` embeds `Article URL: <url>` at the top for grounded citations. `src/chunking.py` mirrors this whitespace window locally to log exact `files_embedded` and `chunks_embedded` counts.

## How to Run Locally

```bash
# One-shot scrape -> normalize -> delta upload (exits 0)
python main.py

# Preview scrape and delta counts without uploading
python main.py --dry-run

# Query the populated Gemini File Search Store
python main.py --query "How do I add a YouTube video?"
```

## Run with Docker

```bash
docker build -t kb-sync .
docker run --rm -e API_KEY=... -e ZENDESK_BASE_URL=... -e SYSTEM_PROMPT="..." kb-sync
```

## Tests

```bash
# Component & integration suite (offline)
pytest -m "not live" --cov=src -v

# Opt-in live Help Center + Gemini File Search integration
pytest -m live -v
```

## Daily Job Deployment & Logs

Scheduled daily (`0 2 * * *` UTC) on GitHub Actions via [`.github/workflows/daily-sync.yml`](.github/workflows/daily-sync.yml) (setup guide: [`docs/deploy_github_actions.md`](docs/deploy_github_actions.md)). On ephemeral runners, `SyncPipeline` hydrates prior hashes and document IDs from Gemini `customMetadata` so only **added** or **updated** articles are uploaded, then publishes a Job Summary table and `last-run-summary` artifact.

- **Daily Job Logs & Run History**: https://github.com/NguyenHongAn/assessment-os/actions/workflows/daily-sync.yml

## Assistant Sanity Check

![Assistant Sanity Check](docs/assets/assistant_screenshot.png)
