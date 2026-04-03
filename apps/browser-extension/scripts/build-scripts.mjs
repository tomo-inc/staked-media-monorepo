import { build } from "esbuild";

const entries = [
  ["src/scripts/shared.ts", "dist/shared.js"],
  ["src/scripts/panel-helpers.ts", "dist/panel-helpers.js"],
  ["src/entries/background.js", "dist/background.js"],
  ["src/entries/content-script.js", "dist/content-script.js"],
  ["src/entries/panel.js", "dist/panel.js"],
  ["src/entries/options.js", "dist/options.js"]
];

await Promise.all(
  entries.map(([entryPoint, outfile]) =>
    build({
      entryPoints: [entryPoint],
      outfile,
      bundle: false,
      platform: "browser",
      target: ["chrome114"],
      legalComments: "none"
    })
  )
);
