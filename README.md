# Facebook Marketplace Scraper (Wrapper Actor)

This project packages the wrapper actor so it can be built and executed on Apify's platform. It vendors a public Marketplace scraper at build time and layers custom orchestration, proxy configuration, and run-to-run deduplication on top.

## Features
- Mirrors the original actor input fields, including proxy configuration and deduplication toggles.
- Launches Playwright Chromium with optional proxy routing.
- Optionally fetches per-item detail pages for richer data.
- Persists seen listing IDs between runs to avoid duplicates.

## Project layout
- `.actor/actor.json` – Actor manifest with the exact input schema used on Apify.
- `INPUT_SCHEMA.json` – Standalone schema file validated with Apify tooling.
- `Dockerfile` – Finalized image definition based on `apify/actor-python-playwright` with the upstream scraper vendored during build.
- `requirements.txt` – Python dependencies pinned for reproducible builds (including `apify==3.0.3`).
- `src/__main__.py` – Async wrapper entrypoint executed by Apify.

## Runbook
The steps below demonstrate how to build and run the actor locally using the Apify CLI. They mirror what Apify does on the platform, so a successful local build indicates the actor is ready for Apify.

1. **Install and authenticate the Apify CLI (one time per environment):**
   ```bash
   npm install -g apify-cli
   apify login
   ```
   When prompted, paste the API token from the Apify Console (Settings → Integrations).

2. **Build the actor image:**
   ```bash
   apify build
   ```
   This command installs Python dependencies, vendors the upstream scraper repository, and produces a local Docker image identical to the one Apify will build.

3. **Run the actor locally:**
   ```bash
   apify run --input=sample-input.json
   ```
   Copy the sample payload below into `sample-input.json` (or provide your own file) before running the command.

4. **Deploy to Apify (optional):**
   ```bash
   apify push
   ```
   This uploads the actor, triggering the same build pipeline on Apify's infrastructure.

## Sample input
Create `sample-input.json` with the following example payload:
```json
{
  "urls": [
    "https://www.facebook.com/marketplace/portland/search/?query=Dive%20gear&radius=805&deliveryMethod=all"
  ],
  "fetch_item_details": false,
  "deduplicate_across_runs": true,
  "stop_on_first_page_all_duplicates": false,
  "max_items": 100,
  "proxy": {
    "useApifyProxy": true,
    "apifyProxyGroups": ["RESIDENTIAL"],
    "apifyProxyCountry": "US"
  }
}
```
Modify or replace this file to suit your scraping needs before running the actor.
