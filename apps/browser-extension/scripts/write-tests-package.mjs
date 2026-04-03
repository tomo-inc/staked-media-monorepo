import { mkdir, writeFile } from "node:fs/promises";

const TESTS_OUTDIR = "tests-dist";

await mkdir(TESTS_OUTDIR, { recursive: true });
await writeFile(
	`${TESTS_OUTDIR}/package.json`,
	JSON.stringify({ type: "module" }, null, 2) + "\n",
	"utf8",
);
