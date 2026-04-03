(function () {
	const {
		DEFAULT_CONFIG,
		coerceWindowId,
		escapeHtml,
		extractDrafts,
		sendRuntimeMessage,
	} = window.StakedMediaExtensionShared;
	const { buildPanelShell, deriveConnectionIndicator, isWhitelistDeniedError } =
		window.StakedMediaPanelHelpers;
	const params = new URLSearchParams(window.location.search);
	const HOST_MODE = params.get("host") === "popup" ? "popup" : "sidepanel";
	const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

	const SETTINGS_DEFAULTS = { ...DEFAULT_CONFIG };

	const STATE = {
		config: null,
		health: null,
		latencyMs: null,
		healthState: "loading",
		generated: null,
		lastGenerateDurationMs: null,
		loading: false,
		composerAvailable: false,
		composerMessage: "Open the X composer to insert drafts.",
		currentWindowId: null,
		targetWindowId: null,
		currentView: "main",
		settingsPage: "home",
		activeTab: "profile",
		profile: null,
		profileLoading: false,
		usernameError: "",
		generationProgress: null,
		generationProgressTimer: null,
		generationStartedAt: null,
	};

	const root = document.getElementById("app");
	root.innerHTML = buildPanelShell();
	root.firstElementChild?.setAttribute("data-host", HOST_MODE);

	const ui = {
		headerTitle: root.querySelector('[data-slot="header-title"]'),
		username: root.querySelector('[data-field="username"]'),
		idea: root.querySelector('[data-field="idea"]'),
		draftCount: root.querySelector('[data-field="draftCount"]'),
		generateButton: root.querySelector('[data-action="generate"]'),
		openSettingsButton: root.querySelector('[data-action="open-settings"]'),
		closeSettingsButton: root.querySelector('[data-action="close-settings"]'),
		openApiSettingsButton: root.querySelector(
			'[data-action="open-api-settings"]',
		),
		toggleOpenModeButton: root.querySelector(
			'[data-action="toggle-open-mode"]',
		),
		statusSection: root.querySelector('[data-slot="status-section"]'),
		status: root.querySelector('[data-slot="status"]'),
		usernameError: root.querySelector('[data-slot="username-error"]'),
		results: root.querySelector('[data-slot="results"]'),
		composer: root.querySelector('[data-slot="composer"]'),
		dot: root.querySelector('[data-slot="connection"]'),
		latencyText: root.querySelector('[data-slot="latency-text"]'),
		settingsStatusSection: root.querySelector(".smc-settings-status-section"),
		settingsStatus: root.querySelector('[data-slot="settings-status"]'),
		sBackendBaseUrl: root.querySelector('[data-field="s-backendBaseUrl"]'),
		sApiModeDrafts: root.querySelector('[data-field="s-apiModeDrafts"]'),
		sApiModeContent: root.querySelector('[data-field="s-apiModeContent"]'),
		sTheme: root.querySelector('[data-field="s-theme"]'),
		sHostModeTitle: root.querySelector('[data-slot="s-host-mode-title"]'),
		profileInfo: root.querySelector('[data-slot="profile-info"]'),
		views: root.querySelectorAll("[data-view]"),
		settingsPages: root.querySelectorAll("[data-settings-view]"),
	};

	// Tab navigation
	root.querySelectorAll("[data-tab-target]").forEach((btn) => {
		btn.addEventListener("click", () => {
			switchTab(btn.getAttribute("data-tab-target"));
		});
	});

	ui.openSettingsButton.addEventListener("click", () => {
		openSettingsView();
	});

	ui.closeSettingsButton.addEventListener("click", async () => {
		await closeSettingsView();
	});

	ui.openApiSettingsButton.addEventListener("click", () => {
		openApiSettingsPage();
	});

	ui.toggleOpenModeButton.addEventListener("click", async () => {
		await switchHostMode(getNextHostMode());
	});

	ui.sTheme.addEventListener("change", async () => {
		await saveTheme(ui.sTheme.value);
	});

	ui.sApiModeDrafts.addEventListener("change", async () => {
		if (ui.sApiModeDrafts.checked) {
			await saveApiMode("drafts");
		}
	});

	ui.sApiModeContent.addEventListener("change", async () => {
		if (ui.sApiModeContent.checked) {
			await saveApiMode("content");
		}
	});

	ui.sBackendBaseUrl.addEventListener("blur", async () => {
		await saveBackendBaseUrl();
	});

	ui.sBackendBaseUrl.addEventListener("keydown", (event) => {
		if (event.key !== "Enter") {
			return;
		}
		event.preventDefault();
		ui.sBackendBaseUrl.blur();
	});

	ui.username.addEventListener("input", () => {
		if (!STATE.usernameError) {
			return;
		}
		renderUsernameError("");
	});

	root
		.querySelector('[data-action="generate"]')
		.addEventListener("click", async () => {
			await handleGenerate();
		});

	root
		.querySelector('[data-action="clear-results"]')
		.addEventListener("click", () => {
			STATE.generated = null;
			STATE.lastGenerateDurationMs = null;
			render();
		});

	root
		.querySelector('[data-action="load-profile"]')
		.addEventListener("click", async () => {
			await handleLoadProfile();
		});

	root
		.querySelector('[data-action="ingest-profile"]')
		.addEventListener("click", async () => {
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

	if (typeof systemThemeQuery.addEventListener === "function") {
		systemThemeQuery.addEventListener("change", () => {
			if ((STATE.config?.theme || SETTINGS_DEFAULTS.theme) === "system") {
				applyTheme("system");
			}
		});
	}

	function switchTab(tabName) {
		STATE.activeTab = tabName;
		root.querySelectorAll("[data-tab-target]").forEach((btn) => {
			btn.classList.toggle(
				"smc-tab-active",
				btn.getAttribute("data-tab-target") === tabName,
			);
		});
		root.querySelectorAll("[data-tab-panel]").forEach((panel) => {
			panel.classList.toggle(
				"smc-tab-panel-active",
				panel.getAttribute("data-tab-panel") === tabName,
			);
		});
	}

	function openSettingsView() {
		STATE.currentView = "settings";
		STATE.settingsPage = "home";
		loadSettingsUI({ syncApiForm: true });
		renderView();
	}

	function openApiSettingsPage() {
		STATE.currentView = "settings";
		STATE.settingsPage = "api";
		loadSettingsUI({ syncApiForm: true });
		renderView();
	}

	async function closeSettingsView() {
		if (STATE.currentView !== "settings") {
			return;
		}
		if (STATE.settingsPage === "api") {
			const saved = await saveBackendBaseUrl();
			if (!saved) {
				return;
			}
			STATE.settingsPage = "home";
			renderView();
			return;
		}
		STATE.currentView = "main";
		renderView();
	}

	async function bootstrap() {
		const currentWindow = await chrome.windows.getCurrent();
		STATE.currentWindowId = coerceWindowId(currentWindow?.id);
		STATE.targetWindowId =
			HOST_MODE === "popup"
				? await resolvePopupTargetWindowId()
				: STATE.currentWindowId;

		const configResponse = await sendRuntimeMessage({ type: "get_config" });
		STATE.config = configResponse.config;
		applyTheme(STATE.config?.theme);
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
			STATE.healthState = "ready";
		} catch (_error) {
			STATE.health = null;
			STATE.latencyMs = null;
			STATE.healthState = "error";
		}
		renderConnectionDot();
	}

	function loadSettingsUI(options = {}) {
		const syncApiForm = options.syncApiForm !== false;
		const config = STATE.config || {};
		const merged = { ...SETTINGS_DEFAULTS, ...config };
		if (syncApiForm) {
			ui.sBackendBaseUrl.value = merged.backendBaseUrl;
			if (merged.apiMode === "drafts") {
				ui.sApiModeDrafts.checked = true;
			} else {
				ui.sApiModeContent.checked = true;
			}
		}
		ui.sTheme.value = merged.theme || "light";
		if (ui.sHostModeTitle) {
			ui.sHostModeTitle.textContent = getOpenModeToggleLabel(merged.hostMode);
		}
	}

	async function saveTheme(theme) {
		try {
			const response = await sendRuntimeMessage({
				type: "save_config",
				payload: { theme },
			});
			STATE.config = response.config;
			applyTheme(STATE.config.theme);
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus("", "");
		} catch (error) {
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus(formatRuntimeError(error), "warn");
		}
	}

	async function saveApiMode(apiMode) {
		try {
			const response = await sendRuntimeMessage({
				type: "save_config",
				payload: { apiMode },
			});
			STATE.config = response.config;
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus("", "");
		} catch (error) {
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus(formatRuntimeError(error), "warn");
		}
	}

	async function saveBackendBaseUrl() {
		const nextValue = ui.sBackendBaseUrl.value.trim();
		const currentValue = String(
			STATE.config?.backendBaseUrl || SETTINGS_DEFAULTS.backendBaseUrl,
		);
		if (nextValue === currentValue) {
			return true;
		}
		try {
			const response = await sendRuntimeMessage({
				type: "save_config",
				payload: { backendBaseUrl: nextValue },
			});
			STATE.config = response.config;
			loadSettingsUI({ syncApiForm: true });
			await refreshHealth();
			renderSettingsStatus("", "");
			return true;
		} catch (error) {
			renderSettingsStatus(formatRuntimeError(error), "warn");
			return false;
		}
	}

	async function switchHostMode(hostMode) {
		const nextHostMode = hostMode === "popup" ? "popup" : "sidepanel";
		try {
			if (HOST_MODE === "sidepanel" && nextHostMode === "popup") {
				await switchSidePanelToPopup();
				return;
			}
			if (HOST_MODE === "popup" && nextHostMode === "sidepanel") {
				await switchPopupToSidePanel();
				return;
			}
			await persistHostMode(nextHostMode);
		} catch (error) {
			renderSettingsStatus(formatRuntimeError(error), "warn");
		}
	}

	async function persistHostMode(hostMode) {
		const response = await sendRuntimeMessage({
			type: "save_config",
			payload: { hostMode },
		});
		STATE.config = response.config;
		loadSettingsUI({ syncApiForm: false });
		renderSettingsStatus("", "");
		return response.config;
	}

	async function switchSidePanelToPopup() {
		await persistHostMode("popup");
		await closeCurrentSidePanelShell();
	}

	async function switchPopupToSidePanel() {
		const targetWindowId = coerceWindowId(STATE.targetWindowId);
		if (!targetWindowId) {
			renderSettingsStatus(
				"Could not find a browser window for Side Panel. Try again.",
				"warn",
			);
			return;
		}

		try {
			await openSidePanelInWindow(targetWindowId);
		} catch (error) {
			renderSettingsStatus(formatRuntimeError(error), "warn");
			return;
		}

		try {
			await persistHostMode("sidepanel");
		} catch (error) {
			await closeSidePanelInWindow(targetWindowId);
			renderSettingsStatus(formatRuntimeError(error), "warn");
			return;
		}

		window.close();
	}

	function renderSettingsStatus(text, kind) {
		if (!ui.settingsStatus) return;
		const message = String(text || "");
		ui.settingsStatus.textContent = message;
		ui.settingsStatus.className = `smc-settings-status${kind ? ` smc-settings-status-${kind}` : ""}`;
		if (ui.settingsStatusSection) {
			ui.settingsStatusSection.hidden = !message;
		}
	}

	async function handleLoadProfile() {
		const username = ui.username.value.trim();
		if (!username) {
			renderStatus("Username is required.", "error");
			return;
		}
		renderUsernameError("");
		renderStatus("", "");
		STATE.profileLoading = true;
		renderProfileInfo();
		try {
			const response = await sendRuntimeMessage({
				type: "check_profile",
				payload: { username },
			});
			STATE.profile = response.profile;
			renderUsernameError("");
			renderStatus("", "");
			renderProfileInfo();
		} catch (error) {
			STATE.profile = null;
			renderProfileInfo();
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			} else {
				renderStatus(formatRuntimeError(error), "error");
			}
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
		renderUsernameError("");
		renderStatus("", "");
		STATE.profileLoading = true;
		renderProfileInfo();
		try {
			const response = await sendRuntimeMessage({
				type: "ingest_profile",
				payload: { username },
			});
			STATE.profile = {
				exists: true,
				username: response.result.username,
				storedTweetCount: response.result.fetched_tweet_count,
				personaReady: true,
				profile: response.result.profile,
				latestPersonaSnapshot: {
					persona: response.result.persona,
				},
			};
			renderUsernameError("");
			renderProfileInfo();
			renderStatus(
				`Ingested ${response.result.fetched_tweet_count} tweets. Persona ready.`,
				"success",
			);
		} catch (error) {
			renderProfileInfo();
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			} else {
				renderStatus(formatRuntimeError(error), "error");
			}
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
			draft_count: ui.draftCount.value,
		};
		renderUsernameError("");
		renderStatus("", "");
		await runGeneration(payload);
	}

	async function runGeneration(payload) {
		setLoading(true);
		const startedAt = performance.now();
		try {
			const response = await sendRuntimeMessage({
				type: "generate",
				payload,
			});
			STATE.generated = response.result;
			STATE.lastGenerateDurationMs = Math.round(performance.now() - startedAt);
			const draftCount = extractDrafts(STATE.generated).length;
			const durationLabel =
				STATE.lastGenerateDurationMs != null
					? ` in ${STATE.lastGenerateDurationMs} ms`
					: "";
			renderStatus(
				`Generated ${draftCount} draft${draftCount === 1 ? "" : "s"}${durationLabel}.`,
				"success",
			);
			render();
		} catch (error) {
			STATE.lastGenerateDurationMs = Math.round(performance.now() - startedAt);
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			}
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
					targetWindowId: STATE.targetWindowId,
				},
			});
			STATE.composerAvailable = Boolean(response.composer?.available);
			STATE.composerMessage =
				response.composer?.message || "Open the X composer to insert drafts.";
			renderComposerState();
		} catch (_error) {
			STATE.composerAvailable = false;
			STATE.composerMessage = "Unable to reach the active tab.";
			renderComposerState();
		}
	}

	function hydrateInputs() {
		ui.username.value =
			ui.username.value.trim() || STATE.config?.defaultUsername || "";
		if (!ui.draftCount.value) {
			ui.draftCount.value = "3";
		}
	}

	function render() {
		renderView();
		renderGenerateButton();
		renderConnectionDot();
		renderUsernameError(STATE.usernameError);
		renderProfileInfo();
		renderResults();
		renderComposerState();
	}

	function renderView() {
		const isSettingsView = STATE.currentView === "settings";
		ui.views.forEach((view) => {
			view.classList.toggle(
				"smc-view-active",
				view.getAttribute("data-view") === STATE.currentView,
			);
		});
		ui.settingsPages.forEach((page) => {
			page.classList.toggle(
				"smc-settings-page-active",
				page.getAttribute("data-settings-view") === STATE.settingsPage,
			);
		});
		if (ui.headerTitle) {
			if (!isSettingsView) {
				ui.headerTitle.textContent = "X Copilot";
			} else if (STATE.settingsPage === "api") {
				ui.headerTitle.textContent = "API & Generation";
			} else {
				ui.headerTitle.textContent = "Settings";
			}
		}
		if (ui.openSettingsButton) {
			ui.openSettingsButton.hidden = isSettingsView;
		}
		if (ui.closeSettingsButton) {
			ui.closeSettingsButton.hidden = !isSettingsView;
			ui.closeSettingsButton.setAttribute(
				"aria-label",
				STATE.settingsPage === "api" ? "Back to settings" : "Back to main view",
			);
		}
	}

	function applyTheme(theme) {
		const requestedTheme =
			theme || STATE.config?.theme || SETTINGS_DEFAULTS.theme;
		const resolvedTheme =
			requestedTheme === "system"
				? systemThemeQuery.matches
					? "dark"
					: "light"
				: requestedTheme;
		document.documentElement.setAttribute("data-smc-theme", resolvedTheme);
	}

	function getOpenModeToggleLabel(hostMode) {
		return hostMode === "popup" ? "Switch to Side Panel" : "Switch to Popup";
	}

	function getNextHostMode() {
		return STATE.config?.hostMode === "popup" ? "sidepanel" : "popup";
	}

	function renderGenerateButton() {
		if (!ui.generateButton) {
			return;
		}
		ui.generateButton.classList.toggle("smc-button-loading", STATE.loading);
		ui.generateButton.setAttribute(
			"aria-busy",
			STATE.loading ? "true" : "false",
		);
		ui.generateButton.innerHTML = STATE.loading
			? '<span class="smc-button-content"><span class="smc-button-spinner" aria-hidden="true"></span><span>Generating</span></span>'
			: "Generate";
	}

	function renderConnectionDot() {
		const dot = ui.dot;
		const latencyEl = ui.latencyText;
		if (!dot) return;
		const indicator = deriveConnectionIndicator({
			health: STATE.health,
			latencyMs: STATE.latencyMs,
			healthState: STATE.healthState,
		});
		dot.className = indicator.className;
		dot.title = indicator.title;
		if (latencyEl) latencyEl.textContent = indicator.latencyText;
	}

	function renderUsernameError(text) {
		STATE.usernameError = String(text || "");
		if (!ui.usernameError) {
			return;
		}
		ui.usernameError.textContent = STATE.usernameError;
		ui.usernameError.hidden = !STATE.usernameError;
	}

	function renderProfileInfo() {
		if (!ui.profileInfo) return;
		if (STATE.profileLoading) {
			ui.profileInfo.innerHTML =
				'<div class="smc-profile-hint">Loading profile...</div>';
			return;
		}
		if (!STATE.profile) {
			ui.profileInfo.innerHTML = "";
			return;
		}
		if (!STATE.profile.exists) {
			ui.profileInfo.innerHTML =
				'<div class="smc-profile-hint smc-profile-hint-warn">Profile not found. Click Ingest to fetch tweets and build persona.</div>';
			return;
		}
		const p = STATE.profile.profile || {};

		if (!STATE.profile.personaReady) {
			ui.profileInfo.innerHTML =
				'<div class="smc-profile-hint smc-profile-hint-warn">Profile loaded, but persona is missing. Click Ingest to build persona.</div>';
			return;
		}

		const personaStatus = STATE.profile.personaReady ? "Ready" : "Missing";
		const personaClass = STATE.profile.personaReady
			? "smc-profile-status-ok"
			: "smc-profile-status-warn";

		let personaSection = "";
		if (
			STATE.profile.personaReady &&
			STATE.profile.latestPersonaSnapshot?.persona
		) {
			const persona = STATE.profile.latestPersonaSnapshot.persona;
			personaSection = `
        <div class="smc-persona-section">
          <div class="smc-persona-title">Persona Portrait</div>
          ${persona.author_summary ? `<div class="smc-persona-item"><strong>Summary:</strong> ${escapeHtml(persona.author_summary)}</div>` : ""}
          ${persona.voice_traits?.length ? `<div class="smc-persona-item"><strong>Voice:</strong> ${escapeHtml(persona.voice_traits.join(", "))}</div>` : ""}
          ${
						persona.topic_clusters?.length
							? `<div class="smc-persona-item"><strong>Topics:</strong> ${escapeHtml(
									persona.topic_clusters
										.map((t) => t.label || t.name || "")
										.filter(Boolean)
										.join(", "),
								)}</div>`
							: ""
					}
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
		const timingHtml =
			STATE.lastGenerateDurationMs != null
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
				const index = Number.parseInt(
					button.getAttribute("data-copy-index"),
					10,
				);
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
				const index = Number.parseInt(
					button.getAttribute("data-insert-index"),
					10,
				);
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
							targetWindowId: STATE.targetWindowId,
						},
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
		const className = STATE.composerAvailable
			? "smc-pill smc-pill-good"
			: "smc-pill smc-pill-warn";
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
		if (nextLoading) {
			startGenerationProgress();
		} else {
			stopGenerationProgress();
		}
		root.querySelectorAll("button").forEach((button) => {
			if (
				button.hasAttribute("data-copy-index") ||
				button.hasAttribute("data-insert-index")
			) {
				return;
			}
			button.disabled = nextLoading;
		});
		renderGenerateButton();
	}

	function startGenerationProgress() {
		stopGenerationProgress();
		STATE.generationStartedAt = Date.now();
		STATE.generationProgress = {
			percent: 8,
			message: "Preparing request...",
		};
		renderGenerationProgress();
		STATE.generationProgressTimer = window.setInterval(() => {
			if (!STATE.loading || !STATE.generationStartedAt) {
				return;
			}
			const elapsedMs = Date.now() - STATE.generationStartedAt;
			const nextPercent = deriveProgressPercent(elapsedMs);
			const nextMessage = deriveProgressMessage(nextPercent);
			if (
				nextPercent === STATE.generationProgress?.percent &&
				nextMessage === STATE.generationProgress?.message
			) {
				return;
			}
			STATE.generationProgress = {
				percent: nextPercent,
				message: nextMessage,
			};
			renderGenerationProgress();
		}, 120);
	}

	function stopGenerationProgress() {
		if (STATE.generationProgressTimer != null) {
			window.clearInterval(STATE.generationProgressTimer);
			STATE.generationProgressTimer = null;
		}
		STATE.generationStartedAt = null;
		STATE.generationProgress = null;
	}

	function deriveProgressPercent(elapsedMs) {
		const progressCap = 93;
		const eased = 1 - Math.exp(-elapsedMs / 2500);
		const percent = Math.round(progressCap * eased);
		return Math.max(8, Math.min(progressCap, percent));
	}

	function deriveProgressMessage(percent) {
		if (percent < 28) {
			return "Preparing request...";
		}
		if (percent < 60) {
			return "Generating drafts...";
		}
		if (percent < 86) {
			return "Refining tone and structure...";
		}
		return "Finalizing output...";
	}

	function renderGenerationProgress() {
		if (!STATE.loading || !STATE.generationProgress) {
			return;
		}
		const { percent, message } = STATE.generationProgress;
		ui.status.innerHTML = `
      <div class="smc-banner smc-banner-loading smc-banner-progress" role="status" aria-live="polite">
        <div class="smc-progress-head">
          <span class="smc-progress-label">${escapeHtml(message)}</span>
          <span class="smc-progress-percent">${percent}%</span>
        </div>
        <div class="smc-progress-track" aria-hidden="true">
          <div class="smc-progress-fill" style="width: ${percent}%;"></div>
        </div>
      </div>
    `;
		if (ui.statusSection) {
			ui.statusSection.hidden = false;
		}
	}

	function renderStatus(text, level) {
		if (!text) {
			ui.status.innerHTML = "";
			if (ui.statusSection) {
				ui.statusSection.hidden = true;
			}
			return;
		}
		ui.status.innerHTML = `<div class="smc-banner smc-banner-${level || "info"}">${escapeHtml(text)}</div>`;
		if (ui.statusSection) {
			ui.statusSection.hidden = false;
		}
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
			const [activeTab] = await chrome.tabs.query({
				active: true,
				lastFocusedWindow: true,
			});
			return coerceWindowId(activeTab?.windowId);
		} catch (_error) {
			return null;
		}
	}

	async function openSidePanelInWindow(windowId) {
		if (typeof chrome.sidePanel?.open !== "function") {
			throw new Error("Side Panel is unavailable in this browser.");
		}
		await chrome.sidePanel.open({ windowId });
	}

	async function closeSidePanelInWindow(windowId) {
		const normalizedWindowId = coerceWindowId(windowId);
		if (!normalizedWindowId || typeof chrome.sidePanel?.close !== "function") {
			return false;
		}
		try {
			await chrome.sidePanel.close({ windowId: normalizedWindowId });
			return true;
		} catch (_error) {
			return false;
		}
	}

	async function closeCurrentSidePanelShell() {
		const currentHostWindowId =
			coerceWindowId(STATE.currentWindowId) ||
			coerceWindowId(STATE.targetWindowId);
		const closed = await closeSidePanelInWindow(currentHostWindowId);
		if (!closed) {
			window.close();
		}
	}
})();
