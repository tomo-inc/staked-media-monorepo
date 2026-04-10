import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { Resvg } from "@resvg/resvg-js";

const __dirname = dirname(fileURLToPath(import.meta.url));
const iconsDir = resolve(__dirname, "../public/icons");
const svgPath = resolve(iconsDir, "icon.svg");
const sizes = [16, 32, 48, 128, 512];

const svg = await readFile(svgPath);
await mkdir(iconsDir, { recursive: true });

for (const size of sizes) {
	const resvg = new Resvg(svg, {
		background: "rgba(0,0,0,0)",
		fitTo: {
			mode: "width",
			value: size,
		},
	});
	const png = resvg.render().asPng();
	await writeFile(resolve(iconsDir, `icon-${size}.png`), png);
}

console.log(
	`Generated extension icons from ${svgPath} at sizes ${sizes.join(", ")}`,
);
