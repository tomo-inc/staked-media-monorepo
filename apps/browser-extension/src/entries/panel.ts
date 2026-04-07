interface PanelWindow extends Window {
	StakedMediaExtensionShared: StakedMediaExtensionSharedApi;
	StakedMediaPanelHelpers: StakedMediaPanelHelpersApi;
}

interface RuntimeErrorWithStatus extends Error {
	status?: number;
	payload?: unknown;
	path?: string;
	code?: string;
}

interface PanelHealth {
	baseUrl?: string;
	status?: string;
	latencyMs?: number;
}

interface ProfileRecord extends Record<string, unknown> {
	followers_count?: number;
	following_count?: number;
}

interface PersonaTopicCluster {
	label?: string;
	name?: string;
}

interface PersonaPayload {
	author_summary?: string;
	voice_traits?: string[];
	topic_clusters?: PersonaTopicCluster[];
}

interface PersonaSnapshot {
	persona?: PersonaPayload | null;
}

interface PanelProfileState {
	exists: boolean;
	username: string;
	storedTweetCount: number;
	personaReady: boolean;
	profile: ProfileRecord | null;
	latestPersonaSnapshot: PersonaSnapshot | null;
}

interface PanelConfigResponse {
	config: StakedMediaExtensionConfig;
}

interface PanelHealthResponse {
	health?: PanelHealth;
}

interface PanelCheckProfileResponse {
	profile: PanelProfileState;
}

interface PanelIngestProfileResult {
	username?: string;
	fetched_tweet_count?: number;
	profile?: ProfileRecord | null;
	persona?: PersonaPayload | null;
}

interface PanelIngestProfileResponse {
	result: PanelIngestProfileResult;
}

interface PanelGenerateResponse {
	result: StakedMediaDraftSource | null;
}

interface PanelHotEventsPayload {
	hours?: number;
	count?: number;
	items?: PanelHotEventRecord[];
	warnings?: string[];
	source_status?: Record<
		string,
		{
			status?: string;
			count?: number;
			error?: string;
		}
	>;
}

interface PanelHotEventsResponse {
	result: PanelHotEventsPayload | null;
}

interface PanelComposerResponse {
	composer?: {
		available?: boolean;
		message?: string;
	} | null;
}

interface PanelLocalConversationCapability {
	supported: boolean;
	message: string;
	checkedAt: string;
}

interface PanelLocalConversationCapabilityResponse {
	result: PanelLocalConversationCapability;
}

interface GenerationProgress {
	percent: number;
	message: string;
}

type PanelView = "main" | "settings";
type PanelSettingsPage = "home" | "api";
type PanelTab = "profile" | "draft" | "conversation";
type HealthState = "loading" | "ready" | "error";
type PanelStatusKind = "" | "warn";
type PanelDraftLike = StakedMediaDraftRecord | string;

interface PanelHotEventRecord {
	id: string;
	title?: string;
	summary?: string;
	url?: string;
	source?: string;
	source_domain?: string;
	published_at?: string;
	relative_age_hint?: string;
	heat_score?: number;
	category?: string;
	subcategory?: string;
	content_type?: "news" | "tweet" | string;
	author_handle?: string;
}

interface PanelState {
	config: StakedMediaExtensionConfig | null;
	health: PanelHealth | null;
	latencyMs: number | null;
	healthState: HealthState;
	generated: StakedMediaDraftSource | null;
	lastGenerateDurationMs: number | null;
	loading: boolean;
	composerAvailable: boolean;
	composerMessage: string;
	currentWindowId: number | null;
	targetWindowId: number | null;
	currentView: PanelView;
	settingsPage: PanelSettingsPage;
	activeTab: PanelTab;
	profile: PanelProfileState | null;
	profileLoading: boolean;
	usernameError: string;
	generationProgress: GenerationProgress | null;
	generationProgressTimer: number | null;
	generationStartedAt: number | null;
	hotEvents: PanelHotEventRecord[];
	hotEventsWarnings: string[];
	hotEventsFetchedAt: string;
	hotEventsLoading: boolean;
	selectedHotEventId: string;
	conversationGenerated: StakedMediaDraftSource | null;
	lastConversationDurationMs: number | null;
	conversationErrorHint: string;
}

interface PanelUi {
	headerTitle: HTMLElement;
	username: HTMLInputElement;
	idea: HTMLTextAreaElement;
	draftCount: HTMLInputElement;
	generateButton: HTMLButtonElement;
	openSettingsButton: HTMLButtonElement;
	closeSettingsButton: HTMLButtonElement;
	openApiSettingsButton: HTMLButtonElement;
	toggleOpenModeButton: HTMLButtonElement;
	statusSection: HTMLElement;
	status: HTMLElement;
	usernameError: HTMLElement;
	results: HTMLElement;
	composer: HTMLElement;
	dot: HTMLElement;
	latencyText: HTMLElement;
	settingsStatusSection: HTMLElement;
	settingsStatus: HTMLElement;
	sBackendBaseUrl: HTMLInputElement;
	sApiModeDrafts: HTMLInputElement;
	sApiModeContent: HTMLInputElement;
	sTheme: HTMLSelectElement;
	sLanguage: HTMLSelectElement;
	sHostModeTitle: HTMLElement;
	profileInfo: HTMLElement;
	hotEventsMeta: HTMLElement;
	hotEvents: HTMLElement;
	conversationComment: HTMLTextAreaElement;
	conversationDraftCount: HTMLInputElement;
	generateConversationButton: HTMLButtonElement;
	sendToDraftButton: HTMLButtonElement;
	sendToDraftHint: HTMLElement;
	conversationResults: HTMLElement;
	views: NodeListOf<HTMLElement>;
	settingsPages: NodeListOf<HTMLElement>;
}

(function () {
	const panelWindow = window as PanelWindow;
	const {
		DEFAULT_CONFIG,
		coerceWindowId,
		escapeHtml,
		extractDrafts,
		listLanguageOptions,
		resolveLocale,
		sendRuntimeMessage,
		t,
	} = panelWindow.StakedMediaExtensionShared;
	const { buildPanelShell, deriveConnectionIndicator, isWhitelistDeniedError } =
		panelWindow.StakedMediaPanelHelpers;
	const params = new URLSearchParams(window.location.search);
	const HOST_MODE = params.get("host") === "popup" ? "popup" : "sidepanel";
	const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

	const SETTINGS_DEFAULTS = { ...DEFAULT_CONFIG };
	const HOT_EVENTS_CACHE_TTL_MS = 120 * 1000;
	const REMOTE_BACKEND_BASE_URL = "https://api.sayviner.top:8443";

	const STATE: PanelState = {
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
		hotEvents: [],
		hotEventsWarnings: [],
		hotEventsFetchedAt: "",
		hotEventsLoading: false,
		selectedHotEventId: "",
		conversationGenerated: null,
		lastConversationDurationMs: null,
		conversationErrorHint: "",
	};

	const root = document.getElementById("app") as HTMLElement;
	root.innerHTML = buildPanelShell();
	root.firstElementChild?.setAttribute("data-host", HOST_MODE);

	const ui: PanelUi = {
		headerTitle: root.querySelector(
			'[data-slot="header-title"]',
		) as HTMLElement,
		username: root.querySelector('[data-field="username"]') as HTMLInputElement,
		idea: root.querySelector('[data-field="idea"]') as HTMLTextAreaElement,
		draftCount: root.querySelector(
			'[data-field="draftCount"]',
		) as HTMLInputElement,
		generateButton: root.querySelector(
			'[data-action="generate"]',
		) as HTMLButtonElement,
		openSettingsButton: root.querySelector(
			'[data-action="open-settings"]',
		) as HTMLButtonElement,
		closeSettingsButton: root.querySelector(
			'[data-action="close-settings"]',
		) as HTMLButtonElement,
		openApiSettingsButton: root.querySelector(
			'[data-action="open-api-settings"]',
		) as HTMLButtonElement,
		toggleOpenModeButton: root.querySelector(
			'[data-action="toggle-open-mode"]',
		) as HTMLButtonElement,
		statusSection: root.querySelector(
			'[data-slot="status-section"]',
		) as HTMLElement,
		status: root.querySelector('[data-slot="status"]') as HTMLElement,
		usernameError: root.querySelector(
			'[data-slot="username-error"]',
		) as HTMLElement,
		results: root.querySelector('[data-slot="results"]') as HTMLElement,
		composer: root.querySelector('[data-slot="composer"]') as HTMLElement,
		dot: root.querySelector('[data-slot="connection"]') as HTMLElement,
		latencyText: root.querySelector(
			'[data-slot="latency-text"]',
		) as HTMLElement,
		settingsStatusSection: root.querySelector(
			".smc-settings-status-section",
		) as HTMLElement,
		settingsStatus: root.querySelector(
			'[data-slot="settings-status"]',
		) as HTMLElement,
		sBackendBaseUrl: root.querySelector(
			'[data-field="s-backendBaseUrl"]',
		) as HTMLInputElement,
		sApiModeDrafts: root.querySelector(
			'[data-field="s-apiModeDrafts"]',
		) as HTMLInputElement,
		sApiModeContent: root.querySelector(
			'[data-field="s-apiModeContent"]',
		) as HTMLInputElement,
		sTheme: root.querySelector('[data-field="s-theme"]') as HTMLSelectElement,
		sLanguage: root.querySelector(
			'[data-field="s-language"]',
		) as HTMLSelectElement,
		sHostModeTitle: root.querySelector(
			'[data-slot="s-host-mode-title"]',
		) as HTMLElement,
		profileInfo: root.querySelector(
			'[data-slot="profile-info"]',
		) as HTMLElement,
		hotEventsMeta: root.querySelector(
			'[data-slot="hot-events-meta"]',
		) as HTMLElement,
		hotEvents: root.querySelector('[data-slot="hot-events"]') as HTMLElement,
		conversationComment: root.querySelector(
			'[data-field="conversationComment"]',
		) as HTMLTextAreaElement,
		conversationDraftCount: root.querySelector(
			'[data-field="conversationDraftCount"]',
		) as HTMLInputElement,
		generateConversationButton: root.querySelector(
			'[data-action="generate-conversation"]',
		) as HTMLButtonElement,
		sendToDraftButton: root.querySelector(
			'[data-action="send-to-draft"]',
		) as HTMLButtonElement,
		sendToDraftHint: root.querySelector(
			'[data-slot="send-to-draft-hint"]',
		) as HTMLElement,
		conversationResults: root.querySelector(
			'[data-slot="conversation-results"]',
		) as HTMLElement,
		views: root.querySelectorAll("[data-view]") as NodeListOf<HTMLElement>,
		settingsPages: root.querySelectorAll(
			"[data-settings-view]",
		) as NodeListOf<HTMLElement>,
	};

	applyRemoteApiGuard();

	// Tab navigation
	(
		root.querySelectorAll("[data-tab-target]") as NodeListOf<HTMLButtonElement>
	).forEach((btn) => {
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

	ui.sLanguage.addEventListener("change", async () => {
		await saveLanguage(ui.sLanguage.value as StakedMediaLanguageMode);
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

	ui.conversationComment.addEventListener("input", () => {
		renderSendToDraftButton();
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
		.querySelector('[data-action="refresh-hot-events"]')
		.addEventListener("click", async () => {
			await loadHotEvents(true);
		});

	root
		.querySelector('[data-action="generate-conversation"]')
		.addEventListener("click", async () => {
			await handleConversationGenerate();
		});

	root
		.querySelector('[data-action="send-to-draft"]')
		.addEventListener("click", () => {
			handleSendToDraft();
		});

	root
		.querySelector('[data-action="clear-conversation-results"]')
		.addEventListener("click", () => {
			STATE.conversationGenerated = null;
			STATE.lastConversationDurationMs = null;
			STATE.conversationErrorHint = "";
			renderConversationResults();
			renderSendToDraftButton();
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

	function switchTab(tabName: string | null): void {
		let nextTab: PanelTab = "profile";
		if (tabName === "draft") {
			nextTab = "draft";
		} else if (tabName === "conversation") {
			nextTab = "conversation";
		}
		STATE.activeTab = nextTab;
		(
			root.querySelectorAll(
				"[data-tab-target]",
			) as NodeListOf<HTMLButtonElement>
		).forEach((btn) => {
			btn.classList.toggle(
				"smc-tab-active",
				btn.getAttribute("data-tab-target") === nextTab,
			);
		});
		(
			root.querySelectorAll("[data-tab-panel]") as NodeListOf<HTMLElement>
		).forEach((panel) => {
			panel.classList.toggle(
				"smc-tab-panel-active",
				panel.getAttribute("data-tab-panel") === nextTab,
			);
		});
		if (
			nextTab === "conversation" &&
			!STATE.hotEventsLoading &&
			STATE.hotEvents.length === 0
		) {
			void loadHotEvents(false);
		}
		if (nextTab === "conversation") {
			void ensureLocalConversationCapability(false);
		}
	}

	function openSettingsView(): void {
		STATE.currentView = "settings";
		STATE.settingsPage = "home";
		loadSettingsUI({ syncApiForm: true });
		renderView();
	}

	function openApiSettingsPage(): void {
		STATE.currentView = "settings";
		STATE.settingsPage = "api";
		loadSettingsUI({ syncApiForm: true });
		renderView();
	}

	async function closeSettingsView(): Promise<void> {
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

	async function bootstrap(): Promise<void> {
		const currentWindow = await chrome.windows.getCurrent();
		STATE.currentWindowId = coerceWindowId(currentWindow?.id);
		STATE.targetWindowId =
			HOST_MODE === "popup"
				? await resolvePopupTargetWindowId()
				: STATE.currentWindowId;

		const configResponse = await sendRuntimeMessage<PanelConfigResponse>({
			type: "get_config",
		});
		STATE.config = configResponse.config;
		await enforceRemoteBackendConfig();
		applyTheme(STATE.config?.theme);
		hydrateInputs();
		await refreshHealth();
		await refreshComposerState();
		await ensureLocalConversationCapability(true);
		render();
	}

	async function refreshHealth(): Promise<void> {
		try {
			const response = await sendRuntimeMessage<PanelHealthResponse>({
				type: "health_check",
			});
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

	async function ensureLocalConversationCapability(
		forceRefresh: boolean,
	): Promise<void> {
		try {
			const response =
				await sendRuntimeMessage<PanelLocalConversationCapabilityResponse>({
					type: "check_local_conversation_capability",
					payload: { refresh: forceRefresh },
				});
			const supported = Boolean(response?.result?.supported);
			if (!supported) {
				STATE.conversationErrorHint =
					String(response?.result?.message || "").trim() ||
					"Local conversation backend is outdated. Please restart local backend with latest code and --reload.";
				renderConversationResults();
				renderSendToDraftButton();
				return;
			}
			if (!STATE.conversationGenerated) {
				STATE.conversationErrorHint = "";
				renderConversationResults();
				renderSendToDraftButton();
			}
		} catch (_error) {
			if (!STATE.conversationGenerated) {
				STATE.conversationErrorHint =
					"Unable to verify local backend capability. Make sure http://127.0.0.1:8000 is running.";
				renderConversationResults();
				renderSendToDraftButton();
			}
		}
	}

	function applyRemoteApiGuard(): void {
		ui.sBackendBaseUrl.readOnly = true;
		ui.sBackendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
		ui.sApiModeContent.disabled = true;
	}

	function getResolvedLocale(): StakedMediaLocale {
		const languageSetting =
			STATE.config?.language || SETTINGS_DEFAULTS.language;
		return resolveLocale(languageSetting, navigator.language);
	}

	function tr(key: string): string {
		return t(key, getResolvedLocale());
	}

	function applyLocalizedContent(): void {
		const locale = getResolvedLocale();
		(root.querySelectorAll("[data-i18n]") as NodeListOf<HTMLElement>).forEach(
			(element) => {
				const key = String(element.getAttribute("data-i18n") || "").trim();
				if (!key) {
					return;
				}
				element.textContent = t(key, locale);
			},
		);
		const themeLightOption = ui.sTheme.querySelector(
			'option[value="light"]',
		) as HTMLOptionElement | null;
		const themeDarkOption = ui.sTheme.querySelector(
			'option[value="dark"]',
		) as HTMLOptionElement | null;
		const themeSystemOption = ui.sTheme.querySelector(
			'option[value="system"]',
		) as HTMLOptionElement | null;
		if (themeLightOption) {
			themeLightOption.textContent = t("theme.light", locale);
		}
		if (themeDarkOption) {
			themeDarkOption.textContent = t("theme.dark", locale);
		}
		if (themeSystemOption) {
			themeSystemOption.textContent = t("theme.system", locale);
		}

		const languageSetting =
			STATE.config?.language || SETTINGS_DEFAULTS.language;
		const languageOptions = listLanguageOptions(locale);
		ui.sLanguage.innerHTML = languageOptions
			.map(
				(option) =>
					`<option value="${escapeHtml(option.value)}">${escapeHtml(option.label)}</option>`,
			)
			.join("");
		ui.sLanguage.value = languageSetting;
	}

	async function enforceRemoteBackendConfig(): Promise<void> {
		if (!STATE.config) {
			return;
		}
		const currentBackendBaseUrl = String(
			STATE.config.backendBaseUrl || "",
		).trim();
		const needsBackendBaseUrlSync =
			currentBackendBaseUrl !== REMOTE_BACKEND_BASE_URL;
		const needsApiModeSync = STATE.config.apiMode !== "drafts";
		if (!needsBackendBaseUrlSync && !needsApiModeSync) {
			return;
		}

		try {
			const response = await sendRuntimeMessage<PanelConfigResponse>({
				type: "save_config",
				payload: {
					backendBaseUrl: REMOTE_BACKEND_BASE_URL,
					apiMode: "drafts",
				},
			});
			STATE.config = response.config;
		} catch (error) {
			renderStatus(formatRuntimeError(error), "warn");
		}
	}

	function loadSettingsUI(options: { syncApiForm?: boolean } = {}): void {
		const syncApiForm = options.syncApiForm !== false;
		const config = STATE.config || {};
		const merged = { ...SETTINGS_DEFAULTS, ...config };
		if (syncApiForm) {
			ui.sBackendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
			ui.sApiModeDrafts.checked = true;
			ui.sApiModeContent.checked = false;
		}
		ui.sTheme.value = merged.theme || "light";
		ui.sLanguage.value = merged.language || "auto";
		applyLocalizedContent();
		if (ui.sHostModeTitle) {
			ui.sHostModeTitle.textContent = getOpenModeToggleLabel(
				merged.hostMode,
				getResolvedLocale(),
			);
		}
	}

	async function saveLanguage(
		language: StakedMediaLanguageMode,
	): Promise<void> {
		try {
			const response = await sendRuntimeMessage<PanelConfigResponse>({
				type: "save_config",
				payload: { language },
			});
			STATE.config = response.config;
			loadSettingsUI({ syncApiForm: false });
			render();
			renderSettingsStatus("", "");
		} catch (error) {
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus(formatRuntimeError(error), "warn");
		}
	}

	async function saveTheme(theme: string): Promise<void> {
		try {
			const response = await sendRuntimeMessage<PanelConfigResponse>({
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

	async function saveApiMode(apiMode: StakedMediaApiMode): Promise<void> {
		if (apiMode !== "drafts") {
			loadSettingsUI({ syncApiForm: true });
			renderSettingsStatus(
				"Only Drafts API mode is enabled for this remote API test phase.",
				"warn",
			);
			return;
		}
		try {
			const response = await sendRuntimeMessage<PanelConfigResponse>({
				type: "save_config",
				payload: {
					apiMode: "drafts",
				},
			});
			STATE.config = response.config;
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus("", "");
		} catch (error) {
			loadSettingsUI({ syncApiForm: false });
			renderSettingsStatus(formatRuntimeError(error), "warn");
		}
	}

	async function saveBackendBaseUrl(): Promise<boolean> {
		const nextValue = REMOTE_BACKEND_BASE_URL;
		ui.sBackendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
		const currentValue = String(
			STATE.config?.backendBaseUrl || SETTINGS_DEFAULTS.backendBaseUrl,
		);
		if (nextValue === currentValue) {
			return true;
		}
		try {
			const response = await sendRuntimeMessage<PanelConfigResponse>({
				type: "save_config",
				payload: {
					backendBaseUrl: REMOTE_BACKEND_BASE_URL,
					apiMode: "drafts",
				},
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

	async function switchHostMode(hostMode: StakedMediaHostMode): Promise<void> {
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

	async function persistHostMode(
		hostMode: StakedMediaHostMode,
	): Promise<StakedMediaExtensionConfig> {
		const response = await sendRuntimeMessage<PanelConfigResponse>({
			type: "save_config",
			payload: { hostMode },
		});
		STATE.config = response.config;
		loadSettingsUI({ syncApiForm: false });
		renderSettingsStatus("", "");
		return response.config;
	}

	async function switchSidePanelToPopup(): Promise<void> {
		await persistHostMode("popup");
		await closeCurrentSidePanelShell();
	}

	async function switchPopupToSidePanel(): Promise<void> {
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

	function renderSettingsStatus(text: unknown, kind: PanelStatusKind): void {
		if (!ui.settingsStatus) return;
		const message = String(text || "");
		ui.settingsStatus.textContent = message;
		ui.settingsStatus.className = `smc-settings-status${kind ? ` smc-settings-status-${kind}` : ""}`;
		if (ui.settingsStatusSection) {
			ui.settingsStatusSection.hidden = !message;
		}
	}

	async function handleLoadProfile(): Promise<void> {
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
			const response = await sendRuntimeMessage<PanelCheckProfileResponse>({
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

	async function handleIngestProfile(): Promise<void> {
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
			const response = await sendRuntimeMessage<PanelIngestProfileResponse>({
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

	async function handleGenerate(): Promise<void> {
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
			draft_count: ui.draftCount.value || "3",
		};
		renderUsernameError("");
		renderStatus("", "");
		await runGeneration(payload);
	}

	async function runGeneration(payload: {
		username: string;
		idea: string;
		draft_count: string;
	}): Promise<void> {
		setLoading(true);
		const startedAt = performance.now();
		try {
			const response = await sendRuntimeMessage<PanelGenerateResponse>({
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

	async function loadHotEvents(forceRefresh: boolean): Promise<void> {
		if (!forceRefresh && hasFreshHotEventsCache()) {
			renderHotEvents();
			return;
		}
		STATE.hotEventsLoading = true;
		renderHotEvents();
		try {
			const response = await sendRuntimeMessage<PanelHotEventsResponse>({
				type: "get_hot_events",
				payload: {
					hours: 24,
					limit: 50,
					refresh: forceRefresh,
				},
			});
			const rawItems = Array.isArray(response.result?.items)
				? response.result?.items
				: [];
			const nextItems = rawItems
				.map((item) => normalizeHotEventRecord(item as PanelHotEventRecord))
				.filter((item) => Boolean(item.id));
			STATE.hotEvents = nextItems;
			STATE.hotEventsWarnings = Array.isArray(response.result?.warnings)
				? response.result?.warnings.map((item) => String(item || ""))
				: [];
			STATE.hotEventsFetchedAt = new Date().toISOString();
			if (
				STATE.selectedHotEventId &&
				!STATE.hotEvents.find(
					(item) => getHotEventId(item) === STATE.selectedHotEventId,
				)
			) {
				STATE.selectedHotEventId = "";
				renderSendToDraftButton();
			}
			renderHotEvents();
			renderStatus("", "");
		} catch (error) {
			renderStatus(formatApiError(error), "error");
		} finally {
			STATE.hotEventsLoading = false;
			renderHotEvents();
		}
	}

	function renderHotEvents(): void {
		if (!ui.hotEvents || !ui.hotEventsMeta) {
			return;
		}
		if (STATE.hotEventsLoading) {
			ui.hotEventsMeta.innerHTML = "Loading 24h hot events...";
			ui.hotEvents.innerHTML =
				'<div class="smc-empty">Loading hot events...</div>';
			return;
		}
		if (!STATE.hotEvents.length) {
			const warningHtml = renderHotWarnings();
			ui.hotEventsMeta.innerHTML = warningHtml;
			ui.hotEvents.innerHTML =
				'<div class="smc-empty">No hot events available right now.</div>';
			return;
		}
		const fetchedAtLabel = STATE.hotEventsFetchedAt
			? `Fetched at ${new Date(STATE.hotEventsFetchedAt).toLocaleTimeString()}`
			: "";
		const summaryLabel = escapeHtml(
			`${STATE.hotEvents.length} events in last 24h. ${fetchedAtLabel}`.trim(),
		);
		const warningHtml = renderHotWarnings();
		ui.hotEventsMeta.innerHTML = `<div>${summaryLabel}</div>${warningHtml}`;
		ui.hotEvents.innerHTML = `
      <div class="smc-hot-carousel-shell">
        <div class="smc-hot-carousel-track" data-slot="hot-events-track">
          ${STATE.hotEvents
						.map((event, index) => {
							const eventId = getHotEventId(event);
							if (!eventId) {
								return "";
							}
							const isSelected = eventId === STATE.selectedHotEventId;
							const title = escapeHtml(event.title || "Untitled event");
							const summary = escapeHtml(event.summary || "");
							const contentType =
								String(event.content_type || "").toLowerCase() === "tweet"
									? "tweet"
									: "news";
							const authorHandle = String(event.author_handle || "").trim();
							const sourceDomain = escapeHtml(deriveSourceDomain(event));
							const sourceLabel =
								contentType === "tweet" && authorHandle
									? escapeHtml(`@${authorHandle.replace(/^@+/, "")}`)
									: sourceDomain;
							const relativeAge = escapeHtml(
								formatRelativeAge(event.published_at, event.relative_age_hint),
							);
							const heatScore = Number.isFinite(Number(event.heat_score))
								? Number(event.heat_score).toFixed(1)
								: "0.0";
							return `
              <article class="smc-hot-event-card ${isSelected ? "smc-hot-event-selected" : ""}" data-action="select-hot-event-card" data-hot-event-id="${escapeHtml(eventId)}" role="button" tabindex="0">
                <div class="smc-hot-event-head">
                  <span class="smc-hot-event-rank">#${index + 1}</span>
                  <span class="smc-hot-event-type smc-hot-event-type-${contentType}">${contentType}</span>
                  <span class="smc-hot-event-meta">${sourceLabel} | ${relativeAge}</span>
                  <span class="smc-hot-event-score">${heatScore}</span>
                </div>
                <h3 class="smc-hot-event-title">${title}</h3>
                ${summary ? `<p class="smc-hot-event-summary">${summary}</p>` : ""}
                <div class="smc-hot-event-actions">
                  <button class="smc-outline-button" data-action="select-hot-event" data-hot-event-id="${escapeHtml(eventId)}" type="button">
                    ${escapeHtml(isSelected ? tr("action.selected") : tr("action.select"))}
                  </button>
                </div>
              </article>
            `;
						})
						.join("")}
        </div>
      </div>
    `;

		const pickHotEvent = (eventId: string): void => {
			const normalizedEventId = String(eventId || "").trim();
			if (!normalizedEventId) {
				return;
			}
			STATE.selectedHotEventId = normalizedEventId;
			renderHotEvents();
			renderSendToDraftButton();
			renderStatus("Hot event selected. Add your take and generate.", "info");
		};
		const hotEventsTrack = ui.hotEvents.querySelector(
			'[data-slot="hot-events-track"]',
		) as HTMLElement | null;
		let isDragNavigating = false;
		(
			ui.hotEvents.querySelectorAll(
				'[data-action="select-hot-event"]',
			) as NodeListOf<HTMLButtonElement>
		).forEach((button) => {
			button.addEventListener("pointerdown", (pointerEvent) => {
				pointerEvent.stopPropagation();
			});
			button.addEventListener("click", (clickEvent) => {
				clickEvent.stopPropagation();
				if (isDragNavigating) {
					return;
				}
				pickHotEvent(String(button.getAttribute("data-hot-event-id") || ""));
			});
		});
		(
			ui.hotEvents.querySelectorAll(
				'[data-action="select-hot-event-card"]',
			) as NodeListOf<HTMLElement>
		).forEach((card) => {
			card.addEventListener("click", () => {
				if (isDragNavigating) {
					return;
				}
				pickHotEvent(String(card.getAttribute("data-hot-event-id") || ""));
			});
			card.addEventListener("keydown", (keyboardEvent) => {
				if (keyboardEvent.key !== "Enter" && keyboardEvent.key !== " ") {
					return;
				}
				keyboardEvent.preventDefault();
				pickHotEvent(String(card.getAttribute("data-hot-event-id") || ""));
			});
		});
		if (!hotEventsTrack) {
			return;
		}
		hotEventsTrack.addEventListener(
			"wheel",
			(wheelEvent) => {
				if (Math.abs(wheelEvent.deltaY) <= Math.abs(wheelEvent.deltaX)) {
					return;
				}
				wheelEvent.preventDefault();
				hotEventsTrack.scrollBy({
					left: wheelEvent.deltaY,
					behavior: "auto",
				});
			},
			{ passive: false },
		);

		let pointerActive = false;
		let pointerStartX = 0;
		let pointerStartScrollLeft = 0;
		let movedDistance = 0;
		const endPointerDrag = (pointerId?: number): void => {
			if (!pointerActive) {
				return;
			}
			pointerActive = false;
			hotEventsTrack.classList.remove("smc-hot-carousel-track-dragging");
			if (pointerId != null && hotEventsTrack.hasPointerCapture(pointerId)) {
				hotEventsTrack.releasePointerCapture(pointerId);
			}
			if (movedDistance > 8) {
				isDragNavigating = true;
				window.setTimeout(() => {
					isDragNavigating = false;
				}, 80);
			}
		};

		hotEventsTrack.addEventListener("pointerdown", (pointerEvent) => {
			if (pointerEvent.pointerType === "mouse" && pointerEvent.button !== 0) {
				return;
			}
			const pointerTarget = pointerEvent.target as Element | null;
			if (
				pointerTarget?.closest(
					'[data-action="select-hot-event"],button,input,textarea,select,a,label',
				)
			) {
				return;
			}
			pointerActive = true;
			pointerStartX = pointerEvent.clientX;
			pointerStartScrollLeft = hotEventsTrack.scrollLeft;
			movedDistance = 0;
			hotEventsTrack.classList.add("smc-hot-carousel-track-dragging");
			hotEventsTrack.setPointerCapture(pointerEvent.pointerId);
		});

		hotEventsTrack.addEventListener("pointermove", (pointerEvent) => {
			if (!pointerActive) {
				return;
			}
			const delta = pointerEvent.clientX - pointerStartX;
			movedDistance = Math.max(movedDistance, Math.abs(delta));
			hotEventsTrack.scrollLeft = pointerStartScrollLeft - delta;
		});

		hotEventsTrack.addEventListener("pointerup", (pointerEvent) => {
			endPointerDrag(pointerEvent.pointerId);
		});
		hotEventsTrack.addEventListener("pointercancel", (pointerEvent) => {
			endPointerDrag(pointerEvent.pointerId);
		});
		hotEventsTrack.addEventListener("pointerleave", () => {
			endPointerDrag();
		});
	}

	function renderHotWarnings(): string {
		if (!STATE.hotEventsWarnings.length) {
			return "";
		}
		const body = STATE.hotEventsWarnings
			.filter((item) => item)
			.map((item) => escapeHtml(item))
			.join(" | ");
		if (!body) {
			return "";
		}
		return `<div class="smc-hot-warning">${body}</div>`;
	}

	function hasFreshHotEventsCache(): boolean {
		if (!STATE.hotEvents.length || !STATE.hotEventsFetchedAt) {
			return false;
		}
		const fetchedAt = Date.parse(STATE.hotEventsFetchedAt);
		if (!Number.isFinite(fetchedAt)) {
			return false;
		}
		return Date.now() - fetchedAt < HOT_EVENTS_CACHE_TTL_MS;
	}

	function deriveSourceDomain(event: PanelHotEventRecord): string {
		const sourceDomain = String(event.source_domain || "")
			.trim()
			.toLowerCase();
		if (sourceDomain) {
			return sourceDomain;
		}

		const rawUrl = String(event.url || "").trim();
		if (rawUrl) {
			try {
				const url = new URL(rawUrl);
				const hostname = url.hostname.toLowerCase().replace(/^www\./, "");
				if (hostname) {
					return hostname;
				}
			} catch (_error) {
				// Ignore parse errors and fall back to source text.
			}
		}

		const source = String(event.source || "")
			.trim()
			.toLowerCase();
		return source || "unknown";
	}

	function getHotEventId(
		event: PanelHotEventRecord | null | undefined,
	): string {
		return String(event?.id ?? "").trim();
	}

	function normalizeHotEventRecord(
		event: PanelHotEventRecord,
	): PanelHotEventRecord {
		return {
			...event,
			id: getHotEventId(event),
			author_handle: String(event?.author_handle || "").trim() || undefined,
		};
	}

	function formatRelativeAge(
		publishedAt: string | undefined,
		fallbackHint: string | undefined,
	): string {
		const timestamp = Date.parse(String(publishedAt || ""));
		if (!Number.isFinite(timestamp)) {
			return String(fallbackHint || "unknown");
		}

		const elapsedSeconds = Math.floor((Date.now() - timestamp) / 1000);
		if (elapsedSeconds < 60) {
			return "just now";
		}

		const minutes = Math.floor(elapsedSeconds / 60);
		if (minutes < 60) {
			return `${minutes}m ago`;
		}

		const hours = Math.floor(minutes / 60);
		if (hours < 24) {
			return `${hours}h ago`;
		}

		const days = Math.floor(hours / 24);
		return `${days}d ago`;
	}

	async function handleConversationGenerate(): Promise<void> {
		const username = ui.username.value.trim();
		if (!username) {
			renderStatus("Username is required.", "error");
			return;
		}
		const selectedEvent = STATE.hotEvents.find(
			(item) => getHotEventId(item) === STATE.selectedHotEventId,
		);
		if (!selectedEvent) {
			renderStatus("Select a hot event first.", "error");
			return;
		}
		const payload = {
			username,
			event_id: getHotEventId(selectedEvent),
			event_payload: selectedEvent,
			comment: ui.conversationComment.value || "",
			draft_count: ui.conversationDraftCount.value || "3",
		};
		renderUsernameError("");
		renderStatus("", "");
		await runConversationGeneration(payload);
	}

	async function runConversationGeneration(payload: {
		username: string;
		event_id: string;
		event_payload: PanelHotEventRecord;
		comment: string;
		draft_count: string;
	}): Promise<void> {
		setLoading(true);
		const startedAt = performance.now();
		STATE.conversationErrorHint = "";
		try {
			const response = await sendRuntimeMessage<PanelGenerateResponse>({
				type: "conversation_generate",
				payload,
			});
			STATE.conversationGenerated = response.result;
			STATE.lastConversationDurationMs = Math.round(
				performance.now() - startedAt,
			);
			const draftCount = extractDrafts(STATE.conversationGenerated).length;
			if (!draftCount) {
				STATE.lastConversationDurationMs = null;
				STATE.conversationErrorHint =
					"Conversation request completed but returned no drafts. Please refresh hot events and try again.";
				renderStatus(STATE.conversationErrorHint, "warn");
				renderConversationResults();
				renderSendToDraftButton();
				return;
			}
			const durationLabel =
				STATE.lastConversationDurationMs != null
					? ` in ${STATE.lastConversationDurationMs} ms`
					: "";
			renderStatus(
				`Generated ${draftCount} conversation draft${draftCount === 1 ? "" : "s"}${durationLabel}.`,
				"success",
			);
			renderConversationResults();
			renderSendToDraftButton();
		} catch (error) {
			STATE.conversationGenerated = null;
			STATE.lastConversationDurationMs = null;
			STATE.conversationErrorHint = formatApiError(error);
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			}
			renderStatus(STATE.conversationErrorHint, "error");
			renderConversationResults();
			renderSendToDraftButton();
		} finally {
			setLoading(false);
		}
	}

	function handleSendToDraft(): void {
		const draftIdea = getCurrentConversationConclusion();
		if (!draftIdea) {
			renderStatus("No conversation content available to send.", "error");
			renderSendToDraftButton();
			return;
		}
		ui.idea.value = draftIdea;
		switchTab("draft");
		renderStatus("Sent to Draft idea.", "success");
	}

	function getSelectedHotEventRecord(): PanelHotEventRecord | null {
		if (!STATE.selectedHotEventId) {
			return null;
		}
		const selected = STATE.hotEvents.find(
			(item) => getHotEventId(item) === STATE.selectedHotEventId,
		);
		return selected || null;
	}

	function buildFallbackDraftIdea(): string {
		const selectedEvent = getSelectedHotEventRecord();
		const comment = String(ui.conversationComment.value || "").trim();
		if (!selectedEvent) {
			return "";
		}
		const title = String(selectedEvent.title || "").trim();
		const rawSummary = String(selectedEvent.summary || "")
			.replace(/\s+/g, " ")
			.trim();
		const summary =
			rawSummary.length > 260
				? `${rawSummary.slice(0, 260).trim()}...`
				: rawSummary;
		const focus = [title, summary].filter(Boolean).join(" ");
		if (!focus && !comment) {
			return "";
		}
		if (!focus && comment) {
			return `我的补充想法：${comment}`;
		}
		if (!comment) {
			return `新闻重点：${focus}`;
		}
		return [`新闻重点：${focus}`, `我的补充想法：${comment}`]
			.filter(Boolean)
			.join("\n\n");
	}

	function getGeneratedConversationConclusion(): string {
		const drafts = extractDrafts(
			STATE.conversationGenerated,
		) as PanelDraftLike[];
		return getDraftText(drafts, 0).trim();
	}

	function getCurrentConversationConclusion(): string {
		const generatedConclusion = getGeneratedConversationConclusion();
		if (generatedConclusion) {
			return generatedConclusion;
		}
		return buildFallbackDraftIdea();
	}

	async function refreshComposerState(): Promise<void> {
		try {
			const response = await sendRuntimeMessage<PanelComposerResponse>({
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

	function hydrateInputs(): void {
		ui.username.value =
			ui.username.value.trim() || STATE.config?.defaultUsername || "";
		if (!ui.draftCount.value) {
			ui.draftCount.value = "3";
		}
		if (!ui.conversationDraftCount.value) {
			ui.conversationDraftCount.value = "3";
		}
	}

	function render(): void {
		applyLocalizedContent();
		renderView();
		renderGenerateButton();
		renderConnectionDot();
		renderUsernameError(STATE.usernameError);
		renderProfileInfo();
		renderResults();
		renderHotEvents();
		renderConversationResults();
		renderSendToDraftButton();
		renderComposerState();
	}

	function renderView(): void {
		const locale = getResolvedLocale();
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
				ui.headerTitle.textContent = t("app.title", locale);
			} else if (STATE.settingsPage === "api") {
				ui.headerTitle.textContent = t("settings.apiPageTitle", locale);
			} else {
				ui.headerTitle.textContent = t("settings.title", locale);
			}
		}
		if (ui.openSettingsButton) {
			ui.openSettingsButton.hidden = isSettingsView;
		}
		if (ui.closeSettingsButton) {
			ui.closeSettingsButton.hidden = !isSettingsView;
			ui.closeSettingsButton.setAttribute(
				"aria-label",
				STATE.settingsPage === "api"
					? t("settings.backToSettings", locale)
					: t("settings.backToMainView", locale),
			);
		}
	}

	function applyTheme(theme: StakedMediaThemeMode | null | undefined): void {
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

	function getOpenModeToggleLabel(
		hostMode: StakedMediaHostMode | null | undefined,
		locale: StakedMediaLocale,
	): string {
		return hostMode === "popup"
			? t("settings.switchToSidePanel", locale)
			: t("settings.switchToPopup", locale);
	}

	function getNextHostMode(): StakedMediaHostMode {
		return STATE.config?.hostMode === "popup" ? "sidepanel" : "popup";
	}

	function renderGenerateButton(): void {
		if (!ui.generateButton) {
			return;
		}
		ui.generateButton.classList.toggle("smc-button-loading", STATE.loading);
		ui.generateButton.setAttribute(
			"aria-busy",
			STATE.loading ? "true" : "false",
		);
		ui.generateButton.innerHTML = STATE.loading
			? `<span class="smc-button-content"><span class="smc-button-spinner" aria-hidden="true"></span><span>${escapeHtml(
					tr("action.generating"),
				)}</span></span>`
			: tr("action.generate");
	}

	function renderConnectionDot(): void {
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

	function renderUsernameError(text: unknown): void {
		STATE.usernameError = String(text || "");
		if (!ui.usernameError) {
			return;
		}
		ui.usernameError.textContent = STATE.usernameError;
		ui.usernameError.hidden = !STATE.usernameError;
	}

	function renderProfileInfo(): void {
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

	function renderResults(): void {
		renderDraftCards({
			target: ui.results,
			source: STATE.generated,
			durationMs: STATE.lastGenerateDurationMs,
			emptyMessage: "No generated drafts yet.",
			showTimingWhenEmpty: true,
		});
	}

	function renderConversationResults(): void {
		renderDraftCards({
			target: ui.conversationResults,
			source: STATE.conversationGenerated,
			durationMs: STATE.lastConversationDurationMs,
			emptyMessage: getConversationEmptyMessage(),
		});
	}

	function getConversationEmptyMessage(): string {
		const hint = String(STATE.conversationErrorHint || "").trim();
		if (hint) {
			return hint;
		}
		return "No conversation drafts yet.";
	}

	function renderSendToDraftButton(): void {
		if (!ui.sendToDraftButton) {
			return;
		}
		const generatedConclusion = getGeneratedConversationConclusion();
		const sendableDraftIdea = getCurrentConversationConclusion();
		const hasDraftIdea = Boolean(sendableDraftIdea);
		ui.sendToDraftButton.disabled = !hasDraftIdea || STATE.loading;
		if (!ui.sendToDraftHint) {
			return;
		}
		let hint = "";
		if (STATE.loading) {
			hint = "Generating conversation result...";
		} else if (!hasDraftIdea) {
			hint =
				String(STATE.conversationErrorHint || "").trim() ||
				"Select a hot event first, then add your take or generate conversation.";
		} else if (!generatedConclusion) {
			hint = "Will send event focus + your take to Draft.";
		}
		ui.sendToDraftHint.textContent = hint;
		ui.sendToDraftHint.hidden = !hint;
	}

	function renderDraftCards(options: {
		target: HTMLElement;
		source: StakedMediaDraftSource | null;
		durationMs: number | null;
		emptyMessage: string;
		showTimingWhenEmpty?: boolean;
	}): void {
		const { target, source, durationMs, emptyMessage } = options;
		const showTimingWhenEmpty = Boolean(options.showTimingWhenEmpty);
		if (!target) {
			return;
		}
		const timingHtml =
			durationMs != null
				? `
          <div class="smc-result-meta">
            <span class="smc-result-meta-label">Response time</span>
            <span class="smc-result-meta-value">${escapeHtml(`${durationMs} ms`)}</span>
          </div>
        `
				: "";
		const drafts = extractDrafts(source) as PanelDraftLike[];
		if (!drafts.length) {
			const emptyTimingHtml = showTimingWhenEmpty ? timingHtml : "";
			target.innerHTML = `${emptyTimingHtml}<div class="smc-empty">${escapeHtml(emptyMessage)}</div>`;
			return;
		}
		target.innerHTML = `
      ${timingHtml}
      ${drafts
				.map((draft, index) => {
					const text = typeof draft === "string" ? draft : draft.text || "";
					return `
            <article class="smc-draft-card">
              <div class="smc-draft-head">
                <span class="smc-draft-label">Draft #${index + 1}</span>
                <div class="smc-draft-actions">
                  <button class="smc-outline-button" data-copy-index="${index}">${escapeHtml(
										tr("action.copy"),
									)}</button>
                  <button class="smc-outline-button" data-insert-index="${index}">${escapeHtml(
										tr("action.insert"),
									)}</button>
                </div>
              </div>
              <p class="smc-draft-text">${escapeHtml(text)}</p>
            </article>
          `;
				})
				.join("")}
    `;

		(
			target.querySelectorAll(
				"[data-copy-index]",
			) as NodeListOf<HTMLButtonElement>
		).forEach((button) => {
			button.addEventListener("click", async () => {
				const index = Number.parseInt(
					button.getAttribute("data-copy-index") || "",
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

		(
			target.querySelectorAll(
				"[data-insert-index]",
			) as NodeListOf<HTMLButtonElement>
		).forEach((button) => {
			button.addEventListener("click", async () => {
				const index = Number.parseInt(
					button.getAttribute("data-insert-index") || "",
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

	function renderComposerState(): void {
		const className = STATE.composerAvailable
			? "smc-pill smc-pill-good"
			: "smc-pill smc-pill-warn";
		ui.composer.innerHTML = `<span class="${className}">${escapeHtml(STATE.composerMessage)}</span>`;
	}

	function getDraftText(drafts: PanelDraftLike[], index: number): string {
		const draft = drafts[index];
		if (!draft) return "";
		if (typeof draft === "string") return draft;
		return String(draft.text || "");
	}

	function setLoading(nextLoading: boolean): void {
		STATE.loading = nextLoading;
		if (nextLoading) {
			startGenerationProgress();
		} else {
			stopGenerationProgress();
		}
		(root.querySelectorAll("button") as NodeListOf<HTMLButtonElement>).forEach(
			(button) => {
				if (
					button.hasAttribute("data-copy-index") ||
					button.hasAttribute("data-insert-index")
				) {
					return;
				}
				button.disabled = nextLoading;
			},
		);
		renderGenerateButton();
	}

	function startGenerationProgress(): void {
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

	function stopGenerationProgress(): void {
		if (STATE.generationProgressTimer != null) {
			window.clearInterval(STATE.generationProgressTimer);
			STATE.generationProgressTimer = null;
		}
		STATE.generationStartedAt = null;
		STATE.generationProgress = null;
	}

	function deriveProgressPercent(elapsedMs: number): number {
		const progressCap = 93;
		const eased = 1 - Math.exp(-elapsedMs / 2500);
		const percent = Math.round(progressCap * eased);
		return Math.max(8, Math.min(progressCap, percent));
	}

	function deriveProgressMessage(percent: number): string {
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

	function renderGenerationProgress(): void {
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

	function renderStatus(text: unknown, level: string | null | undefined): void {
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

	function formatApiError(error: unknown): string {
		const runtimeError = error as RuntimeErrorWithStatus;
		const code = String(runtimeError?.code || "").trim();
		const path = String(runtimeError?.path || "");
		const detailText = extractErrorDetailText(runtimeError?.payload);
		if (code === "LOCAL_BACKEND_REBUILD_UNSUPPORTED") {
			return "Local backend is outdated: /api/v1/profiles/rebuild-persona is unavailable. Restart local backend with latest code and --reload.";
		}
		if (code === "LOCAL_BACKEND_OPENAPI_UNAVAILABLE") {
			return "Local backend capability check failed. Confirm http://127.0.0.1:8000 is reachable.";
		}
		if (runtimeError?.status === 404) {
			if (path.startsWith("/api/v1/profiles/rebuild-persona")) {
				return "Profile is missing in local backend. Import profile history into local DB first.";
			}
			if (path.startsWith("/api/v1/profiles/")) {
				return "Profile not found in the backend. Run ingest first.";
			}
			if (path.startsWith("/api/v1/content/hot-events")) {
				return "Local conversation backend does not expose hot-events. Start or update local backend at http://127.0.0.1:8000.";
			}
			if (path.startsWith("/api/v1/conversation/generate")) {
				if (detailText.includes("selected hot event was not found")) {
					return "Selected hot event expired. Refresh hot events and select again.";
				}
				return "Local conversation endpoint is unavailable. Start or update local backend at http://127.0.0.1:8000.";
			}
			if (path === "/openapi.json") {
				return "Local backend OpenAPI route is unavailable. Start or update local backend at http://127.0.0.1:8000.";
			}
			return "Backend endpoint returned 404. Check API Base URL and backend version.";
		}
		if (
			runtimeError?.status === 405 &&
			path.startsWith("/api/v1/profiles/rebuild-persona")
		) {
			return "Local backend does not support persona rebuild yet. Restart local backend with latest code and --reload.";
		}
		if (runtimeError?.status === 409) {
			if (path.startsWith("/api/v1/profiles/rebuild-persona")) {
				return "Local backend has no tweets for this user, so persona rebuild cannot run yet.";
			}
			return "Persona is missing in the backend. Re-run ingest before generating.";
		}
		if (runtimeError?.status === 422) {
			return "The backend rejected the request. Check your input and try again.";
		}
		if (runtimeError?.status === 502) {
			return "The backend failed while calling upstream services. Retry once the service is healthy.";
		}
		return formatRuntimeError(error);
	}

	function extractErrorDetailText(payload: unknown): string {
		if (payload && typeof payload === "object" && !Array.isArray(payload)) {
			const detail = (payload as { detail?: unknown }).detail;
			return String(detail || "")
				.trim()
				.toLowerCase();
		}
		return "";
	}

	function formatRuntimeError(error: unknown): string {
		return String(
			(error as Error | undefined)?.message || error || "Unknown error",
		);
	}

	async function resolvePopupTargetWindowId(): Promise<number | null> {
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

	async function openSidePanelInWindow(windowId: number): Promise<void> {
		if (typeof chrome.sidePanel?.open !== "function") {
			throw new Error("Side Panel is unavailable in this browser.");
		}
		await chrome.sidePanel.open({ windowId });
	}

	async function closeSidePanelInWindow(windowId: unknown): Promise<boolean> {
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

	async function closeCurrentSidePanelShell(): Promise<void> {
		const currentHostWindowId =
			coerceWindowId(STATE.currentWindowId) ||
			coerceWindowId(STATE.targetWindowId);
		const closed = await closeSidePanelInWindow(currentHostWindowId);
		if (!closed) {
			window.close();
		}
	}
})();
