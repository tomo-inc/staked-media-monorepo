const { DEFAULT_CONFIG: OPTIONS_DEFAULT_CONFIG, sendRuntimeMessage } =
	window.StakedMediaExtensionShared;

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
	hostModeTitle: document.getElementById("hostModeTitle") as HTMLElement,
	toggleOpenModeButton: document.getElementById(
		"toggleOpenModeButton",
	) as HTMLButtonElement,
	status: document.getElementById("status") as HTMLElement,
};

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
	applyConfig(state.config, { syncApiForm: true });
	renderPage();
	setStatus("", "");
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

function renderPage(): void {
	const isApiPage = state.page === "api";
	fields.homePage.hidden = isApiPage;
	fields.apiPage.hidden = !isApiPage;
	fields.backButton.hidden = !isApiPage;
	fields.backButton.setAttribute(
		"aria-label",
		isApiPage ? "Back to settings" : "Back",
	);
	fields.headerTitle.textContent = isApiPage ? "API & Generation" : "Settings";
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

async function saveApiMode(apiMode: StakedMediaApiMode): Promise<void> {
	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { apiMode },
		});
		applyConfig(response.config || DEFAULTS, { syncApiForm: false });
		setStatus("", "");
	} catch (error) {
		applyConfig(state.config || DEFAULTS, { syncApiForm: false });
		setStatus(formatRuntimeError(error), "warn");
	}
}

async function saveBackendBaseUrl(): Promise<boolean> {
	const nextValue = fields.backendBaseUrl.value.trim();
	const currentValue = String(
		state.config?.backendBaseUrl || DEFAULTS.backendBaseUrl,
	);

	if (nextValue === currentValue) {
		return true;
	}

	try {
		const response = await sendRuntimeMessage<OptionsConfigResponse>({
			type: "save_config",
			payload: { backendBaseUrl: nextValue },
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

function getOpenModeToggleLabel(hostMode: StakedMediaHostMode): string {
	return hostMode === "popup" ? "Switch to Side Panel" : "Switch to Popup";
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
