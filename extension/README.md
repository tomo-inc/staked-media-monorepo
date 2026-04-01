# Browser Extension MVP

This directory contains a no-build Chrome/Edge Manifest V3 extension that talks to the existing FastAPI backend.

## Files

- `manifest.json`: MV3 manifest
- `background.js`: backend bridge, host-mode orchestration, and config storage
- `content-script.js`: X/Twitter composer bridge
- `panel.html` / `panel.js` / `panel.css`: side panel and popup UI
- `options.html` / `options.js`: extension settings page

## Load locally

1. Start the Python backend:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

2. Open Chrome or Edge and go to `chrome://extensions`
3. Enable `Developer mode`
4. Click `Load unpacked`
5. Select the `extension/` directory from this repository
6. Open `https://x.com`, click the extension icon, and use the default host mode
7. In extension Settings, choose `Switch to Side Panel` or `Switch to Popup` to persist how the toolbar icon opens the UI

## Tests

Run the extension unit tests with Node:

```bash
node --test extension/tests/*.test.js
```

## MVP Constraints

- The backend URL must use `localhost` or `127.0.0.1`
- The local backend at `http://127.0.0.1:8000` must already be reachable from the browser extension
- The current backend has no extension-specific authentication model
- The extension does not auto-publish; it only inserts selected text into the X composer
- Persona generation still requires `POST /api/v1/profiles/ingest` before draft generation
