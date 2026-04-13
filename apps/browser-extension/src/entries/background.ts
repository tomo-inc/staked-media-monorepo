importScripts("shared.js");

type BackgroundGlobalRoot = typeof globalThis & {
	StakedMediaExtensionShared: StakedMediaExtensionSharedApi;
};

interface RuntimeErrorWithStatus extends Error {
	status?: number;
	payload?: unknown;
	path?: string;
	code?: string;
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
	baseUrlOverride?: string;
}

interface LocalTrendingCapability {
	supported: boolean;
	message: string;
	checkedAt: string;
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
	DEFAULT_PUBLIC_ERROR_MESSAGE,
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
	hotEvents: "/api/v1/content/hot-events",
	contentIdeas: "/api/v1/content/ideas",
	trendingGenerate: "/api/v1/trending/generate",
	exposureAnalyze: "/api/v1/exposure/analyze",
};
const LOCAL_CAPABILITY_CACHE_TTL_MS = 60 * 1000;
let cachedLocalTrendingCapability:
	| (LocalTrendingCapability & { checkedAtMs: number; baseUrl: string })
	| null = null;

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
			get_hot_events: async (payload) => ({
				result: await getHotEvents(payload || {}),
			}),
			check_local_trending_capability: async (payload) => ({
				result: await checkLocalTrendingCapability(Boolean(payload?.refresh)),
			}),
			trending_generate: async (payload) => ({
				result: await generateTrending(payload || {}),
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
	const currentConfig = await getConfig();
	const nextConfig = sanitizeConfig(
		{
			...currentConfig,
			...patch,
		},
		{ strictBackendBaseUrl: true },
	);
	if (nextConfig.backendBaseUrl !== currentConfig.backendBaseUrl) {
		cachedLocalTrendingCapability = null;
	}
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
		await saveConfig({ defaultUsername: normalizedUsername });
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

async function getHotEvents(
	payload: BackgroundPayload,
): Promise<Record<string, unknown> | null> {
	const hours = clampInt(payload.hours || 24, 1, 72);
	const limit = clampInt(payload.limit || 50, 1, 200);
	const refresh = Boolean(payload.refresh);
	const lang = String(payload.lang || "en").trim() || "en";
	const query = `hours=${hours}&limit=${limit}&refresh=${refresh ? "true" : "false"}&lang=${encodeURIComponent(lang)}`;
	const baseUrl = await getBackendBaseUrl();
	return requestJson<Record<string, unknown> | null>({
		path: `${API.hotEvents}?${query}`,
		method: "GET",
		baseUrlOverride: baseUrl,
	});
}

async function generateTrending(payload: BackgroundPayload): Promise<unknown> {
	const username = assertNonEmpty(payload.username, "username");
	const body: Record<string, unknown> = {
		username,
		comment: String(payload.comment || "").trim(),
		draft_count: clampInt(payload.draft_count || 3, 1, 10),
	};
	const eventId = String(payload.event_id || "").trim();
	if (eventId) {
		body.event_id = eventId;
	}
	if (payload.event_payload && typeof payload.event_payload === "object") {
		body.event_payload = payload.event_payload;
	}
	const baseUrl = await getBackendBaseUrl();
	let result: unknown;
	try {
		result = await requestJson<unknown>({
			path: API.trendingGenerate,
			method: "POST",
			body,
			deniedUsername: username,
			baseUrlOverride: baseUrl,
		});
	} catch (error) {
		const runtimeError = error as RuntimeErrorWithStatus;
		const detailText = extractErrorDetailText(runtimeError?.payload);
		if (
			runtimeError?.status === 409 &&
			detailText.includes("persona not found")
		) {
			const capability = await checkLocalTrendingCapability(false);
			if (!capability.supported) {
				throw createRuntimeError(DEFAULT_PUBLIC_ERROR_MESSAGE, {
					path: "/openapi.json",
				});
			}
			await requestJson<unknown>({
				path: API.ingest,
				method: "POST",
				body: { username },
				deniedUsername: username,
				baseUrlOverride: baseUrl,
			});
			result = await requestJson<unknown>({
				path: API.trendingGenerate,
				method: "POST",
				body,
				deniedUsername: username,
				baseUrlOverride: baseUrl,
			});
		} else {
			throw error;
		}
	}
	await saveConfig({ defaultUsername: username });
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
		throw new Error(DEFAULT_PUBLIC_ERROR_MESSAGE);
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
	baseUrlOverride,
}: RequestJsonOptions): Promise<TResponse> {
	const baseUrl = baseUrlOverride
		? normalizeBaseUrl(baseUrlOverride)
		: await getBackendBaseUrl();
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
		throw createRuntimeError(DEFAULT_PUBLIC_ERROR_MESSAGE, { path });
	}

	const rawText = await response.text();
	let payload: unknown = null;
	if (rawText) {
		try {
			payload = JSON.parse(rawText);
		} catch (_error) {
			payload = null;
		}
	}

	if (!response.ok) {
		if (response.status === 403 && path.startsWith("/api/v1/")) {
			const error = new Error(
				formatForbiddenMessage(deniedUsername),
			) as RuntimeErrorWithStatus;
			error.status = response.status;
			error.payload = payload;
			error.path = path;
			throw error;
		}
		throw createRuntimeError(DEFAULT_PUBLIC_ERROR_MESSAGE, {
			status: response.status,
			payload:
				payload && typeof payload === "object" && !Array.isArray(payload)
					? payload
					: undefined,
			path,
		});
	}

	return payload as TResponse;
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

async function checkLocalTrendingCapability(
	forceRefresh: boolean,
): Promise<LocalTrendingCapability> {
	const now = Date.now();
	const baseUrl = await getBackendBaseUrl();
	if (
		!forceRefresh &&
		cachedLocalTrendingCapability &&
		cachedLocalTrendingCapability.baseUrl === baseUrl &&
		now - cachedLocalTrendingCapability.checkedAtMs <
			LOCAL_CAPABILITY_CACHE_TTL_MS
	) {
		return {
			supported: cachedLocalTrendingCapability.supported,
			message: cachedLocalTrendingCapability.message,
			checkedAt: cachedLocalTrendingCapability.checkedAt,
		};
	}

	try {
		const openApi = await requestJson<Record<string, unknown>>({
			path: "/openapi.json",
			method: "GET",
			baseUrlOverride: baseUrl,
		});
		const supported = hasOpenApiOperation(
			openApi,
			API.trendingGenerate,
			"post",
		);
		const capability: LocalTrendingCapability = {
			supported,
			message: supported
				? "Trending capability check passed."
				: "Configured backend is outdated: /api/v1/trending/generate (POST) is missing.",
			checkedAt: new Date().toISOString(),
		};
		cachedLocalTrendingCapability = {
			...capability,
			baseUrl,
			checkedAtMs: now,
		};
		return capability;
	} catch (error) {
		const runtimeError = error as RuntimeErrorWithStatus;
		const capability: LocalTrendingCapability = {
			supported: false,
			message:
				runtimeError?.message ||
				"Failed to verify backend capability from /openapi.json.",
			checkedAt: new Date().toISOString(),
		};
		cachedLocalTrendingCapability = {
			...capability,
			baseUrl,
			checkedAtMs: now,
		};
		return capability;
	}
}

function hasOpenApiOperation(
	openApi: Record<string, unknown>,
	pathName: string,
	methodName: "get" | "post",
): boolean {
	if (!openApi || typeof openApi !== "object") {
		return false;
	}
	const paths = (openApi as { paths?: unknown }).paths;
	if (!paths || typeof paths !== "object") {
		return false;
	}
	const routePath = (paths as Record<string, unknown>)[pathName];
	if (!routePath || typeof routePath !== "object") {
		return false;
	}
	return Boolean((routePath as Record<string, unknown>)[methodName]);
}

function formatForbiddenMessage(_username: unknown): string {
	return DEFAULT_PUBLIC_ERROR_MESSAGE;
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
	path?: string;
	code?: string;
} {
	if (!error) {
		return { message: "Unknown error" };
	}
	if (typeof error === "string") {
		return { message: error };
	}
	const runtimeError = error as RuntimeErrorWithStatus;
	const message = String(runtimeError.message || error);
	return {
		message,
		status: Number.isFinite(runtimeError.status)
			? runtimeError.status
			: undefined,
		payload:
			message === DEFAULT_PUBLIC_ERROR_MESSAGE
				? undefined
				: runtimeError.payload,
		path: runtimeError.path ? String(runtimeError.path) : undefined,
		code: runtimeError.code ? String(runtimeError.code) : undefined,
	};
}

function createRuntimeError(
	message: string,
	options: {
		status?: number;
		payload?: unknown;
		path?: string;
		code?: string;
	} = {},
): RuntimeErrorWithStatus {
	const error = new Error(message) as RuntimeErrorWithStatus;
	if (options.status != null) {
		error.status = options.status;
	}
	if (options.payload !== undefined) {
		error.payload = options.payload;
	}
	if (options.path) {
		error.path = options.path;
	}
	if (options.code) {
		error.code = options.code;
	}
	return error;
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
