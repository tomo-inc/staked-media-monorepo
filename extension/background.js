importScripts("shared.js");

const {
  DEFAULT_CONFIG,
  FALLBACK_BACKEND_BASE_URL,
  coerceWindowId,
  normalizeBaseUrl,
  normalizeHostMode,
  routeMessage,
  sanitizeConfig
} = globalThis.StakedMediaExtensionShared;

const API = {
  healthz: "/healthz",
  profile: (username) => `/api/v1/profiles/${encodeURIComponent(username)}`,
  ingest: "/api/v1/profiles/ingest",
  draftsGenerate: "/api/v1/drafts/generate",
  contentGenerate: "/api/v1/content/generate",
  contentIdeas: "/api/v1/content/ideas",
  exposureAnalyze: "/api/v1/exposure/analyze"
};

initializeHostBehavior();

chrome.runtime.onInstalled.addListener(async () => {
  const current = await storageGet(Object.keys(DEFAULT_CONFIG));
  const nextConfig = sanitizeConfig(current);
  await storageSet(nextConfig);
  await applyHostMode(nextConfig.hostMode);
});

chrome.runtime.onStartup.addListener(() => {
  initializeHostBehavior();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  handleMessage(message, _sender)
    .then((payload) => sendResponse({ ok: true, ...payload }))
    .catch((error) => sendResponse({ ok: false, error: normalizeError(error) }));
  return true;
});

async function handleMessage(message) {
  return routeMessage(message, {
    get_config: async () => ({ config: await getConfig() }),
    save_config: async (payload) => ({ config: await saveConfig(payload || {}) }),
    health_check: async () => ({ health: await healthCheck() }),
    check_profile: async (payload) => ({ profile: await checkProfile(payload || {}) }),
    ingest_profile: async (payload) => ({ result: await ingestProfile(payload || {}) }),
    generate: async (payload) => ({ result: await generate(payload || {}) }),
    generate_drafts: async (payload) => ({ result: await generateDrafts(payload || {}) }),
    generate_content: async (payload) => ({ result: await generateContent(payload || {}) }),
    suggest_ideas: async (payload) => ({ result: await suggestIdeas(payload || {}) }),
    analyze_exposure: async (payload) => ({ result: await analyzeExposure(payload || {}) }),
    get_composer_state: async (payload) => ({ composer: await getComposerState(payload || {}) }),
    insert_text: async (payload) => ({ result: await insertTextIntoComposer(payload || {}) })
  });
}

async function getConfig() {
  const stored = await storageGet(Object.keys(DEFAULT_CONFIG));
  return sanitizeConfig(stored);
}

async function saveConfig(patch) {
  const nextConfig = sanitizeConfig(
    {
      ...(await getConfig()),
      ...patch
    },
    { strictBackendBaseUrl: true }
  );
  await storageSet(nextConfig);
  await applyHostMode(nextConfig.hostMode);
  return nextConfig;
}

async function getBackendBaseUrl() {
  const config = await getConfig();
  return normalizeBaseUrl(config.backendBaseUrl || FALLBACK_BACKEND_BASE_URL);
}

async function healthCheck() {
  const baseUrl = await getBackendBaseUrl();
  const start = performance.now();
  const payload = await requestJson({
    path: API.healthz,
    method: "GET"
  });
  const latencyMs = Math.round(performance.now() - start);
  return {
    baseUrl,
    status: payload.status || "ok",
    latencyMs
  };
}

async function checkProfile({ username }) {
  const normalizedUsername = assertNonEmpty(username, "username");
  try {
    const payload = await requestJson({
      path: API.profile(normalizedUsername),
      method: "GET",
      deniedUsername: normalizedUsername
    });
    return {
      exists: true,
      username: payload.profile?.username || normalizedUsername,
      storedTweetCount: payload.stored_tweet_count || 0,
      personaReady: Boolean(payload.latest_persona_snapshot),
      profile: payload.profile || null,
      latestPersonaSnapshot: payload.latest_persona_snapshot || null
    };
  } catch (error) {
    if (error && typeof error === "object" && error.status === 404) {
      return {
        exists: false,
        username: normalizedUsername,
        storedTweetCount: 0,
        personaReady: false,
        profile: null,
        latestPersonaSnapshot: null
      };
    }
    throw error;
  }
}

async function ingestProfile(payload) {
  const body = {
    username: assertNonEmpty(payload.username, "username")
  };
  const result = await requestJson({
    path: API.ingest,
    method: "POST",
    body,
    deniedUsername: body.username
  });
  await saveConfig({ defaultUsername: body.username });
  return result;
}

async function generate(payload) {
  const config = await getConfig();
  if (config.apiMode === "drafts") {
    return generateDrafts(payload);
  }
  return generateContent(payload);
}

async function generateDrafts(payload) {
  const body = {
    username: assertNonEmpty(payload.username, "username"),
    prompt: assertNonEmpty(payload.idea || payload.prompt, "idea"),
    draft_count: clampInt(payload.draft_count || 3, 1, 10)
  };
  const result = await requestJson({
    path: API.draftsGenerate,
    method: "POST",
    body,
    deniedUsername: body.username
  });
  await saveConfig({ defaultUsername: body.username });
  return result;
}

async function generateContent(payload) {
  const body = {
    username: assertNonEmpty(payload.username, "username"),
    mode: "A",
    idea: String(payload.idea || "").trim(),
    topic: String(payload.topic || payload.idea || "").trim(),
    draft_count: clampInt(payload.draft_count || 3, 1, 10)
  };
  const result = await requestJson({
    path: API.contentGenerate,
    method: "POST",
    body,
    deniedUsername: body.username
  });
  await saveConfig({ defaultUsername: body.username });
  return result;
}

async function suggestIdeas(payload) {
  const body = {
    direction: String(payload.direction || "").trim(),
    domain: String(payload.domain || "").trim(),
    topic_hint: String(payload.topic_hint || "").trim(),
    limit: clampInt(payload.limit || 8, 1, 20)
  };
  return requestJson({
    path: API.contentIdeas,
    method: "POST",
    body
  });
}

async function analyzeExposure(payload) {
  const body = {
    username: String(payload.username || "").trim(),
    text: assertNonEmpty(payload.text, "text"),
    topic: String(payload.topic || "").trim(),
    domain: String(payload.domain || "").trim()
  };
  return requestJson({
    path: API.exposureAnalyze,
    method: "POST",
    body,
    deniedUsername: body.username
  });
}

async function getComposerState(payload) {
  const target = await resolveTargetTab(payload.targetWindowId);
  if (!target.tab) {
    return {
      available: false,
      supportedPage: false,
      message: "Open x.com in a normal browser window before inserting drafts.",
      tabTitle: "",
      tabUrl: ""
    };
  }

  if (!isXTab(target.tab)) {
    return {
      available: false,
      supportedPage: false,
      message: "The active tab is not x.com or twitter.com.",
      tabTitle: target.tab.title || "",
      tabUrl: target.tab.url || ""
    };
  }

  try {
    const response = await chrome.tabs.sendMessage(target.tab.id, { type: "get_composer_state" });
    return {
      available: Boolean(response?.available),
      supportedPage: true,
      message: response?.message || "Open the X composer to insert drafts.",
      tabTitle: target.tab.title || "",
      tabUrl: target.tab.url || ""
    };
  } catch (_error) {
    return {
      available: false,
      supportedPage: true,
      message: "Reload the X tab so the extension can attach to the page.",
      tabTitle: target.tab.title || "",
      tabUrl: target.tab.url || ""
    };
  }
}

async function insertTextIntoComposer(payload) {
  const target = await resolveTargetTab(payload.targetWindowId);
  const tab = target.tab;
  if (!tab) {
    throw new Error("Open x.com in a normal browser window before inserting drafts.");
  }
  if (!isXTab(tab)) {
    throw new Error("The active tab is not x.com or twitter.com.");
  }

  const response = await chrome.tabs.sendMessage(tab.id, {
    type: "insert_text",
    payload: {
      text: assertNonEmpty(payload.text, "text")
    }
  });

  if (!response?.ok) {
    throw new Error(response?.error?.message || "Open the X composer before inserting a draft.");
  }

  return {
    inserted: true,
    tabTitle: tab.title || "",
    tabUrl: tab.url || ""
  };
}

async function requestJson({ path, method, body, deniedUsername }) {
  const baseUrl = await getBackendBaseUrl();
  let response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json"
      },
      body: body ? JSON.stringify(body) : undefined
    });
  } catch (_error) {
    throw new Error(`Local backend is unreachable at ${baseUrl}. Start the API server first.`);
  }

  const rawText = await response.text();
  let payload = null;
  if (rawText) {
    try {
      payload = JSON.parse(rawText);
    } catch (_error) {
      payload = rawText;
    }
  }

  if (!response.ok) {
    if (response.status === 403 && path.startsWith("/api/v1/")) {
      const error = new Error(formatForbiddenMessage(deniedUsername));
      error.status = response.status;
      error.payload = payload;
      throw error;
    }
    const detail =
      payload && typeof payload === "object" && !Array.isArray(payload)
        ? payload.detail || JSON.stringify(payload)
        : String(payload || response.statusText || "Request failed");
    const error = new Error(detail);
    error.status = response.status;
    error.payload = payload;
    throw error;
  }

  return payload;
}

function formatForbiddenMessage(username) {
  const normalizedUsername = String(username || "").trim();
  if (normalizedUsername) {
    const handle = normalizedUsername.startsWith("@") ? normalizedUsername : `@${normalizedUsername}`;
    return `User ${handle} is not allowed. Please contact the administrator.`;
  }
  return "This user is not allowed. Please contact the administrator.";
}

function clampInt(value, min, max) {
  const parsed = Number.parseInt(String(value), 10);
  if (!Number.isFinite(parsed)) {
    return min;
  }
  return Math.min(max, Math.max(min, parsed));
}

function assertNonEmpty(value, name) {
  const normalized = String(value || "").trim();
  if (!normalized) {
    throw new Error(`${name} is required`);
  }
  return normalized;
}

function normalizeError(error) {
  if (!error) {
    return { message: "Unknown error" };
  }
  if (typeof error === "string") {
    return { message: error };
  }
  return {
    message: String(error.message || error),
    status: Number.isFinite(error.status) ? error.status : undefined,
    payload: error.payload
  };
}

function storageGet(keys) {
  return new Promise((resolve) => chrome.storage.sync.get(keys, resolve));
}

function storageSet(values) {
  return new Promise((resolve) => chrome.storage.sync.set(values, resolve));
}

async function initializeHostBehavior() {
  const config = await getConfig();
  await applyHostMode(config.hostMode);
}

async function applyHostMode(hostMode) {
  const normalizedHostMode = normalizeHostMode(hostMode);
  await chrome.action
    .setPopup({
      popup: normalizedHostMode === "popup" ? "panel.html?host=popup" : ""
    })
    .catch(() => undefined);
  return chrome.sidePanel
    .setPanelBehavior({
      openPanelOnActionClick: normalizedHostMode === "sidepanel"
    })
    .catch(() => undefined);
}

async function resolveTargetTab(targetWindowId) {
  const windowId = await resolveNormalWindowId(targetWindowId);
  if (!windowId) {
    return { tab: null, windowId: null };
  }
  const [tab] = await chrome.tabs.query({
    active: true,
    windowId
  });
  return {
    tab: tab || null,
    windowId
  };
}

async function resolveNormalWindowId(candidate) {
  const explicitWindowId = coerceWindowId(candidate);
  if (explicitWindowId) {
    const directMatch = await getNormalWindow(explicitWindowId);
    if (directMatch) {
      return directMatch.id;
    }
  }

  try {
    const focusedWindow = await chrome.windows.getLastFocused();
    if (focusedWindow?.type === "normal" && Number.isFinite(focusedWindow.id)) {
      return focusedWindow.id;
    }
  } catch (_error) {
    // Ignore and continue to broader fallback.
  }

  const windows = await chrome.windows.getAll();
  const fallbackWindow = windows.find((windowInfo) => windowInfo.type === "normal" && Number.isFinite(windowInfo.id));
  return fallbackWindow?.id || null;
}

async function getNormalWindow(windowId) {
  try {
    const windowInfo = await chrome.windows.get(windowId);
    if (windowInfo?.type === "normal") {
      return windowInfo;
    }
  } catch (_error) {
    return null;
  }
  return null;
}

function isXTab(tab) {
  const url = String(tab?.url || "");
  return /^https:\/\/(?:x|twitter)\.com\//.test(url);
}
