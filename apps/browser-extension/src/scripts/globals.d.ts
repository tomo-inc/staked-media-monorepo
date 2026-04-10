interface CommonJsModuleLike {
	exports?: unknown;
}

type StakedMediaThemeMode = "light" | "dark" | "system";
type StakedMediaApiMode = "content" | "drafts";
type StakedMediaHostMode = "sidepanel" | "popup";
type StakedMediaLocale = "en" | "zh-CN" | "zh-TW" | "ja" | "ko" | "es";
type StakedMediaLanguageMode = "auto" | StakedMediaLocale;

interface StakedMediaExtensionConfig {
	defaultUsername: string;
	backendBaseUrl: string;
	apiMode: StakedMediaApiMode;
	theme: StakedMediaThemeMode;
	hostMode: StakedMediaHostMode;
	language: StakedMediaLanguageMode;
}

interface StakedMediaNormalizeOptions {
	strictBackendBaseUrl?: boolean;
}

type StakedMediaDraftRecord = { text?: string } & Record<string, unknown>;

interface StakedMediaDraftVariant {
	drafts?: StakedMediaDraftRecord[] | null;
}

interface StakedMediaDraftSource {
	drafts?: StakedMediaDraftRecord[] | null;
	variants?: StakedMediaDraftVariant[] | null;
	formatted_drafts?: string[] | null;
}

interface StakedMediaConnectionIndicatorInput {
	health?: { status?: string } | null;
	latencyMs?: number | null;
	healthState?: string;
}

interface StakedMediaConnectionIndicatorOutput {
	className: string;
	title: string;
	latencyText: string;
}

interface StakedMediaHotEventsStateNoticeInput {
	refreshing?: boolean;
	isStale?: boolean;
	throttled?: boolean;
	nextRefreshAvailableInSeconds?: number | null;
	lastRefreshedAt?: string;
	lastAttemptedAt?: string;
	lastRefreshError?: string;
	formatTimestamp?: (value: string) => string;
}

interface StakedMediaPanelHelpersApi {
	isWhitelistDeniedError(
		error: { status?: number } | null | undefined,
	): boolean;
	deriveConnectionIndicator(
		input: StakedMediaConnectionIndicatorInput,
	): StakedMediaConnectionIndicatorOutput;
	deriveHotEventsStateNotice(
		input: StakedMediaHotEventsStateNoticeInput,
	): string[];
	buildPanelShell(): string;
}

interface StakedMediaExtensionSharedApi {
	DEFAULT_CONFIG: Readonly<StakedMediaExtensionConfig>;
	ALLOWED_BACKEND_HOSTS: ReadonlySet<string>;
	DEFAULT_PUBLIC_ERROR_MESSAGE: string;
	FALLBACK_BACKEND_BASE_URL: string;
	coerceWindowId(value: unknown): number | null;
	escapeHtml(value: unknown): string;
	extractDrafts(
		result: StakedMediaDraftSource | null | undefined,
	): StakedMediaDraftRecord[];
	normalizeBaseUrl(value: unknown): string;
	normalizeHostMode(value: unknown): StakedMediaHostMode;
	resolveLocale(
		languageSetting: unknown,
		browserLanguage: unknown,
	): StakedMediaLocale;
	routeMessage<TPayload = unknown, TResult = unknown>(
		message: { type?: string; payload?: TPayload } | null | undefined,
		handlers: Record<
			string,
			(payload: TPayload, rawMessage: unknown) => Promise<TResult> | TResult
		>,
	): Promise<TResult>;
	sanitizeConfig(
		config: Partial<StakedMediaExtensionConfig> | null | undefined,
		options?: StakedMediaNormalizeOptions,
	): StakedMediaExtensionConfig;
	sanitizeUserVisibleErrorMessage(
		message: unknown,
		fallbackMessage?: string,
	): string;
	sendRuntimeMessage<TResponse = unknown>(message: unknown): Promise<TResponse>;
	t(key: string, locale: StakedMediaLocale): string;
	listLanguageOptions(
		locale: StakedMediaLocale,
	): Array<{ value: StakedMediaLanguageMode; label: string }>;
}

interface ChromeRuntimeLastError {
	message?: string;
}

interface ChromeEventLike<TArgs extends unknown[]> {
	addListener(listener: (...args: TArgs) => void | Promise<void>): void;
}

interface ChromeTabLike {
	id?: number;
	title?: string;
	url?: string;
	windowId?: number;
	active?: boolean;
}

interface ChromeWindowLike {
	id?: number;
	type?: string;
}

interface ChromeRuntimeMessageSender {
	tab?: ChromeTabLike;
}

interface ChromeRuntimeOnMessageLike {
	addListener(
		listener: (
			message: unknown,
			sender: ChromeRuntimeMessageSender,
			sendResponse: (response?: unknown) => void,
		) => boolean | undefined,
	): void;
}

interface ChromeRuntimeLike {
	lastError?: ChromeRuntimeLastError | null;
	getManifest(): {
		version?: string;
		name?: string;
	};
	sendMessage<TResponse = unknown>(
		message: unknown,
		callback?: (response: TResponse) => void,
	): void;
	onInstalled: ChromeEventLike<[]>;
	onStartup: ChromeEventLike<[]>;
	onMessage: ChromeRuntimeOnMessageLike;
}

interface ChromeStorageAreaLike {
	get(
		keys: string[] | string | null,
		callback: (items: Record<string, unknown>) => void,
	): void;
	set(items: Record<string, unknown>, callback?: () => void): void;
}

interface ChromeStorageLike {
	sync: ChromeStorageAreaLike;
}

interface ChromeActionLike {
	setPopup(details: { popup: string }): Promise<void>;
}

interface ChromeSidePanelLike {
	setPanelBehavior(details: { openPanelOnActionClick: boolean }): Promise<void>;
	open?(details: { windowId: number }): Promise<void>;
	close?(details: { windowId: number }): Promise<void>;
}

interface ChromeTabsLike {
	query(queryInfo: {
		active?: boolean;
		windowId?: number;
		lastFocusedWindow?: boolean;
	}): Promise<ChromeTabLike[]>;
	sendMessage<TResponse = unknown>(
		tabId: number,
		message: unknown,
	): Promise<TResponse>;
}

interface ChromeWindowsLike {
	getCurrent(): Promise<ChromeWindowLike>;
	getLastFocused(): Promise<ChromeWindowLike>;
	getAll(): Promise<ChromeWindowLike[]>;
	get(windowId: number): Promise<ChromeWindowLike>;
}

interface ChromeLike {
	runtime: ChromeRuntimeLike;
	storage: ChromeStorageLike;
	action: ChromeActionLike;
	sidePanel: ChromeSidePanelLike;
	tabs: ChromeTabsLike;
	windows: ChromeWindowsLike;
}

interface Window {
	StakedMediaExtensionShared: StakedMediaExtensionSharedApi;
	StakedMediaPanelHelpers: StakedMediaPanelHelpersApi;
	__stakedMediaCopilotBridgeLoaded?: boolean;
}

declare const module: CommonJsModuleLike | undefined;

declare const chrome: ChromeLike;

declare function importScripts(...paths: string[]): void;
