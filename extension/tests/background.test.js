const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const shared = require("../shared.js");

function createBackgroundHarness(options = {}) {
  const storage = { ...(options.storage || {}) };
  const calls = {
    setPopup: [],
    setPanelBehavior: []
  };
  const listeners = {
    onInstalled: null,
    onStartup: null,
    onMessage: null
  };

  const context = {
    console,
    URL,
    JSON,
    Math,
    Number,
    String,
    Object,
    Array,
    Promise,
    Error,
    encodeURIComponent,
    performance: {
      now: (() => {
        let tick = 0;
        return () => {
          tick += 25;
          return tick;
        };
      })()
    },
    fetch: options.fetch || (async () => {
      throw new Error("fetch not stubbed");
    }),
    importScripts() {
      context.StakedMediaExtensionShared = shared;
    }
  };

  context.globalThis = context;
  context.chrome = {
    runtime: {
      onInstalled: { addListener(listener) { listeners.onInstalled = listener; } },
      onStartup: { addListener(listener) { listeners.onStartup = listener; } },
      onMessage: { addListener(listener) { listeners.onMessage = listener; } },
      lastError: null
    },
    storage: {
      sync: {
        get(keys, callback) {
          const result = {};
          if (Array.isArray(keys)) {
            for (const key of keys) {
              if (Object.prototype.hasOwnProperty.call(storage, key)) {
                result[key] = storage[key];
              }
            }
          }
          callback(result);
        },
        set(values, callback) {
          Object.assign(storage, values);
          callback?.();
        }
      }
    },
    action: {
      async setPopup(payload) {
        calls.setPopup.push(payload);
      }
    },
    sidePanel: {
      async setPanelBehavior(payload) {
        calls.setPanelBehavior.push(payload);
      }
    },
    tabs: {
      async query() {
        return [];
      },
      async sendMessage() {
        return null;
      }
    },
    windows: {
      async getLastFocused() {
        return { type: "normal", id: 91 };
      },
      async getAll() {
        return [{ type: "normal", id: 91 }];
      },
      async get(windowId) {
        return { type: "normal", id: windowId };
      }
    }
  };

  const code = fs.readFileSync(path.join(__dirname, "..", "background.js"), "utf8");
  vm.runInNewContext(code, context, {
    filename: "background.js"
  });

  return { context, storage, calls, listeners };
}

function flushTasks() {
  return new Promise((resolve) => setImmediate(resolve));
}

function dispatchRuntimeMessage(listener, message) {
  return new Promise((resolve) => {
    const keepAlive = listener(message, {}, (response) => resolve(response));
    assert.equal(keepAlive, true);
  });
}

test("background save_config updates host mode and popup behavior", async () => {
  const harness = createBackgroundHarness();
  await flushTasks();

  const response = await dispatchRuntimeMessage(harness.listeners.onMessage, {
    type: "save_config",
    payload: { hostMode: "popup" }
  });

  assert.equal(response.ok, true);
  assert.equal(response.config.hostMode, "popup");
  assert.equal(harness.storage.hostMode, "popup");
  assert.equal(harness.calls.setPopup.at(-1)?.popup, "panel.html?host=popup");
  assert.equal(harness.calls.setPanelBehavior.at(-1)?.openPanelOnActionClick, false);
});

test("background save_config accepts hosted backend URLs", async () => {
  const harness = createBackgroundHarness();
  await flushTasks();

  const response = await dispatchRuntimeMessage(harness.listeners.onMessage, {
    type: "save_config",
    payload: { backendBaseUrl: "https://api.example.com" }
  });

  assert.equal(response.ok, true);
  assert.equal(response.config.backendBaseUrl, "https://api.example.com");
  assert.equal(harness.storage.backendBaseUrl, "https://api.example.com");
});

test("background save_config rejects unsupported backend protocols", async () => {
  const harness = createBackgroundHarness();
  await flushTasks();

  const response = await dispatchRuntimeMessage(harness.listeners.onMessage, {
    type: "save_config",
    payload: { backendBaseUrl: "ftp://api.example.com" }
  });

  assert.equal(response.ok, false);
  assert.match(response.error.message, /Backend URL must be a valid http\(s\) URL without embedded credentials\./);
});

test("background save_config rejects backend credentials", async () => {
  const harness = createBackgroundHarness();
  await flushTasks();

  const response = await dispatchRuntimeMessage(harness.listeners.onMessage, {
    type: "save_config",
    payload: { backendBaseUrl: "https://user:secret@example.com" }
  });

  assert.equal(response.ok, false);
  assert.match(response.error.message, /Backend URL must be a valid http\(s\) URL without embedded credentials\./);
});
