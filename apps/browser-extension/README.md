# Browser Extension MVP

This directory contains the Chrome/Edge Manifest V3 extension for FoxSpark.
Source code and browser-loadable artifacts are fully separated:

- `src/`: frontend source code (`TS/JS/Tailwind`)
- `public/`: static extension files (`manifest`, HTML templates)
- `dist/`: compiled output that the browser actually loads

## Layout

- `src/entries/`: runtime entry files (`background`, `content-script`, `panel`, `options`)
- `src/scripts/`: shared logic and TS modules (`shared.ts`, `panel-helpers.ts`)
- `src/styles/panel.tailwind.css`: Tailwind stylesheet entry
- `tests/`: Node unit tests against compiled `dist` artifacts

## Build And Load

1. Build extension:

```bash
cd apps/browser-extension
npm install
npm run generate:icons
npm run build
```

2. Open `chrome://extensions`
3. Enable `Developer mode`
4. Click `Load unpacked`
5. Select `apps/browser-extension/dist`
6. Open `https://x.com`, click the extension icon, and use the side panel or popup mode

## Tests

```bash
cd apps/browser-extension
npm test
```

## Icons

- `public/icons/icon.svg` is the source-of-truth icon artwork.
- Chrome extension manifest icons still need raster PNG files, so regenerate them after editing the SVG:

```bash
cd apps/browser-extension
npm run generate:icons
```

## MVP Constraints

- The extension does not auto-publish; it only inserts selected text into the X composer
