const test = require("node:test");
const assert = require("node:assert/strict");

const { deriveConnectionIndicator } = require("../panel-helpers.js");

test("deriveConnectionIndicator distinguishes loading from failed health checks", () => {
  const loading = deriveConnectionIndicator({
    health: null,
    latencyMs: null,
    healthState: "loading"
  });
  const failed = deriveConnectionIndicator({
    health: null,
    latencyMs: null,
    healthState: "error"
  });

  assert.equal(loading.title, "Checking...");
  assert.equal(loading.className, "smc-status-dot smc-dot-warn");
  assert.equal(loading.latencyText, "--");

  assert.equal(failed.title, "Disconnected");
  assert.equal(failed.className, "smc-status-dot smc-dot-err");
  assert.equal(failed.latencyText, "");
});

test("deriveConnectionIndicator renders connected state with latency", () => {
  const connected = deriveConnectionIndicator({
    health: { status: "ok" },
    latencyMs: 123,
    healthState: "ready"
  });

  assert.equal(connected.title, "Connected 123ms");
  assert.equal(connected.className, "smc-status-dot smc-dot-ok");
  assert.equal(connected.latencyText, "123ms");
});
