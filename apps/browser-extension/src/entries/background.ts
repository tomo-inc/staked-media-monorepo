importScripts("shared.js");

type BackgroundGlobalRoot = typeof globalThis & {
	StakedMediaExtensionShared: StakedMediaExtensionSharedApi;
};

interface RuntimeErrorWithStatus extends Error {
	status?: number;
	payload?: unknown;
}

interface ProfileRecord extends Record<string, unknown> {
	username?: string;
	followers_count?: number;
	following_count?: number;
}

interface PersonaSnapshotRecord extends Record<string, unknown> {
	persona?: Record<string, unknown>;
}

interface HealthApiPayload {
	status?: string;
}

interface CheckProfileApiPayload {
	profile?: ProfileRecord | null;
	stored_tweet_count?: number;
	latest_persona_snapshot?: PersonaSnapshotRecord | null;
}

interface ComposerBridgeState {
	available?: boolean;
	message?: string;
}

interface InsertComposerBridgeResponse {
	ok?: boolean;
	error?: {
		message?: string;
	} | null;
}

interface RequestJsonOptions {
	path: string;
	method: "GET" | "POST";
	body?: Record<string, unknown>;
	deniedUsername?: string;
}

interface ComposerStateResult {
	available: boolean;
	supportedPage: boolean;
	message: string;
	tabTitle: string;
	tabUrl: string;
}

interface TargetTabResult {
	tab: ChromeTabLike | null;
	windowId: number | null;
}

type BackgroundPayload = Record<string, unknown>;
type BackgroundMessage =
	| {
			type?: string;
			payload?: BackgroundPayload;
	  }
	| null
	| undefined;

const {
	DEFAULT_CONFIG: SHARED_DEFAULT_CONFIG,
	FALLBACK_BACKEND_BASE_URL,
	coerceWindowId,
	normalizeBaseUrl,
	normalizeHostMode,
	routeMessage,
	sanitizeConfig,
} = (globalThis as BackgroundGlobalRoot).StakedMediaExtensionShared;

const API = {
	healthz: "/healthz",
	profile: (username: string) =>
		`/api/v1/profiles/${encodeURIComponent(username)}`,
	ingest: "/api/v1/profiles/ingest",
	draftsGenerate: "/api/v1/drafts/generate",
	contentGenerate: "/api/v1/content/generate",
	contentIdeas: "/api/v1/content/ideas",
	exposureAnalyze: "/api/v1/exposure/analyze",
};

initializeHostBehavior();

chrome.runtime.onInstalled.addListener(async () => {
	const current = await storageGet(Object.keys(SHARED_DEFAULT_CONFIG));
	const nextConfig = sanitizeConfig(current);
	await storageSet(nextConfig);
	await applyHostMode(nextConfig.hostMode);
});

chrome.runtime.onStartup.addListener(() => {
	void initializeHostBehavior();
});

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
	handleMessage(message)
		.then((payload) => sendResponse({ ok: true, ...payload }))
		.catch((error) =>
			sendResponse({ ok: false, error: normalizeError(error) }),
		);
	return true;
});

async function handleMessage(
	message: unknown,
): Promise<Record<string, unknown>> {
	return routeMessage<BackgroundPayload, Record<string, unknown>>(
		message as BackgroundMessage,
		{
			get_config: async () => ({ config: await getConfig() }),
			save_config: async (payload) => ({
				config: await saveConfig(payload || {}),
			}),
			health_check: async () => ({ health: await healthCheck() }),
			check_profile: async (payload) => ({
				profile: await checkProfile(payload || {}),
			}),
			ingest_profile: async (payload) => ({
				result: await ingestProfile(payload || {}),
			}),
			generate: async (payload) => ({ result: await generate(payload || {}) }),
			generate_drafts: async (payload) => ({
				result: await generateDrafts(payload || {}),
			}),
			generate_content: async (payload) => ({
				result: await generateContent(payload || {}),
			}),
			suggest_ideas: async (payload) => ({
				result: await suggestIdeas(payload || {}),
			}),
			analyze_exposure: async (payload) => ({
				result: await analyzeExposure(payload || {}),
			}),
			get_composer_state: async (payload) => ({
				composer: await getComposerState(payload || {}),
			}),
			insert_text: async (payload) => ({
				result: await insertTextIntoComposer(payload || {}),
			}),
		},
	);
}

async function getConfig(): Promise<StakedMediaExtensionConfig> {
	const stored = await storageGet(Object.keys(SHARED_DEFAULT_CONFIG));
	return sanitizeConfig(stored);
}

async function saveConfig(
	patch: BackgroundPayload,
): Promise<StakedMediaExtensionConfig> {
	const nextConfig = sanitizeConfig(
		{
			...(await getConfig()),
			...patch,
		},
		{ strictBackendBaseUrl: true },
	);
	await storageSet(nextConfig);
	await applyHostMode(nextConfig.hostMode);
	return nextConfig;
}

async function getBackendBaseUrl(): Promise<string> {
	const config = await getConfig();
	return normalizeBaseUrl(config.backendBaseUrl || FALLBACK_BACKEND_BASE_URL);
}

async function healthCheck(): Promise<{
	baseUrl: string;
	status: string;
	latencyMs: number;
}> {
	const baseUrl = await getBackendBaseUrl();
	const start = performance.now();
	const payload = await requestJson<HealthApiPayload>({
		path: API.healthz,
		method: "GET",
	});
	const latencyMs = Math.round(performance.now() - start);
	return {
		baseUrl,
		status: payload.status || "ok",
		latencyMs,
	};
}

async function checkProfile({ username }: BackgroundPayload): Promise<{
	exists: boolean;
	username: string;
	storedTweetCount: number;
	personaReady: boolean;
	profile: ProfileRecord | null;
	latestPersonaSnapshot: PersonaSnapshotRecord | null;
}> {
	const normalizedUsername = assertNonEmpty(username, "username");
	try {
		const payload = await requestJson<CheckProfileApiPayload>({
			path: API.profile(normalizedUsername),
			method: "GET",
			deniedUsername: normalizedUsername,
		});
		return {
			exists: true,
			username: payload.profile?.username || normalizedUsername,
			storedTweetCount: payload.stored_tweet_count || 0,
			personaReady: Boolean(payload.latest_persona_snapshot),
			profile: payload.profile || null,
			latestPersonaSnapshot: payload.latest_persona_snapshot || null,
		};
	} catch (error) {
		const runtimeError = error as RuntimeErrorWithStatus;
		if (runtimeError && runtimeError.status === 404) {
			return {
				exists: false,
				username: normalizedUsername,
				storedTweetCount: 0,
				personaReady: false,
				profile: null,
				latestPersonaSnapshot: null,
			};
		}
		throw error;
	}
}

async function ingestProfile(
	payload: BackgroundPayload,
): Promise<Record<string, unknown>> {
	const body = {
		username: assertNonEmpty(payload.username, "username"),
	};
	const result = await requestJson<Record<string, unknown>>({
		path: API.ingest,
		method: "POST",
		body,
		deniedUsername: body.username,
	});
	await saveConfig({ defaultUsername: body.username });
	return result;
}

async function generate(payload: BackgroundPayload): Promise<unknown> {
	const config = await getConfig();
	if (config.apiMode === "drafts") {
		return generateDrafts(payload);
	}
	return generateContent(payload);
}

async function generateDrafts(payload: BackgroundPayload): Promise<unknown> {
	const body = {
		username: assertNonEmpty(payload.username, "username"),
		prompt: assertNonEmpty(payload.idea || payload.prompt, "idea"),
		draft_count: clampInt(payload.draft_count || 3, 1, 10),
	};
	const result = await requestJson<unknown>({
		path: API.draftsGenerate,
		method: "POST",
		body,
		deniedUsername: body.username,
	});
	await saveConfig({ defaultUsername: body.username });
	return result;
}

async function generateContent(payload: BackgroundPayload): Promise<unknown> {
	const body = {
		username: assertNonEmpty(payload.username, "username"),
		mode: "A",
		idea: String(payload.idea || "").trim(),
		topic: String(payload.topic || payload.idea || "").trim(),
		draft_count: clampInt(payload.draft_count || 3, 1, 10),
	};
	const result = await requestJson<unknown>({
		path: API.contentGenerate,
		method: "POST",
		body,
		deniedUsername: body.username,
	});
	await saveConfig({ defaultUsername: body.username });
	return result;
}

async function suggestIdeas(
	payload: BackgroundPayload,
): Promise<Record<string, unknown> | null> {
	const body = {
		direction: String(payload.direction || "").trim(),
		domain: String(payload.domain || "").trim(),
		topic_hint: String(payload.topic_hint || "").trim(),
		limit: clampInt(payload.limit || 8, 1, 20),
	};
	return requestJson<Record<string, unknown> | null>({
		path: API.contentIdeas,
		method: "POST",
		body,
	});
}

async function analyzeExposure(
	payload: BackgroundPayload,
): Promise<Record<string, unknown> | null> {
	const body = {
		username: String(payload.username || "").trim(),
		text: assertNonEmpty(payload.text, "text"),
		topic: String(payload.topic || "").trim(),
		domain: String(payload.domain || "").trim(),
	};
	return requestJson<Record<string, unknown> | null>({
		path: API.exposureAnalyze,
		method: "POST",
		body,
		deniedUsername: body.username,
	});
}

async function getComposerState(
	payload: BackgroundPayload,
): Promise<ComposerStateResult> {
	const target = await resolveTargetTab(payload.targetWindowId);
	if (!target.tab) {
		return {
			available: false,
			supportedPage: false,
			message: "Open x.com in a normal browser window before inserting drafts.",
			tabTitle: "",
			tabUrl: "",
		};
	}

	if (!isXTab(target.tab)) {
		return {
			available: false,
			supportedPage: false,
			message: "The active tab is not x.com or twitter.com.",
			tabTitle: target.tab.title || "",
			tabUrl: target.tab.url || "",
		};
	}

	try {
		const response = await chrome.tabs.sendMessage<ComposerBridgeState>(
			target.tab.id as number,
			{
				type: "get_composer_state",
			},
		);
		return {
			available: Boolean(response?.available),
			supportedPage: true,
			message: response?.message || "Open the X composer to insert drafts.",
			tabTitle: target.tab.title || "",
			tabUrl: target.tab.url || "",
		};
	} catch (_error) {
		return {
			available: false,
			supportedPage: true,
			message: "Reload the X tab so the extension can attach to the page.",
			tabTitle: target.tab.title || "",
			tabUrl: target.tab.url || "",
		};
	}
}

async function insertTextIntoComposer(payload: BackgroundPayload): Promise<{
	inserted: boolean;
	tabTitle: string;
	tabUrl: string;
}> {
	const target = await resolveTargetTab(payload.targetWindowId);
	const tab = target.tab;
	if (!tab) {
		throw new Error(
			"Open x.com in a normal browser window before inserting drafts.",
		);
	}
	if (!isXTab(tab)) {
		throw new Error("The active tab is not x.com or twitter.com.");
	}

	const response = await chrome.tabs.sendMessage<InsertComposerBridgeResponse>(
		tab.id as number,
		{
			type: "insert_text",
			payload: {
				text: assertNonEmpty(payload.text, "text"),
			},
		},
	);

	if (!response?.ok) {
		throw new Error(
			response?.error?.message ||
				"Open the X composer before inserting a draft.",
		);
	}

	return {
		inserted: true,
		tabTitle: tab.title || "",
		tabUrl: tab.url || "",
	};
}

async function requestJson<TResponse = unknown>({
	path,
	method,
	body,
	deniedUsername,
}: RequestJsonOptions): Promise<TResponse> {
	const baseUrl = await getBackendBaseUrl();
	let response: Response;
	try {
		response = await fetch(`${baseUrl}${path}`, {
			method,
			headers: {
				"Content-Type": "application/json",
			},
			body: body ? JSON.stringify(body) : undefined,
		});
	} catch (_error) {
		throw new Error(
			`Local backend is unreachable at ${baseUrl}. Start the API server first.`,
		);
	}

	const rawText = await response.text();
	let payload: unknown = null;
	if (rawText) {
		try {
			payload = JSON.parse(rawText);
		} catch (_error) {
			payload = rawText;
		}
	}

	if (!response.ok) {
		if (response.status === 403 && path.startsWith("/api/v1/")) {
			const error = new Error(
				formatForbiddenMessage(deniedUsername),
			) as RuntimeErrorWithStatus;
			error.status = response.status;
			error.payload = payload;
			throw error;
		}
		const detail =
			payload && typeof payload === "object" && !Array.isArray(payload)
				? (payload as { detail?: unknown }).detail || JSON.stringify(payload)
				: String(payload || response.statusText || "Request failed");
		const error = new Error(String(detail)) as RuntimeErrorWithStatus;
		error.status = response.status;
		error.payload = payload;
		throw error;
	}

	return payload as TResponse;
}

function formatForbiddenMessage(username: unknown): string {
	const normalizedUsername = String(username || "").trim();
	if (normalizedUsername) {
		const handle = normalizedUsername.startsWith("@")
			? normalizedUsername
			: `@${normalizedUsername}`;
		return `User ${handle} is not allowed. Please contact the administrator.`;
	}
	return "This user is not allowed. Please contact the administrator.";
}

function clampInt(value: unknown, min: number, max: number): number {
	const parsed = Number.parseInt(String(value), 10);
	if (!Number.isFinite(parsed)) {
		return min;
	}
	return Math.min(max, Math.max(min, parsed));
}

function assertNonEmpty(value: unknown, name: string): string {
	const normalized = String(value || "").trim();
	if (!normalized) {
		throw new Error(`${name} is required`);
	}
	return normalized;
}

function normalizeError(error: unknown): {
	message: string;
	status?: number;
	payload?: unknown;
} {
	if (!error) {
		return { message: "Unknown error" };
	}
	if (typeof error === "string") {
		return { message: error };
	}
	const runtimeError = error as RuntimeErrorWithStatus;
	return {
		message: String(runtimeError.message || error),
		status: Number.isFinite(runtimeError.status)
			? runtimeError.status
			: undefined,
		payload: runtimeError.payload,
	};
}

function storageGet(keys: string[]): Promise<Record<string, unknown>> {
	return new Promise((resolve) => chrome.storage.sync.get(keys, resolve));
}

function storageSet(
	values: Record<string, unknown> | StakedMediaExtensionConfig,
): Promise<void> {
	return new Promise((resolve) =>
		chrome.storage.sync.set(values as Record<string, unknown>, resolve),
	);
}

async function initializeHostBehavior(): Promise<void> {
	const config = await getConfig();
	await applyHostMode(config.hostMode);
}

async function applyHostMode(hostMode: unknown): Promise<void> {
	const normalizedHostMode = normalizeHostMode(hostMode);
	await chrome.action
		.setPopup({
			popup: normalizedHostMode === "popup" ? "panel.html?host=popup" : "",
		})
		.catch((): void => undefined);
	return chrome.sidePanel
		.setPanelBehavior({
			openPanelOnActionClick: normalizedHostMode === "sidepanel",
		})
		.catch((): void => undefined);
}

async function resolveTargetTab(
	targetWindowId: unknown,
): Promise<TargetTabResult> {
	const windowId = await resolveNormalWindowId(targetWindowId);
	if (!windowId) {
		return { tab: null, windowId: null };
	}
	const [tab] = await chrome.tabs.query({
		active: true,
		windowId,
	});
	return {
		tab: tab || null,
		windowId,
	};
}

async function resolveNormalWindowId(
	candidate: unknown,
): Promise<number | null> {
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
	const fallbackWindow = windows.find(
		(windowInfo) =>
			windowInfo.type === "normal" && Number.isFinite(windowInfo.id),
	);
	return fallbackWindow?.id || null;
}

async function getNormalWindow(
	windowId: number,
): Promise<ChromeWindowLike | null> {
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

function isXTab(tab: ChromeTabLike | null | undefined): boolean {
	const url = String(tab?.url || "");
	return /^https:\/\/(?:x|twitter)\.com\//.test(url);
}
