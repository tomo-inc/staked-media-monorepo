const {
	DEFAULT_CONFIG: OPTIONS_DEFAULT_CONFIG,
	listLanguageOptions,
	resolveLocale,
	sendRuntimeMessage,
	t,
} =
	window.StakedMediaExtensionShared;
const REMOTE_BACKEND_BASE_URL = "https://api.sayviner.top:8443";

type OptionsPage = "home" | "api";
type StatusKind = "" | "warn";

interface OptionsConfigResponse {
	config?: StakedMediaExtensionConfig;
}

interface OptionsFields {
	headerTitle: HTMLElement;
	backButton: HTMLButtonElement;
	homePage: HTMLElement;
	apiPage: HTMLElement;
	openApiSettingsButton: HTMLButtonElement;
	backendBaseUrl: HTMLInputElement;
	apiModeDrafts: HTMLInputElement;
	apiModeContent: HTMLInputElement;
	theme: HTMLSelectElement;
	language: HTMLSelectElement;
	hostModeTitle: HTMLElement;
	toggleOpenModeButton: HTMLButtonElement;
	status: HTMLElement;
}

interface OptionsState {
	config: StakedMediaExtensionConfig | null;
	page: OptionsPage;
}

const DEFAULTS = { ...OPTIONS_DEFAULT_CONFIG };
const systemThemeQuery = window.matchMedia("(prefers-color-scheme: dark)");

const state: OptionsState = {
	config: null,
	page: "home",
};

const fields: OptionsFields = {
	headerTitle: document.getElementById("headerTitle") as HTMLElement,
	backButton: document.getElementById("backButton") as HTMLButtonElement,
	homePage: document.getElementById("homePage") as HTMLElement,
	apiPage: document.getElementById("apiPage") as HTMLElement,
	openApiSettingsButton: document.getElementById(
		"openApiSettingsButton",
	) as HTMLButtonElement,
	backendBaseUrl: document.getElementById("backendBaseUrl") as HTMLInputElement,
	apiModeDrafts: document.getElementById("apiModeDrafts") as HTMLInputElement,
	apiModeContent: document.getElementById("apiModeContent") as HTMLInputElement,
	theme: document.getElementById("theme") as HTMLSelectElement,
	language: document.getElementById("language") as HTMLSelectElement,
	hostModeTitle: document.getElementById("hostModeTitle") as HTMLElement,
	toggleOpenModeButton: document.getElementById(
		"toggleOpenModeButton",
	) as HTMLButtonElement,
	status: document.getElementById("status") as HTMLElement,
};

applyRemoteApiGuard();

init().catch((error) => {
	setStatus(formatRuntimeError(error), "warn");
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

fields.language.addEventListener("change", async () => {
	await saveLanguage(fields.language.value as StakedMediaLanguageMode);
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
	const response = await sendRuntimeMessage<OptionsConfigResponse>({
		type: "get_config",
	});
	state.config = response.config || DEFAULTS;
	await enforceRemoteBackendConfig();
	applyConfig(state.config, { syncApiForm: true });
	renderPage();
	setStatus("", "");
}

function getResolvedLocale(): StakedMediaLocale {
	return resolveLocale(state.config?.language || DEFAULTS.language, navigator.language);
}

function tr(key: string): string {
	return t(key, getResolvedLocale());
}

function applyRemoteApiGuard(): void {
	fields.backendBaseUrl.readOnly = true;
	fields.backendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
	fields.apiModeContent.disabled = true;
}

async function enforceRemoteBackendConfig(): Promise<void> {
	if (!state.config) {
		return;
	}
	const currentBackendBaseUrl = String(state.config.backendBaseUrl || "").trim();
	const needsBackendBaseUrlSync = currentBackendBaseUrl !== REMOTE_BACKEND_BASE_URL;
	const needsApiModeSync = state.config.apiMode !== "drafts";
	if (!needsBackendBaseUrlSync && !needsApiModeSync) {
		return;
	}

	const response = await sendRuntimeMessage<OptionsConfigResponse>({
		type: "save_config",
		payload: {
			backendBaseUrl: REMOTE_BACKEND_BASE_URL,
			apiMode: "drafts",
		},
	});
	state.config = response.config || DEFAULTS;
}

function applyConfig(
	config: StakedMediaExtensionConfig,
	options: {
		syncApiForm?: boolean;
	} = {},
): void {
	const syncApiForm = options.syncApiForm !== false;
	const next = { ...DEFAULTS, ...config };
	state.config = next;

	if (syncApiForm) {
		fields.backendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
		fields.apiModeDrafts.checked = true;
		fields.apiModeContent.checked = false;
	}

	fields.theme.value = next.theme || "light";
	fields.language.value = next.language || "auto";
	applyLocalizedContent();
	fields.hostModeTitle.textContent = getOpenModeToggleLabel(
		next.hostMode,
		getResolvedLocale(),
	);
	applyTheme(next.theme);
}

function applyLocalizedContent(): void {
	const locale = getResolvedLocale();
	(document.querySelectorAll("[data-i18n]") as NodeListOf<HTMLElement>).forEach(
		(element) => {
			const key = String(element.getAttribute("data-i18n") || "").trim();
			if (!key) {
				return;
			}
			element.textContent = t(key, locale);
		},
	);

	const themeLightOption = fields.theme.querySelector(
		'option[value="light"]',
	) as HTMLOptionElement | null;
	const themeDarkOption = fields.theme.querySelector(
		'option[value="dark"]',
	) as HTMLOptionElement | null;
	const themeSystemOption = fields.theme.querySelector(
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

	const selectedLanguage = state.config?.language || DEFAULTS.language;
	const languageOptions = listLanguageOptions(locale);
	fields.language.innerHTML = languageOptions
		.map(
			(option) =>
				`<option value="${option.value}">${option.label}</option>`,
		)
		.join("");
	fields.language.value = selectedLanguage;
}

function renderPage(): void {
	const isApiPage = state.page === "api";
	fields.homePage.hidden = isApiPage;
	fields.apiPage.hidden = !isApiPage;
	fields.backButton.hidden = !isApiPage;
	fields.backButton.setAttribute(
		"aria-label",
		isApiPage ? tr("settings.backToSettings") : tr("settings.backToMainView"),
	);
	fields.headerTitle.textContent = isApiPage
		? tr("settings.apiPageTitle")
		: tr("settings.title");
}

async function closeCurrentPage(): Promise<void> {
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

async function saveTheme(theme: string): Promise<void> {
	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { theme },
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: false });
		setStatus("", "");
	} catch (error) {
		applyConfig(state.config || DEFAULTS, { syncApiForm: false });
		setStatus(formatRuntimeError(error), "warn");
	}
}

async function saveLanguage(language: StakedMediaLanguageMode): Promise<void> {
	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { language },
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: false });
		renderPage();
		setStatus("", "");
	} catch (error) {
		applyConfig(state.config || DEFAULTS, { syncApiForm: false });
		renderPage();
		setStatus(formatRuntimeError(error), "warn");
	}
}

async function saveApiMode(apiMode: StakedMediaApiMode): Promise<void> {
	if (apiMode !== "drafts") {
		applyConfig(state.config || DEFAULTS, { syncApiForm: true });
		setStatus("Only Drafts API mode is enabled for this remote API test phase.", "warn");
		return;
	}
	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { apiMode: "drafts" },
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: false });
		setStatus("", "");
	} catch (error) {
		applyConfig(state.config || DEFAULTS, { syncApiForm: false });
		setStatus(formatRuntimeError(error), "warn");
	}
}

async function saveBackendBaseUrl(): Promise<boolean> {
	const nextValue = REMOTE_BACKEND_BASE_URL;
	fields.backendBaseUrl.value = REMOTE_BACKEND_BASE_URL;
	const currentValue = String(
		state.config?.backendBaseUrl || DEFAULTS.backendBaseUrl,
	);

	if (nextValue === currentValue) {
		return true;
	}

	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: {
				backendBaseUrl: REMOTE_BACKEND_BASE_URL,
				apiMode: "drafts",
			},
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: true });
		await sendRuntimeMessage({ type: "health_check" });
		setStatus("", "");
		return true;
	} catch (error) {
		setStatus(formatRuntimeError(error), "warn");
		return false;
	}
}

async function switchHostMode(hostMode: StakedMediaHostMode): Promise<void> {
	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { hostMode },
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: false });
		setStatus("", "");
	} catch (error) {
		setStatus(formatRuntimeError(error), "warn");
	}
}

function applyTheme(theme: StakedMediaThemeMode | null | undefined): void {
	const requestedTheme = theme || state.config?.theme || DEFAULTS.theme;
	const resolvedTheme =
		requestedTheme === "system"
			? systemThemeQuery.matches
				? "dark"
				: "light"
			: requestedTheme;
	document.documentElement.setAttribute("data-options-theme", resolvedTheme);
}

function getOpenModeToggleLabel(
	hostMode: StakedMediaHostMode,
	locale: StakedMediaLocale,
): string {
	return hostMode === "popup"
		? t("settings.switchToSidePanel", locale)
		: t("settings.switchToPopup", locale);
}

function getNextHostMode(): StakedMediaHostMode {
	return state.config?.hostMode === "popup" ? "sidepanel" : "popup";
}

function setStatus(message: unknown, kind: StatusKind): void {
	const text = String(message || "");
	fields.status.textContent = text;
	fields.status.className = `status${kind ? ` ${kind}` : ""}`;
	fields.status.hidden = !text;
}

function formatRuntimeError(error: unknown): string {
	return String(
		(error as Error | undefined)?.message || error || "Unknown error",
	);
}
