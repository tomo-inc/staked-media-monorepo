# Browser Extension MVP

This directory contains the Chrome/Edge Manifest V3 extension for Staked Media Copilot.
Source code and browser-loadable artifacts are fully separated:

- `src/`: frontend source code (`TS/JS/Tailwind`)
- `public/`: static extension files (`manifest`, HTML templates)
- `dist/`: compiled output that the browser actually loads

## Layout

- `src/entries/`: runtime entry files (`background`, `content-script`, `panel`, `options`)
- `src/scripts/`: shared logic and TS modules (`shared.ts`, `panel-helpers.ts`)
- `src/styles/panel.tailwind.css`: Tailwind stylesheet entry
- `src/legacy/`: legacy JS/CSS references kept during migration
- `tests/`: Node unit tests against compiled `dist` artifacts

## Build And Load

1. Start backend:

```bash
python -m app.run -c config.json --reload
```

2. Build extension:

```bash
cd apps/browser-extension
npm install
npm run build
```

3. Open `chrome://extensions`
4. Enable `Developer mode`
5. Click `Load unpacked`
6. Select `apps/browser-extension/dist`
7. Open `https://x.com`, click the extension icon, and use the side panel or popup mode

## Tests

```bash
cd apps/browser-extension
npm test
```

## MVP Constraints

- The backend URL must use a valid `http(s)://` origin without embedded credentials
- The configured backend must already be reachable from the browser extension
- The current backend has no extension-specific authentication model
- The extension does not auto-publish; it only inserts selected text into the X composer
- Persona generation still requires `POST /api/v1/profiles/ingest` before draft generation
- API whitelist denials surface below the username field and remain visible in the draft banner during generation failures
