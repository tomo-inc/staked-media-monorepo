# Staked Media MVP

Minimal Python MVP for:
- fetching one X user's profile and a caller-specified number of tweets from the upstream service,
- building a reusable persona from profile + tweet history,
- generating X post drafts that sound like the same author.

## Stack
- FastAPI
- SQLite
- requests
- OpenAI Chat Completions API
- Gemini Generate Content API

## Upstream Data Source
- Base URL: `http://52.76.50.165:8081`
- Proxy: `http://192.168.1.199:9000`

The service routes upstream profile and tweet calls through the configured proxy.

## Local Setup
1. Copy `config.example.json` to `config.json`
2. Edit `config.json`
   - Set `app.llm_provider` to `openai` or `gemini`
   - Fill in the matching API key: `app.openai_api_key` for OpenAI or `app.gemini_api_key` for Gemini
   - Optional overrides live in the same `app` section, including models, proxies, logging, retries, timeouts, and web enrichment
   - If Gemini returns `User location is not supported for the API use.`, set `app.llm_http_proxy` so outbound LLM requests route through a supported region
   - `server.host`, `server.port`, and `server.reload` control the HTTP server startup defaults
3. Install Python packages if you are not using system packages:

```bash
pip install -r requirements.txt
```

4. Start the server:

```bash
python -m app.run -c config.json
```

For local development with hot reload:

```bash
python -m app.run -c config.json --reload
```

## API
### Health
```bash
curl http://127.0.0.1:8000/healthz
```

### Trial whitelist
Persona-related public APIs are guarded by a username allowlist. If the target username is not in the whitelist, the API returns `403 Forbidden`.

Internal whitelist management endpoints:

```bash
curl http://127.0.0.1:8000/admin/api/v1/whitelist/usernames

curl -X POST http://127.0.0.1:8000/admin/api/v1/whitelist/usernames \
  -H 'Content-Type: application/json' \
  -d '{"username":"ryanfang95"}'

curl -X DELETE http://127.0.0.1:8000/admin/api/v1/whitelist/usernames/ryanfang95
```

### Ingest profile and tweets
```bash
curl -X POST http://127.0.0.1:8000/api/v1/profiles/ingest \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "ryanfang95"
  }'
```

The service chooses its own ingest tweet count internally and uses the upstream tweets API's `cursor` pagination until it reaches that count or runs out of tweets.

### Get stored profile and latest persona
```bash
curl http://127.0.0.1:8000/api/v1/profiles/ryanfang95
```

### Generate drafts
```bash
curl -X POST http://127.0.0.1:8000/api/v1/drafts/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "ryanfang95",
    "prompt": "Announce a new strategic partnership",
    "draft_count": 5
  }'
```

### Generate personalized content (mode A/B, auto web enrichment)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/content/generate \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "ryanfang95",
    "mode": "A",
    "idea": "Share thoughts on Binance winners list",
    "direction": "crypto growth",
    "domain": "ai",
    "topic": "Binance AI contest winners",
    "keywords": ["Binance", "winners", "AI"],
    "draft_count": 3
  }'
```

When historical topic matches are sparse (`<3`) or score is below target (`<9.0`), the service automatically fetches public topic signals from the web and retries generation.
`/api/v1/content/generate` now returns three parallel variants in `variants`:
- `normal` (normal writing)
- `expansion` (expansion thinking)
- `open` (open thinking)

For backward compatibility, `drafts` / `formatted_drafts` / `score` still exist and map to `recommended_variant`.
The response also includes quality-gate fields:
- `quality_gate_met`: whether at least one variant reached target (>=9.0)
- `quality_gate_reason`: non-empty when all variants are below target

Note that `/api/v1/content/generate` now enforces the presence of a persona snapshot when saving draft requests; if no persona snapshot exists for the user, the endpoint returns `409 Conflict` instead of attempting to persist the draft.

### Suggest ideas (mode B pre-step)
```bash
curl -X POST http://127.0.0.1:8000/api/v1/content/ideas \
  -H 'Content-Type: application/json' \
  -d '{
    "direction": "crypto",
    "domain": "ai",
    "topic_hint": "Binance",
    "limit": 8
  }'
```

### Exposure helper
```bash
curl -X POST http://127.0.0.1:8000/api/v1/exposure/analyze \
  -H 'Content-Type: application/json' \
  -d '{
    "username": "ryanfang95",
    "text": "Your candidate tweet text here",
    "topic": "Binance",
    "domain": "crypto"
  }'
```

## Notes
- The app reads configuration only from the JSON file passed to `python -m app.run -c ...`; `.env` and environment-variable overrides are no longer used.
- LLM provider selection is config-file based via `app.llm_provider`; the HTTP API does not expose a per-request provider override.
- `app.llm_http_proxy` configures the proxy for outbound LLM requests (OpenAI/Gemini). `app.twitter_data_proxy` configures the proxy for Twitter data API requests. Either can be left empty to disable proxying.
- Persona-related public APIs now require the target username to exist in the database-backed trial whitelist. Internal whitelist management lives under `/admin/api/v1/...`.
- The LLM integration now lives under the `app/llm/` package while keeping supported imports such as `from app.llm import LLMClient, GeminiClient, OpenAIClient, create_llm_client`.
- `app.llm` does not re-export third-party modules. Tests that mock outbound LLM HTTP calls should patch `app.llm.base_client.requests.post`.
- The app now emits structured runtime logs to stdout and, by default, to `data/app.log`.
- Logs are JSON-per-line with an `event` field; API requests include a `request_id` that is propagated into upstream and LLM logs for correlation.
- Prompts and model responses are not logged in full by default; snippets are truncated via `app.log_max_body_chars`. Set `app.log_enable_file=false` to disable file logging.
- LLM provider calls now retry transient failures only (timeouts, connection errors, and 5xx). Score requests use `app.llm_score_timeout_seconds`, which is shorter than the main generation timeout by default.
- Gemini JSON parsing now safely handles fenced JSON blocks and wrapped JSON text, but still fails on genuinely malformed payloads.
- The upstream tweet endpoint paginates with `cursor` and returns `next_cursor`; this app handles that pagination internally and does not expose cursor on its own ingest API.
- The MVP stores raw upstream payloads in SQLite for debugging and reuse.
- Draft generation reads a bounded recent-history window instead of all stored tweets, so ingesting more history does not linearly expand generation cost.
- Persona snapshots now include `generation_guardrails` so draft generation can preserve openings, compression habits, anti-patterns, and bilingual texture.
- Draft generation now extracts theme keywords from the prompt, retrieves matching historical tweets, derives 3-5 high-frequency topic keywords, and uses them to steer generation.
- Draft generation runs automatic similarity checks plus mixed rule/LLM scoring, retrying up to 5 rounds to target a score of `9.0`.
- Draft generation rejects outputs that are too close to source tweets.
- Draft generation follows the language requested in the prompt instead of forcing English-only output.
- Draft responses now include theme keywords, matched historical tweet snippets, top theme keywords, score, retry count, and evaluation metadata.
- Draft responses also include each attempt's full candidate list with per-candidate scores and failure reasons when a candidate does not meet the target score.
- The upstream client retries transient 5xx responses and clears cookies between requests to avoid timeline pagination issues.
- `POST /api/v1/profiles/ingest` uses a server-side ingest count; callers only provide the username.
- If a user has fewer tweets than requested, the service uses all available tweets.

## Validation
```bash
python -m pytest -q
```

## Browser Extension MVP

This repository now includes a Chrome/Edge Manifest V3 extension under [apps/browser-extension/README.md](apps/browser-extension/README.md).

What it does:
- checks whether a profile/persona already exists,
- calls `POST /api/v1/profiles/ingest`,
- calls `POST /api/v1/content/ideas` and `POST /api/v1/content/generate`,
- opens from the Chrome toolbar into a side panel or detached window,
- inserts a selected draft into the active X composer without auto-posting.

Load it locally:
1. Start the backend with `python -m app.run -c config.json --reload`
2. Build extension assets with `cd apps/browser-extension && npm install && npm run build`
3. Open `chrome://extensions`
4. Enable `Developer mode`
5. Click `Load unpacked`
6. Select the `apps/browser-extension/dist` directory
7. Open `https://x.com` and click the extension icon to launch the side panel

Notes:
- Extension source and runtime output are separated as `src/`, `public/`, and `dist/`.
- It assumes the local Python backend is running at `http://127.0.0.1:8000`; there is still no plugin-specific auth layer.
- Ingest is still mandatory before generation.
