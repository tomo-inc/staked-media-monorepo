(function () {
  const {
    DEFAULT_CONFIG,
    coerceWindowId,
    escapeHtml,
    extractDrafts,
    sendRuntimeMessage
  } = window.StakedMediaExtensionShared;
  const params = new URLSearchParams(window.location.search);
  const HOST_MODE = params.get("host") === "popup" ? "popup" : "sidepanel";

  const SETTINGS_DEFAULTS = { ...DEFAULT_CONFIG };

  const STATE = {
    config: null,
    health: null,
    latencyMs: null,
    generated: null,
    lastGenerateDurationMs: null,
    loading: false,
    composerAvailable: false,
    composerMessage: "Open the X composer to insert drafts.",
    currentWindowId: null,
    targetWindowId: null,
    activeTab: "profile",
    profile: null,
    profileLoading: false
  };

  const root = document.getElementById("app");
  root.innerHTML = buildShell();
  root.firstElementChild?.setAttribute("data-host", HOST_MODE);

  const ui = {
    username: root.querySelector('[data-field="username"]'),
    idea: root.querySelector('[data-field="idea"]'),
    draftCount: root.querySelector('[data-field="draftCount"]'),
    generateButton: root.querySelector('[data-action="generate"]'),
    status: root.querySelector('[data-slot="status"]'),
    results: root.querySelector('[data-slot="results"]'),
    composer: root.querySelector('[data-slot="composer"]'),
    dot: root.querySelector('[data-slot="connection"]'),
    latencyText: root.querySelector('[data-slot="latency-text"]'),
    settingsStatus: root.querySelector('[data-slot="settings-status"]'),
    sBackendBaseUrl: root.querySelector('[data-field="s-backendBaseUrl"]'),
    sApiModeDrafts: root.querySelector('[data-field="s-apiModeDrafts"]'),
    sApiModeContent: root.querySelector('[data-field="s-apiModeContent"]'),
    sDebugLogs: root.querySelector('[data-field="s-debugLogs"]'),
    sTheme: root.querySelector('[data-field="s-theme"]'),
    sHostModeText: root.querySelector('[data-slot="s-host-mode-text"]'),
    profileInfo: root.querySelector('[data-slot="profile-info"]')
  };

  // Tab navigation
  root.querySelectorAll("[data-tab-target]").forEach((btn) => {
    btn.addEventListener("click", () => {
      switchTab(btn.getAttribute("data-tab-target"));
    });
  });

  root.querySelector('[data-action="save-settings"]').addEventListener("click", async () => {
    await saveSettings();
  });

  root.querySelector('[data-action="reset-settings"]').addEventListener("click", async () => {
    await resetSettings();
  });

  root.querySelector('[data-action="switch-sidepanel"]').addEventListener("click", async () => {
    await switchHostMode("sidepanel");
  });

  root.querySelector('[data-action="switch-popup"]').addEventListener("click", async () => {
    await switchHostMode("popup");
  });

  root.querySelector('[data-action="generate"]').addEventListener("click", async () => {
    await handleGenerate();
  });

  root.querySelector('[data-action="clear-results"]').addEventListener("click", () => {
    STATE.generated = null;
    STATE.lastGenerateDurationMs = null;
    render();
  });

  root.querySelector('[data-action="load-profile"]').addEventListener("click", async () => {
    await handleLoadProfile();
  });

  root.querySelector('[data-action="ingest-profile"]').addEventListener("click", async () => {
    await handleIngestProfile();
  });

  switchTab("profile");
  render();
  bootstrap().catch((error) => {
    renderStatus(formatRuntimeError(error), "error");
  });

  setInterval(() => {
    refreshComposerState();
  }, 1500);

  setInterval(() => {
    refreshHealth();
  }, 10000);

  function switchTab(tabName) {
    STATE.activeTab = tabName;
    root.querySelectorAll("[data-tab-target]").forEach((btn) => {
      btn.classList.toggle("smc-tab-active", btn.getAttribute("data-tab-target") === tabName);
    });
    root.querySelectorAll("[data-tab-panel]").forEach((panel) => {
      panel.classList.toggle("smc-tab-panel-active", panel.getAttribute("data-tab-panel") === tabName);
    });
    if (tabName === "settings") {
      loadSettingsUI();
    }
  }

  async function bootstrap() {
    const currentWindow = await chrome.windows.getCurrent();
    STATE.currentWindowId = coerceWindowId(currentWindow?.id);
    STATE.targetWindowId = HOST_MODE === "popup"
      ? await resolvePopupTargetWindowId()
      : STATE.currentWindowId;

    const configResponse = await sendRuntimeMessage({ type: "get_config" });
    STATE.config = configResponse.config;
    hydrateInputs();
    await refreshHealth();
    await refreshComposerState();
    render();
  }

  async function refreshHealth() {
    try {
      const response = await sendRuntimeMessage({ type: "health_check" });
      STATE.health = response.health;
      STATE.latencyMs = response.health?.latencyMs ?? null;
    } catch (_error) {
      STATE.health = null;
      STATE.latencyMs = null;
    }
    renderConnectionDot();
  }

  function loadSettingsUI() {
    const config = STATE.config || {};
    const merged = { ...SETTINGS_DEFAULTS, ...config };
    ui.sBackendBaseUrl.value = merged.backendBaseUrl;
    ui.sDebugLogs.checked = Boolean(merged.debugLogs);
    ui.sTheme.value = merged.theme || "light";
    if (ui.sHostModeText) {
      ui.sHostModeText.textContent = merged.hostMode === "popup" ? "Popup" : "Side Panel";
    }
    if (merged.apiMode === "drafts") {
      ui.sApiModeDrafts.checked = true;
    } else {
      ui.sApiModeContent.checked = true;
    }
  }

  async function saveSettings() {
    try {
      const payload = {
        backendBaseUrl: ui.sBackendBaseUrl.value.trim(),
        apiMode: ui.sApiModeDrafts.checked ? "drafts" : "content",
        debugLogs: ui.sDebugLogs.checked,
        theme: ui.sTheme.value
      };
      const response = await sendRuntimeMessage({ type: "save_config", payload });
      STATE.config = response.config;
      await refreshHealth();
      renderSettingsStatus("Settings saved.", "good");
    } catch (error) {
      renderSettingsStatus(formatRuntimeError(error), "warn");
    }
  }

  async function resetSettings() {
    try {
      const response = await sendRuntimeMessage({ type: "save_config", payload: { ...SETTINGS_DEFAULTS } });
      STATE.config = response.config;
      loadSettingsUI();
      await refreshHealth();
      renderSettingsStatus("Settings reset to defaults. Side Panel is now the default open mode.", "good");
    } catch (error) {
      renderSettingsStatus(formatRuntimeError(error), "warn");
    }
  }

  async function switchHostMode(hostMode) {
    const nextHostMode = hostMode === "popup" ? "popup" : "sidepanel";
    try {
      const response = await sendRuntimeMessage({ type: "save_config", payload: { hostMode: nextHostMode } });
      STATE.config = response.config;
      loadSettingsUI();
      const targetLabel = nextHostMode === "popup" ? "Popup" : "Side Panel";
      if (HOST_MODE === nextHostMode) {
        renderSettingsStatus(`${targetLabel} is already the active shell and remains the default.`, "good");
        return;
      }
      renderSettingsStatus(`${targetLabel} is now the default open mode. Close and reopen the extension from the toolbar to use it.`, "good");
    } catch (error) {
      renderSettingsStatus(formatRuntimeError(error), "warn");
    }
  }

  function renderSettingsStatus(text, kind) {
    if (!ui.settingsStatus) return;
    ui.settingsStatus.textContent = text;
    ui.settingsStatus.className = `smc-settings-status${kind ? ` smc-settings-status-${kind}` : ""}`;
  }

  async function handleLoadProfile() {
    const username = ui.username.value.trim();
    if (!username) {
      renderStatus("Username is required.", "error");
      return;
    }
    STATE.profileLoading = true;
    renderProfileInfo();
    try {
      const response = await sendRuntimeMessage({ type: "check_profile", payload: { username } });
      STATE.profile = response.profile;
      renderProfileInfo();
    } catch (error) {
      STATE.profile = null;
      renderProfileInfo();
      renderStatus(formatRuntimeError(error), "error");
    } finally {
      STATE.profileLoading = false;
      renderProfileInfo();
    }
  }

  async function handleIngestProfile() {
    const username = ui.username.value.trim();
    if (!username) {
      renderStatus("Username is required.", "error");
      return;
    }
    STATE.profileLoading = true;
    renderProfileInfo();
    try {
      const response = await sendRuntimeMessage({ type: "ingest_profile", payload: { username } });
      STATE.profile = {
        exists: true,
        username: response.result.username,
        storedTweetCount: response.result.fetched_tweet_count,
        personaReady: true,
        profile: response.result.profile,
        latestPersonaSnapshot: {
          persona: response.result.persona
        }
      };
      renderProfileInfo();
      renderStatus(`Ingested ${response.result.fetched_tweet_count} tweets. Persona ready.`, "success");
    } catch (error) {
      renderProfileInfo();
      renderStatus(formatRuntimeError(error), "error");
    } finally {
      STATE.profileLoading = false;
      renderProfileInfo();
    }
  }

  async function handleGenerate() {
    const username = ui.username.value.trim();
    const idea = ui.idea.value.trim();
    if (!username) {
      renderStatus("Username is required.", "error");
      return;
    }
    if (!idea) {
      renderStatus("Topic / Idea is required.", "error");
      return;
    }
    const payload = {
      username,
      idea,
      draft_count: ui.draftCount.value
    };
    await runGeneration(payload);
  }

  async function runGeneration(payload) {
    setLoading(true);
    const startedAt = performance.now();
    try {
      const response = await sendRuntimeMessage({
        type: "generate",
        payload
      });
      STATE.generated = response.result;
      STATE.lastGenerateDurationMs = Math.round(performance.now() - startedAt);
      const draftCount = extractDrafts(STATE.generated).length;
      const durationLabel = STATE.lastGenerateDurationMs != null ? ` in ${STATE.lastGenerateDurationMs} ms` : "";
      renderStatus(`Generated ${draftCount} draft${draftCount === 1 ? "" : "s"}${durationLabel}.`, "success");
      render();
    } catch (error) {
      STATE.lastGenerateDurationMs = Math.round(performance.now() - startedAt);
      renderStatus(formatApiError(error), "error");
      render();
    } finally {
      setLoading(false);
    }
  }

  async function refreshComposerState() {
    try {
      const response = await sendRuntimeMessage({
        type: "get_composer_state",
        payload: {
          targetWindowId: STATE.targetWindowId
        }
      });
      STATE.composerAvailable = Boolean(response.composer?.available);
      STATE.composerMessage = response.composer?.message || "Open the X composer to insert drafts.";
      renderComposerState();
    } catch (_error) {
      STATE.composerAvailable = false;
      STATE.composerMessage = "Unable to reach the active tab.";
      renderComposerState();
    }
  }

  function hydrateInputs() {
    ui.username.value = ui.username.value.trim() || STATE.config?.defaultUsername || "";
    if (!ui.draftCount.value) {
      ui.draftCount.value = "3";
    }
  }

  function render() {
    renderGenerateButton();
    renderConnectionDot();
    renderProfileInfo();
    renderResults();
    renderComposerState();
  }

  function renderGenerateButton() {
    if (!ui.generateButton) {
      return;
    }
    ui.generateButton.classList.toggle("smc-button-loading", STATE.loading);
    ui.generateButton.setAttribute("aria-busy", STATE.loading ? "true" : "false");
    ui.generateButton.innerHTML = STATE.loading
      ? '<span class="smc-button-content"><span class="smc-button-spinner" aria-hidden="true"></span><span>Generating</span></span>'
      : "Generate";
  }

  function renderConnectionDot() {
    const dot = ui.dot;
    const latencyEl = ui.latencyText;
    if (!dot) return;
    if (STATE.health === null && STATE.latencyMs === null) {
      dot.className = "smc-status-dot smc-dot-warn";
      dot.title = "Checking...";
      if (latencyEl) latencyEl.textContent = "--";
    } else if (STATE.health?.status === "ok") {
      dot.className = "smc-status-dot smc-dot-ok";
      dot.title = STATE.latencyMs != null ? `Connected ${STATE.latencyMs}ms` : "Connected";
      if (latencyEl) latencyEl.textContent = STATE.latencyMs != null ? `${STATE.latencyMs}ms` : "";
    } else {
      dot.className = "smc-status-dot smc-dot-err";
      dot.title = "Disconnected";
      if (latencyEl) latencyEl.textContent = "";
    }
  }

  function renderProfileInfo() {
    if (!ui.profileInfo) return;
    if (STATE.profileLoading) {
      ui.profileInfo.innerHTML = '<div class="smc-profile-hint">Loading profile...</div>';
      return;
    }
    if (!STATE.profile) {
      ui.profileInfo.innerHTML = '';
      return;
    }
    if (!STATE.profile.exists) {
      ui.profileInfo.innerHTML = '<div class="smc-profile-hint smc-profile-hint-warn">Profile not found. Click Ingest to fetch tweets and build persona.</div>';
      return;
    }
    const p = STATE.profile.profile || {};

    if (!STATE.profile.personaReady) {
      ui.profileInfo.innerHTML = '<div class="smc-profile-hint smc-profile-hint-warn">Profile loaded, but persona is missing. Click Ingest to build persona.</div>';
      return;
    }

    const personaStatus = STATE.profile.personaReady ? "Ready" : "Missing";
    const personaClass = STATE.profile.personaReady ? "smc-profile-status-ok" : "smc-profile-status-warn";

    let personaSection = '';
    if (STATE.profile.personaReady && STATE.profile.latestPersonaSnapshot?.persona) {
      const persona = STATE.profile.latestPersonaSnapshot.persona;
      personaSection = `
        <div class="smc-persona-section">
          <div class="smc-persona-title">Persona Portrait</div>
          ${persona.author_summary ? `<div class="smc-persona-item"><strong>Summary:</strong> ${escapeHtml(persona.author_summary)}</div>` : ''}
          ${persona.voice_traits?.length ? `<div class="smc-persona-item"><strong>Voice:</strong> ${escapeHtml(persona.voice_traits.join(', '))}</div>` : ''}
          ${persona.topic_clusters?.length ? `<div class="smc-persona-item"><strong>Topics:</strong> ${escapeHtml(persona.topic_clusters.map(t => t.label || t.name || '').filter(Boolean).join(', '))}</div>` : ''}
        </div>
      `;
    }

    ui.profileInfo.innerHTML = `
      <div class="smc-profile-card">
        <div class="smc-profile-header">
          <strong>Profile</strong>
          <span class="smc-profile-username">@${escapeHtml(STATE.profile.username)}</span>
        </div>
        <div class="smc-profile-row">
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">Followers</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(p.followers_count || 0))}</span>
          </div>
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">Following</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(p.following_count || 0))}</span>
          </div>
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">Tweets</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(STATE.profile.storedTweetCount || 0))}</span>
          </div>
        </div>
        ${personaSection}
        <div class="smc-profile-footer">
          <span class="smc-profile-status ${personaClass}">Persona: ${personaStatus}</span>
        </div>
      </div>
    `;
  }

  function renderResults() {
    const timingHtml = STATE.lastGenerateDurationMs != null
      ? `
          <div class="smc-result-meta">
            <span class="smc-result-meta-label">Response time</span>
            <span class="smc-result-meta-value">${escapeHtml(`${STATE.lastGenerateDurationMs} ms`)}</span>
          </div>
        `
      : "";
    const drafts = extractDrafts(STATE.generated);
    if (!drafts.length) {
      ui.results.innerHTML = `${timingHtml}<div class="smc-empty">No generated drafts yet.</div>`;
      return;
    }
    ui.results.innerHTML = `
      ${timingHtml}
      ${drafts
        .map((draft, index) => {
          const text = typeof draft === "string" ? draft : draft.text || "";
          return `
            <article class="smc-draft-card">
              <div class="smc-draft-head">
                <span class="smc-draft-label">Draft #${index + 1}</span>
                <div class="smc-draft-actions">
                  <button class="smc-outline-button" data-copy-index="${index}">Copy</button>
                  <button class="smc-outline-button" data-insert-index="${index}">Insert</button>
                </div>
              </div>
              <p class="smc-draft-text">${escapeHtml(text)}</p>
            </article>
          `;
        })
        .join("")}
    `;

    ui.results.querySelectorAll("[data-copy-index]").forEach((button) => {
      button.addEventListener("click", async () => {
        const index = Number.parseInt(button.getAttribute("data-copy-index"), 10);
        const text = getDraftText(drafts, index);
        if (!text) return;
        try {
          await navigator.clipboard.writeText(text);
          renderStatus("Copied to clipboard.", "success");
        } catch (_error) {
          renderStatus("Failed to copy.", "error");
        }
      });
    });

    ui.results.querySelectorAll("[data-insert-index]").forEach((button) => {
      button.addEventListener("click", async () => {
        const index = Number.parseInt(button.getAttribute("data-insert-index"), 10);
        const text = getDraftText(drafts, index);
        if (!text) {
          renderStatus("Draft text is missing.", "error");
          return;
        }
        try {
          await sendRuntimeMessage({
            type: "insert_text",
            payload: {
              text,
              targetWindowId: STATE.targetWindowId
            }
          });
          renderStatus("Inserted draft into the X composer.", "success");
          await refreshComposerState();
        } catch (error) {
          renderStatus(formatRuntimeError(error), "error");
        }
      });
    });
  }

  function renderComposerState() {
    const className = STATE.composerAvailable ? "smc-pill smc-pill-good" : "smc-pill smc-pill-warn";
    ui.composer.innerHTML = `<span class="${className}">${escapeHtml(STATE.composerMessage)}</span>`;
  }

  function getDraftText(drafts, index) {
    const draft = drafts[index];
    if (!draft) return "";
    if (typeof draft === "string") return draft;
    return String(draft.text || "");
  }

  function setLoading(nextLoading) {
    STATE.loading = nextLoading;
    root.querySelectorAll("button").forEach((button) => {
      if (button.hasAttribute("data-copy-index") || button.hasAttribute("data-insert-index")) {
        return;
      }
      button.disabled = nextLoading;
    });
    renderGenerateButton();
  }

  function renderStatus(text, level) {
    if (!text) {
      ui.status.innerHTML = "";
      return;
    }
    ui.status.innerHTML = `<div class="smc-banner smc-banner-${level || "info"}">${escapeHtml(text)}</div>`;
  }

  function formatApiError(error) {
    if (error?.status === 404) {
      return "Profile not found in the backend. Run ingest first.";
    }
    if (error?.status === 409) {
      return "Persona is missing in the backend. Re-run ingest before generating.";
    }
    if (error?.status === 422) {
      return "The backend rejected the request. Check your input and try again.";
    }
    if (error?.status === 502) {
      return "The backend failed while calling upstream services. Retry once the service is healthy.";
    }
    return formatRuntimeError(error);
  }

  function formatRuntimeError(error) {
    return String(error?.message || error || "Unknown error");
  }

  async function resolvePopupTargetWindowId() {
    try {
      const [activeTab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
      return coerceWindowId(activeTab?.windowId);
    } catch (_error) {
      return null;
    }
  }

  function buildShell() {
    const hostLabel = HOST_MODE === "popup" ? "Popup" : "Side Panel";
    return `
      <div class="smc-shell">
        <aside class="smc-panel">
          <header class="smc-header">
            <div class="smc-header-left">
              <h1 class="smc-title">X Copilot</h1>
              <span class="smc-pill">${escapeHtml(hostLabel)}</span>
            </div>
            <div class="smc-header-right">
              <span class="smc-latency-text" data-slot="latency-text">--</span>
              <span class="smc-status-dot smc-dot-warn" data-slot="connection" title="Checking..."></span>
            </div>
          </header>

          <nav class="smc-tab-bar">
            <button class="smc-tab smc-tab-active" data-tab-target="profile" type="button">Profile</button>
            <button class="smc-tab" data-tab-target="draft" type="button">Draft</button>
            <button class="smc-tab" data-tab-target="settings" type="button">Settings</button>
          </nav>

          <div class="smc-tab-panel smc-tab-panel-active" data-tab-panel="profile">
            <section class="smc-section">
              <div class="smc-username-row">
                <input class="smc-input" data-field="username" placeholder="@Username" type="text">
                <button class="smc-button smc-button-secondary" data-action="load-profile" type="button">Load</button>
                <button class="smc-button smc-button-secondary" data-action="ingest-profile" type="button">Ingest</button>
              </div>
              <div data-slot="profile-info"></div>
            </section>
          </div>

          <div class="smc-tab-panel" data-tab-panel="draft">
            <section class="smc-section">
              <label class="smc-label">
                Topic / Idea
                <textarea class="smc-textarea" data-field="idea" placeholder="Can Bitcoin be cracked in 9 minutes?&#10;Google warns ECC timeline may arrive earlier&#10;Attack threshold could be 20x lower"></textarea>
              </label>
              <label class="smc-label">
                Draft Count
                <input class="smc-input smc-input-short" data-field="draftCount" min="1" max="10" step="1" type="number" value="3">
              </label>
              <div class="smc-button-row">
                <button class="smc-button smc-button-primary" data-action="generate" type="button">Generate</button>
              </div>
            </section>

            <section class="smc-section">
              <div data-slot="status"></div>
            </section>

            <section class="smc-section">
              <div class="smc-section-head">
                <h2>Result</h2>
                <div class="smc-section-head-right">
                  <div data-slot="composer"></div>
                  <button class="smc-link-button" data-action="clear-results" type="button">Clear</button>
                </div>
              </div>
              <div data-slot="results"></div>
            </section>
          </div>

          <div class="smc-tab-panel" data-tab-panel="settings">
            <section class="smc-section">
              <label class="smc-label">
                API Base URL
                <input class="smc-input" data-field="s-backendBaseUrl" type="text" placeholder="http://127.0.0.1:8000">
              </label>
              <label class="smc-label">
                Generation API Mode
              </label>
              <div class="smc-radio-group">
                <label class="smc-radio-option">
                  <input type="radio" name="s-apiMode" data-field="s-apiModeDrafts" value="drafts">
                  Drafts API (/api/v1/drafts/generate)
                </label>
                <label class="smc-radio-option">
                  <input type="radio" name="s-apiMode" data-field="s-apiModeContent" value="content" checked>
                  Content API (/api/v1/content/generate)
                </label>
              </div>
              <div class="smc-toggle-row">
                <span class="smc-toggle-label">Enable Debug Logs</span>
                <label class="smc-toggle">
                  <input type="checkbox" data-field="s-debugLogs">
                  <span class="smc-toggle-track"></span>
                  <span class="smc-toggle-thumb"></span>
                </label>
              </div>
              <label class="smc-label">
                Theme
                <select class="smc-input" data-field="s-theme">
                  <option value="light">Light</option>
                </select>
              </label>
              <label class="smc-label">
                Default Open Mode
              </label>
              <div class="smc-mode-card">
                <div class="smc-mode-copy">
                  <div class="smc-mode-title">Current default</div>
                  <div class="smc-mode-value" data-slot="s-host-mode-text">Side Panel</div>
                </div>
                <div class="smc-button-row smc-button-row-tight">
                  <button class="smc-button smc-button-secondary" data-action="switch-sidepanel" type="button">Switch to Side Panel</button>
                  <button class="smc-button smc-button-secondary" data-action="switch-popup" type="button">Switch to Popup</button>
                </div>
              </div>
              <div class="smc-button-row">
                <button class="smc-button smc-button-primary" data-action="save-settings" type="button">Save</button>
                <button class="smc-button smc-button-secondary" data-action="reset-settings" type="button">Reset</button>
              </div>
              <div class="smc-settings-status" data-slot="settings-status"></div>
            </section>
          </div>

        </aside>
      </div>
    `;
  }
})();
