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
	last_refreshed_at?: string;
	last_attempted_at?: string;
	refresh_interval_seconds?: number;
	is_stale?: boolean;
	refreshing?: boolean;
	throttled?: boolean;
	next_refresh_available_in_seconds?: number;
	last_refresh_error?: string;
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

interface PanelLocalTrendingCapability {
	supported: boolean;
	message: string;
	checkedAt: string;
}

interface PanelLocalTrendingCapabilityResponse {
	result: PanelLocalTrendingCapability;
}

interface GenerationProgress {
	percent: number;
	message: string;
}

type PanelView = "main" | "settings";
type PanelSettingsPage = "home" | "api";
type PanelTab = "profile" | "draft" | "trending";
type HealthState = "loading" | "ready" | "error";
type LoadingAction = "" | "draft" | "trending";
type ProfileLoadingAction = "" | "load" | "ingest";
type PanelStatusKind = "" | "warn";
type PanelDraftLike = StakedMediaDraftRecord | string;

interface PanelHotEventRecord {
	id: string;
	title?: string;
	summary?: string;
	title_translated?: string;
	summary_translated?: string;
	is_translated?: boolean;
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
	loadingAction: LoadingAction;
	composerAvailable: boolean;
	composerMessage: string;
	currentWindowId: number | null;
	targetWindowId: number | null;
	currentView: PanelView;
	settingsPage: PanelSettingsPage;
	activeTab: PanelTab;
	profile: PanelProfileState | null;
	profileLoading: boolean;
	profileLoadingAction: ProfileLoadingAction;
	usernameError: string;
	generationProgress: GenerationProgress | null;
	generationProgressTimer: number | null;
	generationStartedAt: number | null;
	hotEvents: PanelHotEventRecord[];
	hotEventsWarnings: string[];
	hotEventsFetchedAt: string;
	hotEventsLastRefreshedAt: string;
	hotEventsLastAttemptedAt: string;
	hotEventsRefreshIntervalSeconds: number;
	hotEventsIsStale: boolean;
	hotEventsRefreshing: boolean;
	hotEventsThrottled: boolean;
	hotEventsNextRefreshAvailableInSeconds: number;
	hotEventsLastRefreshError: string;
	hotEventsLoading: boolean;
	hotEventsShowOriginal: Record<string, boolean>;
	hotEventsExpandedSummary: Record<string, boolean>;
	selectedHotEventId: string;
	trendingGenerated: StakedMediaDraftSource | null;
	lastTrendingDurationMs: number | null;
	trendingErrorHint: string;
	hasUnreadDraftResult: boolean;
	debugModeUnlocked: boolean;
	debugTapCount: number;
	debugTapStartedAt: number;
}

interface PanelUi {
	headerTitle: HTMLElement;
	draftTabButton: HTMLButtonElement;
	username: HTMLInputElement;
	idea: HTMLTextAreaElement;
	draftCount: HTMLInputElement;
	generateButton: HTMLButtonElement;
	loadProfileButton: HTMLButtonElement;
	ingestProfileButton: HTMLButtonElement;
	openSettingsButton: HTMLButtonElement;
	closeSettingsButton: HTMLButtonElement;
	openApiSettingsButton: HTMLButtonElement;
	unlockDebugButton: HTMLButtonElement;
	settingsVersion: HTMLElement;
	settingsVersionMode: HTMLElement;
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
	selectedHotEventInfo: HTMLElement;
	trendingComment: HTMLTextAreaElement;
	trendingDraftCount: HTMLInputElement;
	generateTrendingButton: HTMLButtonElement;
	sendToDraftButton: HTMLButtonElement;
	sendToDraftHint: HTMLElement;
	trendingResults: HTMLElement;
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
		sanitizeUserVisibleErrorMessage,
		sendRuntimeMessage,
		t,
	} = panelWindow.StakedMediaExtensionShared;
	const {
		buildPanelShell,
		deriveConnectionIndicator,
		deriveHotEventsStateNotice,
		isWhitelistDeniedError,
	} = panelWindow.StakedMediaPanelHelpers;
	const params = new URLSearchParams(window.location.search);
	const HOST_MODE = params.get("host") === "popup" ? "popup" : "sidepanel";
	const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");
	const EXTENSION_VERSION = chrome.runtime.getManifest().version || "0.0.0";
	const DEBUG_UNLOCK_TAP_WINDOW_MS = 3000;

	const SETTINGS_DEFAULTS = { ...DEFAULT_CONFIG };
	const HOT_EVENTS_CACHE_TTL_MS = 120 * 1000;

	const STATE: PanelState = {
		config: null,
		health: null,
		latencyMs: null,
		healthState: "loading",
		generated: null,
		lastGenerateDurationMs: null,
		loading: false,
		loadingAction: "",
		composerAvailable: false,
		composerMessage: "Open the X composer to insert drafts.",
		currentWindowId: null,
		targetWindowId: null,
		currentView: "main",
		settingsPage: "home",
		activeTab: "profile",
		profile: null,
		profileLoading: false,
		profileLoadingAction: "",
		usernameError: "",
		generationProgress: null,
		generationProgressTimer: null,
		generationStartedAt: null,
		hotEvents: [],
		hotEventsWarnings: [],
		hotEventsFetchedAt: "",
		hotEventsLastRefreshedAt: "",
		hotEventsLastAttemptedAt: "",
		hotEventsRefreshIntervalSeconds: 0,
		hotEventsIsStale: false,
		hotEventsRefreshing: false,
		hotEventsThrottled: false,
		hotEventsNextRefreshAvailableInSeconds: 0,
		hotEventsLastRefreshError: "",
		hotEventsLoading: false,
		hotEventsShowOriginal: {},
		hotEventsExpandedSummary: {},
		selectedHotEventId: "",
		trendingGenerated: null,
		lastTrendingDurationMs: null,
		trendingErrorHint: "",
		hasUnreadDraftResult: false,
		debugModeUnlocked: false,
		debugTapCount: 0,
		debugTapStartedAt: 0,
	};

	const root = document.getElementById("app") as HTMLElement;
	root.innerHTML = buildPanelShell();
	root.firstElementChild?.setAttribute("data-host", HOST_MODE);

	const ui: PanelUi = {
		headerTitle: root.querySelector(
			'[data-slot="header-title"]',
		) as HTMLElement,
		draftTabButton: root.querySelector(
			'[data-tab-target="draft"]',
		) as HTMLButtonElement,
		username: root.querySelector('[data-field="username"]') as HTMLInputElement,
		idea: root.querySelector('[data-field="idea"]') as HTMLTextAreaElement,
		draftCount: root.querySelector(
			'[data-field="draftCount"]',
		) as HTMLInputElement,
		generateButton: root.querySelector(
			'[data-action="generate"]',
		) as HTMLButtonElement,
		loadProfileButton: root.querySelector(
			'[data-action="load-profile"]',
		) as HTMLButtonElement,
		ingestProfileButton: root.querySelector(
			'[data-action="ingest-profile"]',
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
		unlockDebugButton: root.querySelector(
			'[data-action="unlock-debug"]',
		) as HTMLButtonElement,
		settingsVersion: root.querySelector(
			'[data-slot="settings-version"]',
		) as HTMLElement,
		settingsVersionMode: root.querySelector(
			'[data-slot="settings-version-mode"]',
		) as HTMLElement,
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
		selectedHotEventInfo: root.querySelector(
			'[data-slot="selected-hot-event-info"]',
		) as HTMLElement,
		trendingComment: root.querySelector(
			'[data-field="trendingComment"]',
		) as HTMLTextAreaElement,
		trendingDraftCount: root.querySelector(
			'[data-field="trendingDraftCount"]',
		) as HTMLInputElement,
		generateTrendingButton: root.querySelector(
			'[data-action="generate-trending"]',
		) as HTMLButtonElement,
		sendToDraftButton: root.querySelector(
			'[data-action="send-to-draft"]',
		) as HTMLButtonElement,
		sendToDraftHint: root.querySelector(
			'[data-slot="send-to-draft-hint"]',
		) as HTMLElement,
		trendingResults: root.querySelector(
			'[data-slot="trending-results"]',
		) as HTMLElement,
		views: root.querySelectorAll("[data-view]") as NodeListOf<HTMLElement>,
		settingsPages: root.querySelectorAll(
			"[data-settings-view]",
		) as NodeListOf<HTMLElement>,
	};
	const hotEventTooltip = document.createElement("div");
	hotEventTooltip.className = "smc-floating-tooltip";
	hotEventTooltip.hidden = true;
	document.body.appendChild(hotEventTooltip);
	let activeTooltipTarget: HTMLElement | null = null;

	applyApiModeGuard();

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

	ui.unlockDebugButton.addEventListener("click", () => {
		handleDebugUnlockTap();
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

	ui.trendingComment.addEventListener("input", () => {
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
			STATE.hasUnreadDraftResult = false;
			render();
		});

	root
		.querySelector('[data-action="refresh-hot-events"]')
		.addEventListener("click", async () => {
			await loadHotEvents(true);
		});

	root
		.querySelector('[data-action="generate-trending"]')
		.addEventListener("click", async () => {
			await handleTrendingGenerate();
		});

	root
		.querySelector('[data-action="send-to-draft"]')
		.addEventListener("click", () => {
			handleSendToDraft();
		});

	root
		.querySelector('[data-action="clear-trending-results"]')
		.addEventListener("click", () => {
			STATE.trendingGenerated = null;
			STATE.lastTrendingDurationMs = null;
			STATE.trendingErrorHint = "";
			renderTrendingResults();
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
	window.addEventListener("resize", () => {
		positionHotEventTooltip();
	});

	function switchTab(tabName: string | null): void {
		hideHotEventTooltip();
		let nextTab: PanelTab = "profile";
		if (tabName === "draft") {
			nextTab = "draft";
		} else if (tabName === "trending") {
			nextTab = "trending";
		}
		STATE.activeTab = nextTab;
		if (nextTab === "draft") {
			STATE.hasUnreadDraftResult = false;
		}
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
		renderTabNotifications();
		if (
			nextTab === "trending" &&
			!STATE.hotEventsLoading &&
			STATE.hotEvents.length === 0
		) {
			void loadHotEvents(false);
		}
		if (nextTab === "trending") {
			void ensureLocalTrendingCapability(false);
		}
	}

	function openSettingsView(): void {
		STATE.currentView = "settings";
		STATE.settingsPage = "home";
		loadSettingsUI({ syncApiForm: true });
		render();
	}

	function openApiSettingsPage(): void {
		if (!STATE.debugModeUnlocked) {
			return;
		}
		STATE.currentView = "settings";
		STATE.settingsPage = "api";
		loadSettingsUI({ syncApiForm: true });
		render();
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
			render();
			return;
		}
		STATE.currentView = "main";
		render();
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
		STATE.config = configResponse.config || SETTINGS_DEFAULTS;
		await ensureReleaseBackendDefaults();
		await enforceDraftsApiMode();
		applyTheme(STATE.config?.theme);
		hydrateInputs();
		if (STATE.config?.defaultUsername) {
			await handleLoadProfile();
		}
		await refreshHealth();
		await refreshComposerState();
		await ensureLocalTrendingCapability(true);
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

	async function ensureLocalTrendingCapability(
		forceRefresh: boolean,
	): Promise<void> {
		try {
			const response =
				await sendRuntimeMessage<PanelLocalTrendingCapabilityResponse>({
					type: "check_local_trending_capability",
					payload: { refresh: forceRefresh },
				});
			const supported = Boolean(response?.result?.supported);
			if (!supported) {
				const capabilityMessage = String(
					response?.result?.message || "",
				).trim();
				STATE.trendingErrorHint = capabilityMessage
					? sanitizeUserVisibleErrorMessage(
							capabilityMessage,
							tr("error.serviceUnavailable"),
						)
					: `Configured backend is outdated. Update or restart ${getConfiguredBackendBaseUrl()} with the latest code.`;
				renderTrendingResults();
				renderSendToDraftButton();
				return;
			}
			if (!STATE.trendingGenerated) {
				STATE.trendingErrorHint = "";
				renderTrendingResults();
				renderSendToDraftButton();
			}
		} catch (error) {
			if (!STATE.trendingGenerated) {
				STATE.trendingErrorHint = sanitizeUserVisibleErrorMessage(
					(error as Error | undefined)?.message || "",
					tr("error.serviceUnavailable"),
				);
				renderTrendingResults();
				renderSendToDraftButton();
			}
		}
	}

	function applyApiModeGuard(): void {
		ui.sBackendBaseUrl.readOnly = false;
		ui.sApiModeContent.disabled = true;
	}

	function getConfiguredBackendBaseUrl(): string {
		return (
			String(
				STATE.config?.backendBaseUrl || SETTINGS_DEFAULTS.backendBaseUrl,
			).trim() || SETTINGS_DEFAULTS.backendBaseUrl
		);
	}

	function getResolvedLocale(): StakedMediaLocale {
		const languageSetting =
			STATE.config?.language || SETTINGS_DEFAULTS.language;
		return resolveLocale(languageSetting, navigator.language);
	}

	function tr(key: string): string {
		return t(key, getResolvedLocale());
	}

	function getVersionLabel(
		locale: StakedMediaLocale = getResolvedLocale(),
	): string {
		return `${t("settings.versionLabel", locale)}: v${EXTENSION_VERSION}`;
	}

	function getDebugModeLabel(
		locale: StakedMediaLocale = getResolvedLocale(),
	): string {
		return STATE.debugModeUnlocked
			? t("settings.debugMode", locale)
			: t("settings.productionMode", locale);
	}

	async function ensureReleaseBackendDefaults(): Promise<void> {
		if (!STATE.config) {
			return;
		}
		// Release builds always boot against the hosted Drafts API, even if an
		// older local/debug backend setting was persisted. Debug mode only
		// re-exposes the hidden settings UI; it does not bypass this reset.
		const needsHostedBackend =
			STATE.config.backendBaseUrl !== SETTINGS_DEFAULTS.backendBaseUrl ||
			STATE.config.apiMode !== "drafts";
		if (!needsHostedBackend) {
			return;
		}
		const response = await sendRuntimeMessage<PanelConfigResponse>({
			type: "save_config",
			payload: {
				backendBaseUrl: SETTINGS_DEFAULTS.backendBaseUrl,
				apiMode: "drafts",
			},
		});
		STATE.config = response.config;
	}

	function handleDebugUnlockTap(): void {
		const now = Date.now();
		const withinTapWindow =
			STATE.debugTapStartedAt > 0 &&
			now - STATE.debugTapStartedAt <= DEBUG_UNLOCK_TAP_WINDOW_MS;
		STATE.debugTapCount = withinTapWindow ? STATE.debugTapCount + 1 : 1;
		STATE.debugTapStartedAt = now;
		if (STATE.debugTapCount < 5) {
			return;
		}
		STATE.debugModeUnlocked = !STATE.debugModeUnlocked;
		STATE.debugTapCount = 0;
		STATE.debugTapStartedAt = 0;
		loadSettingsUI({ syncApiForm: true });
		render();
	}

	function trf(
		key: string,
		values: Record<string, string | number | null | undefined>,
	): string {
		let template = tr(key);
		for (const [name, value] of Object.entries(values)) {
			template = template.split(`{${name}}`).join(String(value ?? ""));
		}
		return template;
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

	async function enforceDraftsApiMode(): Promise<void> {
		if (!STATE.config) {
			return;
		}
		if (STATE.config.apiMode === "drafts") {
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
		} catch (error) {
			renderStatus(formatRuntimeError(error), "warn");
		}
	}

	function loadSettingsUI(options: { syncApiForm?: boolean } = {}): void {
		const syncApiForm = options.syncApiForm !== false;
		const config = STATE.config || {};
		const merged = { ...SETTINGS_DEFAULTS, ...config };
		if (syncApiForm) {
			ui.sBackendBaseUrl.value =
				merged.backendBaseUrl || SETTINGS_DEFAULTS.backendBaseUrl;
			ui.sApiModeDrafts.checked = merged.apiMode === "drafts";
			ui.sApiModeContent.checked = merged.apiMode === "content";
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
		if (ui.settingsVersion) {
			ui.settingsVersion.textContent = getVersionLabel();
		}
		if (ui.settingsVersionMode) {
			ui.settingsVersionMode.textContent = getDebugModeLabel();
		}
		if (ui.openApiSettingsButton) {
			ui.openApiSettingsButton.hidden = !STATE.debugModeUnlocked;
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
				"Only Drafts API mode is currently enabled.",
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
		const nextValue = String(ui.sBackendBaseUrl.value || "").trim();
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
					backendBaseUrl: nextValue,
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
		if (hasOperationInFlight()) {
			return;
		}
		const username = ui.username.value.trim();
		if (!username) {
			renderStatus(tr("profile.usernameRequired"), "error");
			return;
		}
		renderUsernameError("");
		renderStatus("", "");
		STATE.profileLoading = true;
		STATE.profileLoadingAction = "load";
		renderProfileButtons();
		renderProfileInfo();
		try {
			const response = await sendRuntimeMessage<PanelCheckProfileResponse>({
				type: "check_profile",
				payload: { username },
			});
			STATE.profile = response.profile;
			renderView();
			renderUsernameError("");
			renderStatus("", "");
			renderProfileInfo();
		} catch (error) {
			STATE.profile = null;
			renderView();
			renderProfileInfo();
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			} else {
				renderStatus(formatRuntimeError(error), "error");
			}
		} finally {
			STATE.profileLoading = false;
			STATE.profileLoadingAction = "";
			renderProfileButtons();
			renderProfileInfo();
		}
	}

	async function handleIngestProfile(): Promise<void> {
		if (hasOperationInFlight()) {
			return;
		}
		const username = ui.username.value.trim();
		if (!username) {
			renderStatus(tr("profile.usernameRequired"), "error");
			return;
		}
		renderUsernameError("");
		renderStatus("", "");
		STATE.profileLoading = true;
		STATE.profileLoadingAction = "ingest";
		renderProfileButtons();
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
			renderView();
			renderUsernameError("");
			renderProfileInfo();
			renderStatus(
				trf("profile.ingestSuccess", {
					count: response.result.fetched_tweet_count ?? 0,
				}),
				"success",
			);
		} catch (error) {
			renderView();
			renderProfileInfo();
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			} else {
				renderStatus(formatRuntimeError(error), "error");
			}
		} finally {
			STATE.profileLoading = false;
			STATE.profileLoadingAction = "";
			renderProfileButtons();
			renderProfileInfo();
		}
	}

	async function handleGenerate(): Promise<void> {
		if (hasOperationInFlight()) {
			return;
		}
		const username = ui.username.value.trim();
		const idea = ui.idea.value.trim();
		if (!username || !STATE.profile) {
			shakeHeaderTitle();
			renderStatus("", "");
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
		STATE.hasUnreadDraftResult = false;
		setLoading(true, "draft");
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
			STATE.hasUnreadDraftResult = STATE.activeTab !== "draft";
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
			renderSelectedHotEventInfo();
			return;
		}
		STATE.hotEventsLoading = true;
		renderHotEvents();
		renderSelectedHotEventInfo();
		try {
			const response = await sendRuntimeMessage<PanelHotEventsResponse>({
				type: "get_hot_events",
				payload: {
					hours: 24,
					limit: 50,
					refresh: forceRefresh,
					lang: getResolvedLocale(),
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
			STATE.hotEventsLastRefreshedAt = String(
				response.result?.last_refreshed_at || "",
			).trim();
			STATE.hotEventsLastAttemptedAt = String(
				response.result?.last_attempted_at || "",
			).trim();
			STATE.hotEventsRefreshIntervalSeconds = Number.isFinite(
				Number(response.result?.refresh_interval_seconds),
			)
				? Number(response.result?.refresh_interval_seconds)
				: 0;
			STATE.hotEventsIsStale = Boolean(response.result?.is_stale);
			STATE.hotEventsRefreshing = Boolean(response.result?.refreshing);
			STATE.hotEventsThrottled = Boolean(response.result?.throttled);
			STATE.hotEventsNextRefreshAvailableInSeconds = Number.isFinite(
				Number(response.result?.next_refresh_available_in_seconds),
			)
				? Number(response.result?.next_refresh_available_in_seconds)
				: 0;
			STATE.hotEventsLastRefreshError = String(
				response.result?.last_refresh_error || "",
			).trim();
			STATE.hotEventsShowOriginal = Object.fromEntries(
				Object.entries(STATE.hotEventsShowOriginal).filter(([eventId]) =>
					nextItems.some((item) => getHotEventId(item) === eventId),
				),
			);
			STATE.hotEventsExpandedSummary = Object.fromEntries(
				Object.entries(STATE.hotEventsExpandedSummary).filter(([eventId]) =>
					nextItems.some((item) => getHotEventId(item) === eventId),
				),
			);
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
			renderSelectedHotEventInfo();
			renderStatus("", "");
		} catch (error) {
			renderStatus(formatApiError(error), "error");
		} finally {
			STATE.hotEventsLoading = false;
			renderHotEvents();
			renderSelectedHotEventInfo();
		}
	}

	function showHotEventTooltip(target: HTMLElement, text: string): void {
		const nextText = String(text || "").trim();
		if (!nextText) {
			hideHotEventTooltip();
			return;
		}
		activeTooltipTarget = target;
		hotEventTooltip.textContent = nextText;
		hotEventTooltip.hidden = false;
		hotEventTooltip.setAttribute("data-visible", "true");
		positionHotEventTooltip();
	}

	function hideHotEventTooltip(): void {
		activeTooltipTarget = null;
		hotEventTooltip.hidden = true;
		hotEventTooltip.textContent = "";
		hotEventTooltip.removeAttribute("data-visible");
		hotEventTooltip.style.removeProperty("left");
		hotEventTooltip.style.removeProperty("top");
		hotEventTooltip.style.removeProperty("--smc-tooltip-arrow-left");
	}

	function positionHotEventTooltip(): void {
		if (!activeTooltipTarget || hotEventTooltip.hidden) {
			return;
		}
		const targetRect = activeTooltipTarget.getBoundingClientRect();
		if (targetRect.width <= 0 || targetRect.height <= 0) {
			hideHotEventTooltip();
			return;
		}
		const margin = 8;
		hotEventTooltip.style.left = "0px";
		hotEventTooltip.style.top = "0px";
		const tooltipWidth = hotEventTooltip.offsetWidth;
		const tooltipHeight = hotEventTooltip.offsetHeight;
		const maxLeft = Math.max(margin, window.innerWidth - tooltipWidth - margin);
		const left = Math.min(
			Math.max(targetRect.right - tooltipWidth, margin),
			maxLeft,
		);
		const top = Math.min(
			targetRect.bottom + 8,
			Math.max(margin, window.innerHeight - tooltipHeight - margin),
		);
		const arrowLeft = Math.min(
			Math.max(targetRect.right - left - 12, 12),
			Math.max(12, tooltipWidth - 12),
		);
		hotEventTooltip.style.left = `${Math.round(left)}px`;
		hotEventTooltip.style.top = `${Math.round(top)}px`;
		hotEventTooltip.style.setProperty(
			"--smc-tooltip-arrow-left",
			`${Math.round(arrowLeft)}px`,
		);
	}

	function renderHotEvents(preserveScroll = false): void {
		if (!ui.hotEvents || !ui.hotEventsMeta) {
			return;
		}
		hideHotEventTooltip();
		const previousHotEventsList = ui.hotEvents.querySelector(
			'[data-slot="hot-events-list"]',
		) as HTMLElement | null;
		const preservedScrollTop =
			preserveScroll && previousHotEventsList
				? previousHotEventsList.scrollTop
				: 0;
		if (STATE.hotEventsLoading) {
			ui.hotEventsMeta.innerHTML = "Loading 24h hot events...";
			ui.hotEvents.innerHTML =
				'<div class="smc-empty">Loading hot events...</div>';
			return;
		}
		if (!STATE.hotEvents.length) {
			const warningHtml = renderHotWarnings();
			const stateNoticeHtml = renderHotEventsStateNotice();
			ui.hotEventsMeta.innerHTML = `${stateNoticeHtml}${warningHtml}`;
			ui.hotEvents.innerHTML =
				'<div class="smc-empty">No hot events available right now.</div>';
			return;
		}
		const refreshedAtLabel = STATE.hotEventsLastRefreshedAt
			? `Snapshot updated ${formatHotEventsTimestamp(
					STATE.hotEventsLastRefreshedAt,
				)}`
			: "";
		const summaryLabel = escapeHtml(
			`${STATE.hotEvents.length} events in last 24h. ${refreshedAtLabel}`.trim(),
		);
		const warningHtml = renderHotWarnings();
		const stateNoticeHtml = renderHotEventsStateNotice();
		ui.hotEventsMeta.innerHTML = `<div>${summaryLabel}</div>${stateNoticeHtml}${warningHtml}`;
		ui.hotEvents.innerHTML = `
      <div class="smc-hot-list-frame">
        <div class="smc-hot-list" data-slot="hot-events-list">
          ${STATE.hotEvents
						.map((event, index) => {
							const eventId = getHotEventId(event);
							if (!eventId) {
								return "";
							}
							const isSelected = eventId === STATE.selectedHotEventId;
							const display = getDisplayedHotEventText(event);
							const title = escapeHtml(display.title || "Untitled event");
							const summaryState = getHotEventSummaryState(
								eventId,
								display.summary,
							);
							const summary = escapeHtml(summaryState.text);
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
							const showingOriginal = isShowingOriginalHotEvent(eventId);
							const translationToggleTitle = event.is_translated
								? escapeHtml(
										showingOriginal
											? tr("action.showTranslation")
											: tr("action.showOriginal"),
									)
								: "";
							const translationToggleClass = showingOriginal
								? "smc-hot-translate-button-original"
								: "smc-hot-translate-button-translated";
							const summaryToggleLabel = summaryState.truncated
								? escapeHtml(
										summaryState.expanded
											? tr("action.showLess")
											: tr("action.showMore"),
									)
								: "";
							return `
              <article class="smc-hot-event-card ${isSelected ? "smc-hot-event-selected" : ""}" data-action="select-hot-event-card" data-hot-event-id="${escapeHtml(eventId)}" role="button" tabindex="0">
                <div class="smc-hot-event-head">
                  <div class="smc-hot-event-head-main">
                    <span class="smc-hot-event-rank">#${index + 1}</span>
                    <span class="smc-hot-event-type smc-hot-event-type-${contentType}">${contentType}</span>
                    <span class="smc-hot-event-meta">${sourceLabel} | ${relativeAge}</span>
                  </div>
                  <div class="smc-hot-event-score-group">
                    <span class="smc-hot-event-score">${heatScore}</span>
                    ${
											event.is_translated
												? `<button class="smc-hot-translate-button ${translationToggleClass}" data-action="toggle-hot-event-original" data-hot-event-id="${escapeHtml(eventId)}" data-tooltip-label="${translationToggleTitle}" type="button" aria-label="${translationToggleTitle}" aria-pressed="${showingOriginal ? "true" : "false"}">
                        <svg viewBox="0 0 16 16" aria-hidden="true" focusable="false">
                          <path d="M3.5 3.5h5m-2.5 0c0 4-1.3 6.5-3.2 8m3.2-8c.8 1.7 2 3.3 3.6 4.8m-5.5 1.2h5.8m2.2 0 1.2 3m-1.2-3-1.2-3-1.2 3m2.4 0h-2.4" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.2"/>
                        </svg>
                      </button>`
												: ""
										}
                  </div>
                </div>
                <h3 class="smc-hot-event-title">${title}</h3>
                ${
									summary
										? `<p class="smc-hot-event-summary">${summary}${
												summaryState.truncated
													? ` <button class="smc-hot-summary-toggle" data-action="toggle-hot-event-summary" data-hot-event-id="${escapeHtml(eventId)}" type="button">${summaryToggleLabel}</button>`
													: ""
											}</p>`
										: ""
								}
                <div class="smc-hot-event-actions">
                  <button class="smc-hot-select-button ${isSelected ? "smc-hot-select-button-selected" : ""}" data-action="select-hot-event" data-hot-event-id="${escapeHtml(eventId)}" type="button" aria-pressed="${isSelected ? "true" : "false"}">
                    ${
											isSelected
												? '<svg viewBox="0 0 16 16" aria-hidden="true" focusable="false"><path d="M3.2 8.4 6.3 11.5 12.8 5" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8"/></svg>'
												: ""
										}
                    <span>${escapeHtml(isSelected ? tr("action.selected") : tr("action.select"))}</span>
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
			STATE.selectedHotEventId =
				STATE.selectedHotEventId === normalizedEventId ? "" : normalizedEventId;
			STATE.trendingErrorHint = "";
			renderHotEvents(true);
			renderSelectedHotEventInfo();
			renderSendToDraftButton();
		};
		(
			ui.hotEvents.querySelectorAll(
				'[data-action="toggle-hot-event-original"]',
			) as NodeListOf<HTMLButtonElement>
		).forEach((button) => {
			button.addEventListener("pointerdown", (pointerEvent) => {
				pointerEvent.stopPropagation();
				hideHotEventTooltip();
			});
			button.addEventListener("mouseenter", () => {
				showHotEventTooltip(
					button,
					String(button.getAttribute("data-tooltip-label") || ""),
				);
			});
			button.addEventListener("mouseleave", () => {
				hideHotEventTooltip();
			});
			button.addEventListener("focus", () => {
				showHotEventTooltip(
					button,
					String(button.getAttribute("data-tooltip-label") || ""),
				);
			});
			button.addEventListener("blur", () => {
				hideHotEventTooltip();
			});
			button.addEventListener("click", (clickEvent) => {
				clickEvent.stopPropagation();
				hideHotEventTooltip();
				const eventId = String(button.getAttribute("data-hot-event-id") || "");
				if (!eventId) {
					return;
				}
				STATE.hotEventsShowOriginal[eventId] =
					!isShowingOriginalHotEvent(eventId);
				renderHotEvents(true);
				renderSelectedHotEventInfo();
			});
		});
		(
			ui.hotEvents.querySelectorAll(
				'[data-action="toggle-hot-event-summary"]',
			) as NodeListOf<HTMLButtonElement>
		).forEach((button) => {
			button.addEventListener("pointerdown", (pointerEvent) => {
				pointerEvent.stopPropagation();
			});
			button.addEventListener("click", (clickEvent) => {
				clickEvent.stopPropagation();
				const eventId = String(button.getAttribute("data-hot-event-id") || "");
				if (!eventId) {
					return;
				}
				STATE.hotEventsExpandedSummary[eventId] =
					!isHotEventSummaryExpanded(eventId);
				renderHotEvents(true);
				renderSelectedHotEventInfo();
			});
		});
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
				pickHotEvent(String(button.getAttribute("data-hot-event-id") || ""));
			});
		});
		(
			ui.hotEvents.querySelectorAll(
				'[data-action="select-hot-event-card"]',
			) as NodeListOf<HTMLElement>
		).forEach((card) => {
			card.addEventListener("click", () => {
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
		if (preservedScrollTop > 0) {
			const nextHotEventsList = ui.hotEvents.querySelector(
				'[data-slot="hot-events-list"]',
			) as HTMLElement | null;
			if (nextHotEventsList) {
				nextHotEventsList.scrollTop = preservedScrollTop;
			}
		}
		const currentHotEventsList = ui.hotEvents.querySelector(
			'[data-slot="hot-events-list"]',
		) as HTMLElement | null;
		currentHotEventsList?.addEventListener("scroll", () => {
			hideHotEventTooltip();
		});
	}

	function renderHotWarnings(): string {
		if (!STATE.hotEventsWarnings.length) {
			return "";
		}
		const body = STATE.hotEventsWarnings
			.filter(
				(item) =>
					item && !/^opentwitter unavailable:/i.test(String(item || "").trim()),
			)
			.map((item) => escapeHtml(item))
			.join(" | ");
		if (!body) {
			return "";
		}
		return `<div class="smc-hot-warning">${body}</div>`;
	}

	function renderHotEventsStateNotice(): string {
		const parts = deriveHotEventsStateNotice({
			refreshing: STATE.hotEventsRefreshing,
			isStale: STATE.hotEventsIsStale,
			throttled: STATE.hotEventsThrottled,
			nextRefreshAvailableInSeconds:
				STATE.hotEventsNextRefreshAvailableInSeconds,
			lastRefreshedAt: STATE.hotEventsLastRefreshedAt,
			lastAttemptedAt: STATE.hotEventsLastAttemptedAt,
			lastRefreshError: STATE.hotEventsLastRefreshError,
			formatTimestamp: formatHotEventsTimestamp,
		});
		if (!parts.length) {
			return "";
		}
		return `<div class="smc-hot-warning">${escapeHtml(parts.join(" "))}</div>`;
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

	function formatHotEventsTimestamp(value: string): string {
		const parsed = Date.parse(value);
		if (!Number.isFinite(parsed)) {
			return value;
		}
		return new Date(parsed).toLocaleTimeString();
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
			title_translated:
				String(event?.title_translated || "").trim() || undefined,
			summary_translated:
				String(event?.summary_translated || "").trim() || undefined,
			is_translated: Boolean(event?.is_translated),
			author_handle: String(event?.author_handle || "").trim() || undefined,
		};
	}

	function isShowingOriginalHotEvent(eventId: string): boolean {
		return Boolean(STATE.hotEventsShowOriginal[String(eventId || "").trim()]);
	}

	function isHotEventSummaryExpanded(eventId: string): boolean {
		return Boolean(
			STATE.hotEventsExpandedSummary[String(eventId || "").trim()],
		);
	}

	function getHotEventSummaryState(
		eventId: string,
		summary: string,
		maxChars = 50,
	): {
		text: string;
		truncated: boolean;
		expanded: boolean;
	} {
		const normalizedSummary = String(summary || "").trim();
		if (!normalizedSummary) {
			return {
				text: "",
				truncated: false,
				expanded: false,
			};
		}
		const expanded = isHotEventSummaryExpanded(eventId);
		if (expanded || normalizedSummary.length <= maxChars) {
			return {
				text: normalizedSummary,
				truncated: normalizedSummary.length > maxChars,
				expanded,
			};
		}
		return {
			text: `${normalizedSummary.slice(0, maxChars).trimEnd()}...`,
			truncated: true,
			expanded: false,
		};
	}

	function getDisplayedHotEventText(event: PanelHotEventRecord): {
		title: string;
		summary: string;
	} {
		const eventId = getHotEventId(event);
		const showOriginal = isShowingOriginalHotEvent(eventId);
		if (event.is_translated && !showOriginal) {
			return {
				title: String(event.title_translated || event.title || "").trim(),
				summary: String(event.summary_translated || event.summary || "").trim(),
			};
		}
		return {
			title: String(event.title || "").trim(),
			summary: String(event.summary || "").trim(),
		};
	}

	function renderSelectedHotEventInfo(): void {
		if (!ui.selectedHotEventInfo) {
			return;
		}
		const selectedEvent = STATE.hotEvents.find(
			(item) => getHotEventId(item) === STATE.selectedHotEventId,
		);
		if (!selectedEvent) {
			ui.selectedHotEventInfo.innerHTML = "";
			ui.selectedHotEventInfo.hidden = true;
			return;
		}
		const display = getDisplayedHotEventText(selectedEvent);
		const title = escapeHtml(display.title || "Untitled event");
		ui.selectedHotEventInfo.innerHTML = `
      <div class="smc-selected-event-info">
        <div class="smc-selected-event-status">${escapeHtml(
					tr("hint.hotEventSelected"),
				)}</div>
        <div class="smc-selected-event-title">${title}</div>
      </div>
    `;
		ui.selectedHotEventInfo.hidden = false;
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

	async function handleTrendingGenerate(): Promise<void> {
		if (hasOperationInFlight()) {
			return;
		}
		const username = ui.username.value.trim();
		if (!username || !STATE.profile) {
			shakeHeaderTitle();
			renderStatus("", "");
			return;
		}
		const selectedEvent = STATE.hotEvents.find(
			(item) => getHotEventId(item) === STATE.selectedHotEventId,
		);
		if (!selectedEvent) {
			STATE.trendingErrorHint = tr("hint.selectHotEventBeforeGenerate");
			renderStatus("", "");
			renderSendToDraftButton();
			shakeTrendingHint();
			return;
		}
		const payload = {
			username,
			event_id: getHotEventId(selectedEvent),
			event_payload: selectedEvent,
			comment: ui.trendingComment.value || "",
			draft_count: ui.trendingDraftCount.value || "3",
		};
		renderUsernameError("");
		renderStatus("", "");
		await runTrendingGeneration(payload);
	}

	async function runTrendingGeneration(payload: {
		username: string;
		event_id: string;
		event_payload: PanelHotEventRecord;
		comment: string;
		draft_count: string;
	}): Promise<void> {
		setLoading(true, "trending");
		const startedAt = performance.now();
		STATE.trendingErrorHint = "";
		try {
			const response = await sendRuntimeMessage<PanelGenerateResponse>({
				type: "trending_generate",
				payload,
			});
			STATE.trendingGenerated = response.result;
			STATE.lastTrendingDurationMs = Math.round(performance.now() - startedAt);
			const draftCount = extractDrafts(STATE.trendingGenerated).length;
			if (!draftCount) {
				STATE.lastTrendingDurationMs = null;
				STATE.trendingErrorHint =
					"Trending request completed but returned no drafts. Please refresh hot events and try again.";
				renderStatus(STATE.trendingErrorHint, "warn");
				renderTrendingResults();
				renderSendToDraftButton();
				return;
			}
			const durationLabel =
				STATE.lastTrendingDurationMs != null
					? ` in ${STATE.lastTrendingDurationMs} ms`
					: "";
			renderStatus(
				`Generated ${draftCount} trending draft${draftCount === 1 ? "" : "s"}${durationLabel}.`,
				"success",
			);
			renderTrendingResults();
			renderSendToDraftButton();
		} catch (error) {
			STATE.trendingGenerated = null;
			STATE.lastTrendingDurationMs = null;
			STATE.trendingErrorHint = formatApiError(error);
			if (isWhitelistDeniedError(error)) {
				renderUsernameError(formatRuntimeError(error));
			}
			renderStatus(STATE.trendingErrorHint, "error");
			renderTrendingResults();
			renderSendToDraftButton();
		} finally {
			setLoading(false);
		}
	}

	function handleSendToDraft(): void {
		if (!getSelectedHotEventRecord()) {
			STATE.trendingErrorHint = tr("hint.selectHotEventBeforeGenerate");
			renderStatus("", "");
			renderSendToDraftButton();
			shakeTrendingHint();
			return;
		}
		const draftIdea = getCurrentTrendingConclusion();
		if (!draftIdea) {
			renderStatus("No trending content available to send.", "error");
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
		const comment = String(ui.trendingComment.value || "").trim();
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

	function getGeneratedTrendingConclusion(): string {
		const drafts = extractDrafts(STATE.trendingGenerated) as PanelDraftLike[];
		return getDraftText(drafts, 0).trim();
	}

	function getCurrentTrendingConclusion(): string {
		const generatedConclusion = getGeneratedTrendingConclusion();
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
		if (!ui.trendingDraftCount.value) {
			ui.trendingDraftCount.value = "3";
		}
	}

	function render(): void {
		applyLocalizedContent();
		renderSettingsControls();
		renderView();
		renderTabNotifications();
		renderProfileButtons();
		renderGenerateButton();
		renderConnectionDot();
		renderUsernameError(STATE.usernameError);
		renderProfileInfo();
		renderResults();
		renderHotEvents();
		renderSelectedHotEventInfo();
		renderTrendingResults();
		renderSendToDraftButton();
		renderComposerState();
	}

	function renderSettingsControls(): void {
		if (ui.settingsVersion) {
			ui.settingsVersion.textContent = getVersionLabel();
		}
		if (ui.settingsVersionMode) {
			ui.settingsVersionMode.textContent = getDebugModeLabel();
		}
		if (ui.openApiSettingsButton) {
			ui.openApiSettingsButton.hidden = !STATE.debugModeUnlocked;
		}
	}

	function renderTabNotifications(): void {
		if (!ui.draftTabButton) {
			return;
		}
		ui.draftTabButton.setAttribute(
			"data-has-notification",
			STATE.hasUnreadDraftResult ? "true" : "false",
		);
	}

	function renderView(): void {
		const locale = getResolvedLocale();
		const isSettingsView = STATE.currentView === "settings";
		if (STATE.settingsPage === "api" && !STATE.debugModeUnlocked) {
			STATE.settingsPage = "home";
		}
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
				if (STATE.profile?.username) {
					ui.headerTitle.textContent = `@${STATE.profile.username}`;
					ui.headerTitle.classList.remove("smc-title-attention");
				} else {
					ui.headerTitle.textContent = `* ${t("app.titleNoProfile", locale)}`;
					ui.headerTitle.classList.add("smc-title-attention");
				}
			} else if (STATE.settingsPage === "api" && STATE.debugModeUnlocked) {
				ui.headerTitle.textContent = t("settings.apiPageTitle", locale);
				ui.headerTitle.classList.remove("smc-title-attention");
			} else {
				ui.headerTitle.textContent = t("app.title", locale);
				ui.headerTitle.classList.remove("smc-title-attention");
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

	function hasOperationInFlight(): boolean {
		return STATE.loading || STATE.profileLoading;
	}

	function getLoadingIndicatorDots(): string {
		if (!STATE.generationStartedAt) {
			return ".";
		}
		const elapsedMs = Date.now() - STATE.generationStartedAt;
		const frame = Math.floor(elapsedMs / 400) % 3;
		return ".".repeat(frame + 1);
	}

	function getThinkingLabel(): string {
		return `${tr("action.generating")}${getLoadingIndicatorDots()}`;
	}

	function renderProfileButtons(): void {
		const operationBusy = hasOperationInFlight();
		const buttons = [
			{
				element: ui.loadProfileButton,
				busy: STATE.profileLoading && STATE.profileLoadingAction === "load",
				label: tr("action.load"),
			},
			{
				element: ui.ingestProfileButton,
				busy: STATE.profileLoading && STATE.profileLoadingAction === "ingest",
				label: tr("action.ingest"),
			},
		];

		buttons.forEach(({ element, busy, label }) => {
			if (!element) {
				return;
			}
			element.disabled = operationBusy;
			element.classList.toggle("smc-button-loading", busy);
			element.setAttribute("aria-busy", busy ? "true" : "false");
			element.innerHTML = busy
				? `<span class="smc-button-content"><span class="smc-button-spinner" aria-hidden="true"></span><span>${escapeHtml(
						label,
					)}</span></span>`
				: escapeHtml(label);
		});
	}

	function renderGenerateButton(): void {
		if (!ui.generateButton) {
			return;
		}
		const operationBusy = hasOperationInFlight();
		const isDraftLoading = STATE.loading;
		ui.generateButton.disabled = operationBusy;
		ui.generateButton.classList.toggle("smc-button-loading", isDraftLoading);
		ui.generateButton.setAttribute(
			"aria-busy",
			isDraftLoading ? "true" : "false",
		);
		ui.generateButton.innerHTML = isDraftLoading
			? `<span class="smc-button-content"><span>${escapeHtml(getThinkingLabel())}</span></span>`
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

	function shakeHeaderTitle(): void {
		shakeElement(ui.headerTitle);
	}

	function shakeTrendingHint(): void {
		shakeElement(ui.sendToDraftHint);
	}

	function shakeElement(element: HTMLElement | null | undefined): void {
		if (!element) return;
		element.classList.remove("smc-shake");
		void element.offsetWidth;
		element.classList.add("smc-shake");
		element.addEventListener(
			"animationend",
			() => element.classList.remove("smc-shake"),
			{ once: true },
		);
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
			ui.profileInfo.innerHTML = `<div class="smc-profile-hint">${escapeHtml(tr("profile.loading"))}</div>`;
			return;
		}
		if (!STATE.profile) {
			ui.profileInfo.innerHTML = "";
			return;
		}
		if (!STATE.profile.exists) {
			ui.profileInfo.innerHTML = `<div class="smc-profile-hint smc-profile-hint-warn">${escapeHtml(tr("profile.notFound"))}</div>`;
			return;
		}
		const p = STATE.profile.profile || {};

		if (!STATE.profile.personaReady) {
			ui.profileInfo.innerHTML = `<div class="smc-profile-hint smc-profile-hint-warn">${escapeHtml(tr("profile.personaMissing"))}</div>`;
			return;
		}

		const personaStatus = STATE.profile.personaReady
			? tr("profile.personaReady")
			: tr("profile.personaMissingStatus");
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
          <div class="smc-persona-title">${escapeHtml(tr("profile.personaPortrait"))}</div>
          ${persona.author_summary ? `<div class="smc-persona-item"><strong>${escapeHtml(tr("profile.summary"))}:</strong> ${escapeHtml(persona.author_summary)}</div>` : ""}
          ${persona.voice_traits?.length ? `<div class="smc-persona-item"><strong>${escapeHtml(tr("profile.voice"))}:</strong> ${escapeHtml(persona.voice_traits.join(", "))}</div>` : ""}
          ${
						persona.topic_clusters?.length
							? `<div class="smc-persona-item"><strong>${escapeHtml(tr("profile.topics"))}:</strong> ${escapeHtml(
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
          <strong>${escapeHtml(tr("profile.cardTitle"))}</strong>
          <span class="smc-profile-username">@${escapeHtml(STATE.profile.username)}</span>
        </div>
        <div class="smc-profile-row">
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">${escapeHtml(tr("profile.followers"))}</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(p.followers_count || 0))}</span>
          </div>
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">${escapeHtml(tr("profile.following"))}</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(p.following_count || 0))}</span>
          </div>
          <div class="smc-profile-stat">
            <span class="smc-profile-stat-label">${escapeHtml(tr("profile.tweets"))}</span>
            <span class="smc-profile-stat-value">${escapeHtml(String(STATE.profile.storedTweetCount || 0))}</span>
          </div>
        </div>
        ${personaSection}
        <div class="smc-profile-footer">
          <span class="smc-profile-status ${personaClass}">${escapeHtml(tr("profile.persona"))}: ${escapeHtml(personaStatus)}</span>
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

	function renderTrendingResults(): void {
		renderDraftCards({
			target: ui.trendingResults,
			source: STATE.trendingGenerated,
			durationMs: STATE.lastTrendingDurationMs,
			emptyMessage: getTrendingEmptyMessage(),
		});
	}

	function getTrendingEmptyMessage(): string {
		const hint = String(STATE.trendingErrorHint || "").trim();
		if (hint) {
			return hint;
		}
		return "No trending drafts yet.";
	}

	function renderSendToDraftButton(): void {
		if (!ui.sendToDraftButton || !ui.generateTrendingButton) {
			return;
		}
		const operationBusy = hasOperationInFlight();
		const selectedEvent = getSelectedHotEventRecord();
		const hasSelectedEvent = Boolean(selectedEvent);
		const isTrendingLoading = STATE.loading;
		const generatedConclusion = getGeneratedTrendingConclusion();
		const sendableDraftIdea = getCurrentTrendingConclusion();
		const hasDraftIdea = Boolean(sendableDraftIdea);
		ui.generateTrendingButton.disabled = operationBusy;
		ui.sendToDraftButton.disabled =
			operationBusy || (hasSelectedEvent && !hasDraftIdea);
		ui.generateTrendingButton.classList.toggle(
			"smc-button-loading",
			isTrendingLoading,
		);
		ui.generateTrendingButton.classList.toggle(
			"smc-button-guarded",
			!hasSelectedEvent && !operationBusy,
		);
		ui.sendToDraftButton.classList.toggle(
			"smc-button-guarded",
			!hasSelectedEvent && !operationBusy,
		);
		ui.generateTrendingButton.setAttribute(
			"aria-disabled",
			!hasSelectedEvent && !operationBusy ? "true" : "false",
		);
		ui.sendToDraftButton.setAttribute(
			"aria-disabled",
			!hasSelectedEvent && !operationBusy ? "true" : "false",
		);
		ui.generateTrendingButton.setAttribute(
			"aria-busy",
			isTrendingLoading ? "true" : "false",
		);
		ui.generateTrendingButton.innerHTML = isTrendingLoading
			? `<span class="smc-button-content"><span>${escapeHtml(getThinkingLabel())}</span></span>`
			: tr("action.generate");
		if (!ui.sendToDraftHint) {
			return;
		}
		let hint = "";
		if (isTrendingLoading) {
			hint = "Generating trending result...";
		} else if (!hasSelectedEvent) {
			hint =
				String(STATE.trendingErrorHint || "").trim() ||
				tr("hint.selectHotEventBeforeGenerate");
		} else if (!generatedConclusion) {
			hint = tr("hint.sendSelectedEventToDraft");
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

	function setLoading(nextLoading: boolean, action: LoadingAction = ""): void {
		STATE.loading = nextLoading;
		STATE.loadingAction = nextLoading ? action : "";
		if (nextLoading) {
			startGenerationProgress();
		} else {
			stopGenerationProgress();
		}
		renderProfileButtons();
		renderGenerateButton();
		renderSendToDraftButton();
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
				renderGenerateButton();
				renderSendToDraftButton();
				return;
			}
			STATE.generationProgress = {
				percent: nextPercent,
				message: nextMessage,
			};
			renderGenerationProgress();
			renderGenerateButton();
			renderSendToDraftButton();
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
		const configuredBaseUrl = getConfiguredBackendBaseUrl();
		if (runtimeError?.status === 404) {
			if (path.startsWith("/api/v1/profiles/")) {
				return "Profile not found in the backend. Run ingest first.";
			}
			if (path.startsWith("/api/v1/content/hot-events")) {
				if (detailText.includes("not available yet")) {
					return "Hot events snapshot is not ready yet. Refresh once or wait for the scheduler.";
				}
				return `Configured backend does not expose hot-events. Start or update backend at ${configuredBaseUrl}.`;
			}
			if (path.startsWith("/api/v1/trending/generate")) {
				if (detailText.includes("selected hot event was not found")) {
					return "Selected hot event expired. Refresh hot events and select again.";
				}
				return `Trending endpoint is unavailable on the configured backend. Start or update backend at ${configuredBaseUrl}.`;
			}
			if (path === "/openapi.json") {
				return `Configured backend OpenAPI route is unavailable. Start or update backend at ${configuredBaseUrl}.`;
			}
			return "Backend endpoint returned 404. Check API Base URL and backend version.";
		}
		if (runtimeError?.status === 409) {
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
		return sanitizeUserVisibleErrorMessage(
			(error as Error | undefined)?.message || error || "",
			tr("error.serviceUnavailable"),
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
