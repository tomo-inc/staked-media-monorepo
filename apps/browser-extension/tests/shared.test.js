const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEFAULT_CONFIG,
  escapeHtml,
  extractDrafts,
  routeMessage,
  sanitizeConfig
} = require("../dist/shared.js");

test("routeMessage dispatches supported handlers", async () => {
  const result = await routeMessage(
    { type: "generate", payload: { username: "alice" } },
    {
      generate: async (payload) => ({ echoed: payload.username })
    }
  );

  assert.deepEqual(result, { echoed: "alice" });
});

test("routeMessage rejects unsupported handlers", async () => {
  await assert.rejects(
    () => routeMessage({ type: "missing" }, {}),
    /Unsupported message type: missing/
  );
});

test("default config uses the hosted backend URL", () => {
  assert.equal(DEFAULT_CONFIG.backendBaseUrl, "https://api.sayviner.top:8443");
});

test("sanitizeConfig normalizes and trims persisted settings", () => {
  const config = sanitizeConfig({
    defaultUsername: "  satoshi  ",
    backendBaseUrl: "http://localhost:9000/",
    apiMode: "drafts",
    theme: "dark",
    hostMode: "popup"
  });

  assert.deepEqual(config, {
    ...DEFAULT_CONFIG,
    defaultUsername: "satoshi",
    backendBaseUrl: "http://localhost:9000",
    apiMode: "drafts",
    theme: "dark",
    hostMode: "popup"
  });
});

test("sanitizeConfig falls back for invalid stored backend URLs", () => {
  const config = sanitizeConfig({
    backendBaseUrl: "ftp://api.example.com"
  });

  assert.equal(config.backendBaseUrl, DEFAULT_CONFIG.backendBaseUrl);
});

test("sanitizeConfig accepts hosted backend URLs in strict mode", () => {
  const config = sanitizeConfig(
    {
      backendBaseUrl: "https://api.example.com/v1/"
    },
    { strictBackendBaseUrl: true }
  );

  assert.equal(config.backendBaseUrl, "https://api.example.com/v1");
});

test("sanitizeConfig rejects unsupported backend protocols in strict mode", () => {
  assert.throws(
    () =>
      sanitizeConfig(
        {
          backendBaseUrl: "ftp://api.example.com"
        },
        { strictBackendBaseUrl: true }
      ),
    /Backend URL must be a valid http\(s\) URL without embedded credentials\./
  );
});

test("sanitizeConfig rejects backend URLs with credentials in strict mode", () => {
  assert.throws(
    () =>
      sanitizeConfig(
        {
          backendBaseUrl: "https://user:secret@example.com"
        },
        { strictBackendBaseUrl: true }
      ),
    /Backend URL must be a valid http\(s\) URL without embedded credentials\./
  );
});

test("sanitizeConfig keeps system theme and ignores unknown themes", () => {
  assert.equal(sanitizeConfig({ theme: "system" }).theme, "system");
  assert.equal(sanitizeConfig({ theme: "neon" }).theme, DEFAULT_CONFIG.theme);
});

test("extractDrafts prefers direct drafts and variant drafts", () => {
  assert.deepEqual(extractDrafts({ drafts: [{ text: "one" }] }), [{ text: "one" }]);
  assert.deepEqual(
    extractDrafts({ variants: [{ drafts: [{ text: "two" }] }] }),
    [{ text: "two" }]
  );
});

test("extractDrafts maps formatted drafts into objects", () => {
  assert.deepEqual(extractDrafts({ formatted_drafts: ["alpha", "beta"] }), [
    { text: "alpha" },
    { text: "beta" }
  ]);
});

test("escapeHtml escapes unsafe characters", () => {
  assert.equal(
    escapeHtml('<div class="x">Tom & Jerry</div>'),
    "&lt;div class=&quot;x&quot;&gt;Tom &amp; Jerry&lt;/div&gt;"
  );
});
