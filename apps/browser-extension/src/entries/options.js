const { DEFAULT_CONFIG, sendRuntimeMessage } = window.StakedMediaExtensionShared;

const DEFAULTS = { ...DEFAULT_CONFIG };
const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

const state = {
  config: null,
  page: "home"
};

const fields = {
  headerTitle: document.getElementById("headerTitle"),
  backButton: document.getElementById("backButton"),
  homePage: document.getElementById("homePage"),
  apiPage: document.getElementById("apiPage"),
  openApiSettingsButton: document.getElementById("openApiSettingsButton"),
  backendBaseUrl: document.getElementById("backendBaseUrl"),
  apiModeDrafts: document.getElementById("apiModeDrafts"),
  apiModeContent: document.getElementById("apiModeContent"),
  theme: document.getElementById("theme"),
  hostModeTitle: document.getElementById("hostModeTitle"),
  toggleOpenModeButton: document.getElementById("toggleOpenModeButton"),
  status: document.getElementById("status")
};

init().catch((error) => {
  setStatus(String(error.message || error), "warn");
});

fields.backButton.addEventListener("click", async () => {
  await closeCurrentPage();
});

fields.openApiSettingsButton.addEventListener("click", () => {
  state.page = "api";
  renderPage();
});

fields.toggleOpenModeButton.addEventListener("click", async () => {
  await switchHostMode(getNextHostMode());
});

fields.theme.addEventListener("change", async () => {
  await saveTheme(fields.theme.value);
});

fields.apiModeDrafts.addEventListener("change", async () => {
  if (fields.apiModeDrafts.checked) {
    await saveApiMode("drafts");
  }
});

fields.apiModeContent.addEventListener("change", async () => {
  if (fields.apiModeContent.checked) {
    await saveApiMode("content");
  }
});

fields.backendBaseUrl.addEventListener("blur", async () => {
  await saveBackendBaseUrl();
});

fields.backendBaseUrl.addEventListener("keydown", (event) => {
  if (event.key !== "Enter") {
    return;
  }
  event.preventDefault();
  fields.backendBaseUrl.blur();
});

if (typeof systemThemeQuery.addEventListener === "function") {
  systemThemeQuery.addEventListener("change", () => {
    if ((state.config?.theme || DEFAULTS.theme) === "system") {
      applyTheme("system");
    }
  });
}

async function init() {
  const response = await sendRuntimeMessage({ type: "get_config" });
  state.config = response.config || DEFAULTS;
  applyConfig(state.config, { syncApiForm: true });
  renderPage();
  setStatus("", "");
}

function applyConfig(config, options = {}) {
  const syncApiForm = options.syncApiForm !== false;
  const next = { ...DEFAULTS, ...config };
  state.config = next;

  if (syncApiForm) {
    fields.backendBaseUrl.value = next.backendBaseUrl;
    if (next.apiMode === "drafts") {
      fields.apiModeDrafts.checked = true;
    } else {
      fields.apiModeContent.checked = true;
    }
  }

  fields.theme.value = next.theme || "light";
  fields.hostModeTitle.textContent = getOpenModeToggleLabel(next.hostMode);
  applyTheme(next.theme);
}

function renderPage() {
  const isApiPage = state.page === "api";
  fields.homePage.hidden = isApiPage;
  fields.apiPage.hidden = !isApiPage;
  fields.backButton.hidden = !isApiPage;
  fields.backButton.setAttribute("aria-label", isApiPage ? "Back to settings" : "Back");
  fields.headerTitle.textContent = isApiPage ? "API & Generation" : "Settings";
}

async function closeCurrentPage() {
  if (state.page !== "api") {
    return;
  }
  const saved = await saveBackendBaseUrl();
  if (!saved) {
    return;
  }
  state.page = "home";
  renderPage();
}

async function saveTheme(theme) {
  try {
    const response = await sendRuntimeMessage({ type: "save_config", payload: { theme } });
    applyConfig(response.config || DEFAULTS, { syncApiForm: false });
    setStatus("", "");
  } catch (error) {
    applyConfig(state.config || DEFAULTS, { syncApiForm: false });
    setStatus(String(error.message || error), "warn");
  }
}

async function saveApiMode(apiMode) {
  try {
    const response = await sendRuntimeMessage({ type: "save_config", payload: { apiMode } });
    applyConfig(response.config || DEFAULTS, { syncApiForm: false });
    setStatus("", "");
  } catch (error) {
    applyConfig(state.config || DEFAULTS, { syncApiForm: false });
    setStatus(String(error.message || error), "warn");
  }
}

async function saveBackendBaseUrl() {
  const nextValue = fields.backendBaseUrl.value.trim();
  const currentValue = String(state.config?.backendBaseUrl || DEFAULTS.backendBaseUrl);

  if (nextValue === currentValue) {
    return true;
  }

  try {
    const response = await sendRuntimeMessage({ type: "save_config", payload: { backendBaseUrl: nextValue } });
    applyConfig(response.config || DEFAULTS, { syncApiForm: true });
    await sendRuntimeMessage({ type: "health_check" });
    setStatus("", "");
    return true;
  } catch (error) {
    setStatus(String(error.message || error), "warn");
    return false;
  }
}

async function switchHostMode(hostMode) {
  try {
    const response = await sendRuntimeMessage({ type: "save_config", payload: { hostMode } });
    applyConfig(response.config || DEFAULTS, { syncApiForm: false });
    setStatus("", "");
  } catch (error) {
    setStatus(String(error.message || error), "warn");
  }
}

function applyTheme(theme) {
  const requestedTheme = theme || state.config?.theme || DEFAULTS.theme;
  const resolvedTheme = requestedTheme === "system"
    ? (systemThemeQuery.matches ? "dark" : "light")
    : requestedTheme;
  document.documentElement.setAttribute("data-options-theme", resolvedTheme);
}

function getOpenModeToggleLabel(hostMode) {
  return hostMode === "popup" ? "Switch to Side Panel" : "Switch to Popup";
}

function getNextHostMode() {
  return state.config?.hostMode === "popup" ? "sidepanel" : "popup";
}

function setStatus(message, kind) {
  const text = String(message || "");
  fields.status.textContent = text;
  fields.status.className = `status${kind ? ` ${kind}` : ""}`;
  fields.status.hidden = !text;
}
