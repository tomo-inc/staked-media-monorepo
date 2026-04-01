const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DEFAULT_CONFIG,
  escapeHtml,
  extractDrafts,
  routeMessage,
  sanitizeConfig
} = require("../shared.js");

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

test("sanitizeConfig normalizes and trims persisted settings", () => {
  const config = sanitizeConfig({
    defaultUsername: "  satoshi  ",
    backendBaseUrl: "http://localhost:9000/",
    apiMode: "drafts",
    debugLogs: 1,
    theme: "light",
    hostMode: "popup"
  });

  assert.deepEqual(config, {
    ...DEFAULT_CONFIG,
    defaultUsername: "satoshi",
    backendBaseUrl: "http://localhost:9000",
    apiMode: "drafts",
    debugLogs: true,
    hostMode: "popup"
  });
});

test("sanitizeConfig falls back for invalid stored backend URLs", () => {
  const config = sanitizeConfig({
    backendBaseUrl: "https://api.example.com"
  });

  assert.equal(config.backendBaseUrl, DEFAULT_CONFIG.backendBaseUrl);
});

test("sanitizeConfig rejects non-local backend URLs in strict mode", () => {
  assert.throws(
    () =>
      sanitizeConfig(
        {
          backendBaseUrl: "https://api.example.com"
        },
        { strictBackendBaseUrl: true }
      ),
    /Backend URL must use http\(s\):\/\/localhost or http\(s\):\/\/127\.0\.0\.1\./
  );
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
