const { DEFAULT_CONFIG, sendRuntimeMessage } = window.StakedMediaExtensionShared;
const DEFAULTS = { ...DEFAULT_CONFIG };

const fields = {
  backendBaseUrl: document.getElementById("backendBaseUrl"),
  apiModeDrafts: document.getElementById("apiModeDrafts"),
  apiModeContent: document.getElementById("apiModeContent"),
  debugLogs: document.getElementById("debugLogs"),
  theme: document.getElementById("theme"),
  hostModeValue: document.getElementById("hostModeValue"),
  switchToSidePanelButton: document.getElementById("switchToSidePanelButton"),
  switchToPopupButton: document.getElementById("switchToPopupButton"),
  saveButton: document.getElementById("saveButton"),
  resetButton: document.getElementById("resetButton"),
  status: document.getElementById("status")
};

init().catch((error) => {
  setStatus(String(error.message || error), "warn");
});

fields.saveButton.addEventListener("click", async () => {
  try {
    const config = await saveCurrentConfig();
    applyConfig(config);
    const healthResponse = await sendRuntimeMessage({ type: "health_check" });
    const latency = healthResponse.health?.latencyMs;
    const latencyText = latency != null ? ` (${latency}ms)` : "";
    setStatus(`Settings saved. Backend reachable at ${healthResponse.health.baseUrl}${latencyText}`, "good");
  } catch (error) {
    setStatus(String(error.message || error), "warn");
  }
});

fields.resetButton.addEventListener("click", async () => {
  try {
    const config = await sendRuntimeMessage({ type: "save_config", payload: { ...DEFAULTS } });
    applyConfig(config.config || DEFAULTS);
    setStatus("Settings reset to defaults. Side Panel is now the default open mode.", "good");
  } catch (error) {
    setStatus(String(error.message || error), "warn");
  }
});

fields.switchToSidePanelButton.addEventListener("click", async () => {
  await switchHostMode("sidepanel");
});

fields.switchToPopupButton.addEventListener("click", async () => {
  await switchHostMode("popup");
});

async function init() {
  const response = await sendRuntimeMessage({ type: "get_config" });
  applyConfig(response.config || DEFAULTS);
  setStatus("Settings loaded.", "");
}

function applyConfig(config) {
  const next = { ...DEFAULTS, ...config };
  fields.backendBaseUrl.value = next.backendBaseUrl;
  fields.debugLogs.checked = Boolean(next.debugLogs);
  fields.theme.value = next.theme || "light";
  fields.hostModeValue.textContent = next.hostMode === "popup" ? "Popup" : "Side Panel";
  if (next.apiMode === "drafts") {
    fields.apiModeDrafts.checked = true;
  } else {
    fields.apiModeContent.checked = true;
  }
}

async function saveCurrentConfig() {
  const apiMode = fields.apiModeDrafts.checked ? "drafts" : "content";
  const payload = {
    backendBaseUrl: fields.backendBaseUrl.value.trim(),
    apiMode,
    debugLogs: fields.debugLogs.checked,
    theme: fields.theme.value
  };
  const response = await sendRuntimeMessage({ type: "save_config", payload });
  return response.config;
}

async function switchHostMode(hostMode) {
  try {
    const response = await sendRuntimeMessage({ type: "save_config", payload: { hostMode } });
    applyConfig(response.config || DEFAULTS);
    const label = hostMode === "popup" ? "Popup" : "Side Panel";
    setStatus(`${label} is now the default open mode. Reopen the extension from the toolbar to use it.`, "good");
  } catch (error) {
    setStatus(String(error.message || error), "warn");
  }
}

function setStatus(message, kind) {
  fields.status.textContent = message;
  fields.status.className = `status${kind ? ` ${kind}` : ""}`;
}
