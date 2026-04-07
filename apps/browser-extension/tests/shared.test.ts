import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);

const {
	DEFAULT_CONFIG,
	escapeHtml,
	extractDrafts,
	listLanguageOptions,
	resolveLocale,
	routeMessage,
	sanitizeConfig,
	t,
} = require("../dist/shared.js") as Pick<
	StakedMediaExtensionSharedApi,
	| "DEFAULT_CONFIG"
	| "escapeHtml"
	| "extractDrafts"
	| "listLanguageOptions"
	| "resolveLocale"
	| "routeMessage"
	| "sanitizeConfig"
	| "t"
>;

test("routeMessage dispatches supported handlers", async () => {
	const result = await routeMessage(
		{ type: "generate", payload: { username: "alice" } },
		{
			generate: async (payload) => ({ echoed: payload.username }),
		},
	);

	assert.deepEqual(result, { echoed: "alice" });
});

test("routeMessage rejects unsupported handlers", async () => {
	await assert.rejects(
		() => routeMessage({ type: "missing" }, {}),
		/Unsupported message type: missing/,
	);
});

test("default config uses the hosted backend URL", () => {
	assert.equal(DEFAULT_CONFIG.backendBaseUrl, "https://api.sayviner.top:8443");
	assert.equal(DEFAULT_CONFIG.apiMode, "drafts");
	assert.equal(DEFAULT_CONFIG.language, "auto");
});

test("sanitizeConfig normalizes and trims persisted settings", () => {
	const config = sanitizeConfig({
		defaultUsername: "  satoshi  ",
		backendBaseUrl: "  https://api.sayviner.top:8443/v1/  ",
		apiMode: "drafts",
		theme: "dark",
		hostMode: "popup",
	});

	assert.deepEqual(config, {
		...DEFAULT_CONFIG,
		defaultUsername: "satoshi",
		backendBaseUrl: "https://api.sayviner.top:8443/v1",
		apiMode: "drafts",
		theme: "dark",
		hostMode: "popup",
	});
});

test("sanitizeConfig falls back for invalid stored backend URLs", () => {
	const config = sanitizeConfig({
		backendBaseUrl: "ftp://api.example.com",
	});

	assert.equal(config.backendBaseUrl, DEFAULT_CONFIG.backendBaseUrl);
});

test("sanitizeConfig accepts allowed backend hosts in strict mode", () => {
	const config = sanitizeConfig(
		{
			backendBaseUrl: "https://api.sayviner.top:8443/v1/",
		},
		{ strictBackendBaseUrl: true },
	);

	assert.equal(config.backendBaseUrl, "https://api.sayviner.top:8443/v1");
});

test("sanitizeConfig rejects unsupported backend protocols in strict mode", () => {
	assert.throws(
		() =>
			sanitizeConfig(
				{
					backendBaseUrl: "ftp://api.example.com",
				},
				{ strictBackendBaseUrl: true },
			),
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("sanitizeConfig rejects backend URLs with credentials in strict mode", () => {
	assert.throws(
		() =>
			sanitizeConfig(
				{
					backendBaseUrl: "https://user:secret@localhost",
				},
				{ strictBackendBaseUrl: true },
			),
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("sanitizeConfig rejects non-whitelisted backend hosts in strict mode", () => {
	assert.throws(
		() =>
			sanitizeConfig(
				{
					backendBaseUrl: "https://evil.example.com",
				},
				{ strictBackendBaseUrl: true },
			),
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("sanitizeConfig falls back for non-whitelisted hosts in non-strict mode", () => {
	const config = sanitizeConfig({
		backendBaseUrl: "https://evil.example.com",
	});
	assert.equal(config.backendBaseUrl, DEFAULT_CONFIG.backendBaseUrl);
});

test("sanitizeConfig keeps system theme and ignores unknown themes", () => {
	assert.equal(sanitizeConfig({ theme: "system" }).theme, "system");
	assert.equal(
		sanitizeConfig({
			theme: "neon" as unknown as StakedMediaThemeMode,
		}).theme,
		DEFAULT_CONFIG.theme,
	);
});

test("sanitizeConfig accepts supported language values and falls back to auto", () => {
	assert.equal(
		sanitizeConfig({
			language: "zh-CN",
		}).language,
		"zh-CN",
	);
	assert.equal(
		sanitizeConfig({
			language: "italian" as unknown as StakedMediaLanguageMode,
		}).language,
		"auto",
	);
});

test("resolveLocale maps browser language correctly when language is auto", () => {
	assert.equal(resolveLocale("auto", "zh-HK"), "zh-TW");
	assert.equal(resolveLocale("auto", "zh-CN"), "zh-CN");
	assert.equal(resolveLocale("auto", "ja-JP"), "ja");
	assert.equal(resolveLocale("auto", "ko-KR"), "ko");
	assert.equal(resolveLocale("auto", "es-MX"), "es");
	assert.equal(resolveLocale("auto", "fr-FR"), "en");
	assert.equal(resolveLocale("zh-TW", "fr-FR"), "zh-TW");
});

test("i18n helpers return translated labels and language options", () => {
	assert.equal(t("action.generate", "zh-CN"), "生成");
	const options = listLanguageOptions("zh-CN");
	assert.equal(options[0]?.value, "auto");
	assert.match(String(options[0]?.label || ""), /自动|跟随浏览器/);
});

test("extractDrafts prefers direct drafts and variant drafts", () => {
	assert.deepEqual(extractDrafts({ drafts: [{ text: "one" }] }), [
		{ text: "one" },
	]);
	assert.deepEqual(
		extractDrafts({ variants: [{ drafts: [{ text: "two" }] }] }),
		[{ text: "two" }],
	);
});

test("extractDrafts maps formatted drafts into objects", () => {
	assert.deepEqual(extractDrafts({ formatted_drafts: ["alpha", "beta"] }), [
		{ text: "alpha" },
		{ text: "beta" },
	]);
});

test("escapeHtml escapes unsafe characters", () => {
	assert.equal(
		escapeHtml('<div class="x">Tom & Jerry</div>'),
		"&lt;div class=&quot;x&quot;&gt;Tom &amp; Jerry&lt;/div&gt;",
	);
});
