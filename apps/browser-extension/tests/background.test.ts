import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";

const require = createRequire(import.meta.url);

const shared = require("../dist/shared.js") as StakedMediaExtensionSharedApi;
const objectHasOwn = (
	Object as typeof Object & {
		hasOwn(target: object, property: PropertyKey): boolean;
	}
).hasOwn;

interface BackgroundHarnessOptions {
	storage?: Record<string, unknown>;
	fetch?: (
		url: unknown,
		init?: unknown,
	) => Promise<{
		ok: boolean;
		status: number;
		text(): Promise<string>;
	}>;
}

interface BackgroundCalls {
	setPopup: Array<{ popup: string }>;
	setPanelBehavior: Array<{ openPanelOnActionClick: boolean }>;
}

interface BackgroundListeners {
	onInstalled: (() => void | Promise<void>) | null;
	onStartup: (() => void | Promise<void>) | null;
	onMessage:
		| ((
				message: unknown,
				sender: unknown,
				sendResponse: (response?: unknown) => void,
		  ) => boolean | undefined)
		| null;
}

interface BackgroundHarness {
	context: vm.Context & {
		StakedMediaExtensionShared?: StakedMediaExtensionSharedApi;
	};
	storage: Record<string, unknown>;
	calls: BackgroundCalls;
	listeners: BackgroundListeners;
}

function createBackgroundHarness(
	options: BackgroundHarnessOptions = {},
): BackgroundHarness {
	const storage: Record<string, unknown> = { ...(options.storage || {}) };
	const calls: BackgroundCalls = {
		setPopup: [],
		setPanelBehavior: [],
	};
	const listeners: BackgroundListeners = {
		onInstalled: null,
		onStartup: null,
		onMessage: null,
	};

	const context = {
		console,
		URL,
		JSON,
		Math,
		Number,
		String,
		Object,
		Array,
		Promise,
		Error,
		encodeURIComponent,
		performance: {
			now: (() => {
				let tick = 0;
				return () => {
					tick += 25;
					return tick;
				};
			})(),
		},
		fetch:
			options.fetch ||
			(async () => {
				throw new Error("fetch not stubbed");
			}),
		importScripts() {
			context.StakedMediaExtensionShared = shared;
		},
	} as unknown as vm.Context & {
		StakedMediaExtensionShared?: StakedMediaExtensionSharedApi;
		chrome: {
			runtime: {
				onInstalled: {
					addListener(listener: () => void | Promise<void>): void;
				};
				onStartup: {
					addListener(listener: () => void | Promise<void>): void;
				};
				onMessage: {
					addListener(
						listener: (
							message: unknown,
							sender: unknown,
							sendResponse: (response?: unknown) => void,
						) => boolean | undefined,
					): void;
				};
				lastError: { message?: string } | null;
			};
			storage: {
				sync: {
					get(
						keys: string[] | string | null,
						callback: (items: Record<string, unknown>) => void,
					): void;
					set(values: Record<string, unknown>, callback?: () => void): void;
				};
			};
			action: {
				setPopup(payload: { popup: string }): Promise<void>;
			};
			sidePanel: {
				setPanelBehavior(payload: {
					openPanelOnActionClick: boolean;
				}): Promise<void>;
			};
			tabs: {
				query(): Promise<unknown[]>;
				sendMessage(): Promise<null>;
			};
			windows: {
				getCurrent(): Promise<{ type: string; id: number }>;
				getLastFocused(): Promise<{ type: string; id: number }>;
				getAll(): Promise<Array<{ type: string; id: number }>>;
				get(windowId: number): Promise<{ type: string; id: number }>;
			};
		};
		globalThis: unknown;
		importScripts(...paths: string[]): void;
		fetch: NonNullable<BackgroundHarnessOptions["fetch"]>;
		performance: {
			now(): number;
		};
	};

	context.globalThis = context;
	context.chrome = {
		runtime: {
			onInstalled: {
				addListener(listener) {
					listeners.onInstalled = listener;
				},
			},
			onStartup: {
				addListener(listener) {
					listeners.onStartup = listener;
				},
			},
			onMessage: {
				addListener(listener) {
					listeners.onMessage = listener;
				},
			},
			lastError: null,
		},
		storage: {
			sync: {
				get(keys, callback) {
					const result: Record<string, unknown> = {};
					if (Array.isArray(keys)) {
						for (const key of keys) {
							if (objectHasOwn(storage, key)) {
								result[key] = storage[key];
							}
						}
					}
					callback(result);
				},
				set(values, callback) {
					Object.assign(storage, values);
					callback?.();
				},
			},
		},
		action: {
			async setPopup(payload) {
				calls.setPopup.push(payload);
			},
		},
		sidePanel: {
			async setPanelBehavior(payload) {
				calls.setPanelBehavior.push(payload);
			},
		},
		tabs: {
			async query() {
				return [];
			},
			async sendMessage() {
				return null;
			},
		},
		windows: {
			async getCurrent() {
				return { type: "normal", id: 91 };
			},
			async getLastFocused() {
				return { type: "normal", id: 91 };
			},
			async getAll() {
				return [{ type: "normal", id: 91 }];
			},
			async get(windowId) {
				return { type: "normal", id: windowId };
			},
		},
	};

	const code = readFileSync(
		new URL("../dist/background.js", import.meta.url),
		"utf8",
	);
	vm.runInNewContext(code, context, {
		filename: "background.js",
	});

	return { context, storage, calls, listeners };
}

function flushTasks() {
	return new Promise((resolve) => setImmediate(resolve));
}

function dispatchRuntimeMessage<TResponse>(
	listener: BackgroundListeners["onMessage"],
	message: unknown,
): Promise<TResponse> {
	assert.ok(listener);
	return new Promise((resolve) => {
		const keepAlive = listener(message, {}, (response) => {
			resolve(response as TResponse);
		});
		assert.equal(keepAlive, true);
	});
}

function createJsonResponse(
	status: number,
	payload: Record<string, unknown>,
): {
	ok: boolean;
	status: number;
	text(): Promise<string>;
} {
	return {
		ok: status >= 200 && status < 300,
		status,
		async text() {
			return JSON.stringify(payload);
		},
	};
}

test("background save_config updates host mode and popup behavior", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		config: StakedMediaExtensionConfig;
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { hostMode: "popup" },
	});

	assert.equal(response.ok, true);
	assert.equal(response.config.hostMode, "popup");
	assert.equal(harness.storage.hostMode, "popup");
	assert.equal(
		harness.calls.setPopup[harness.calls.setPopup.length - 1]?.popup,
		"panel.html?host=popup",
	);
	assert.equal(
		harness.calls.setPanelBehavior[harness.calls.setPanelBehavior.length - 1]
			?.openPanelOnActionClick,
		false,
	);
});

test("background save_config accepts allowed backend hosts", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		config: StakedMediaExtensionConfig;
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "https://api.sayviner.top:8443" },
	});

	assert.equal(response.ok, true);
	assert.equal(response.config.backendBaseUrl, "https://api.sayviner.top:8443");
	assert.equal(harness.storage.backendBaseUrl, "https://api.sayviner.top:8443");
});

test("background save_config rejects unsupported backend protocols", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { message: string };
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "ftp://api.example.com" },
	});

	assert.equal(response.ok, false);
	assert.match(
		response.error.message,
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("background save_config rejects backend credentials", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { message: string };
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "https://user:secret@localhost" },
	});

	assert.equal(response.ok, false);
	assert.match(
		response.error.message,
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("background save_config rejects non-whitelisted backend hosts", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { message: string };
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "https://evil.example.com" },
	});

	assert.equal(response.ok, false);
	assert.match(
		response.error.message,
		/Backend URL must be a valid http\(s\) URL pointing to an allowed host\./,
	);
});

test("background generate defaults to drafts api mode when config is not persisted", async () => {
	const seenUrls: string[] = [];
	const harness = createBackgroundHarness({
		fetch: async (url) => {
			seenUrls.push(String(url));
			return createJsonResponse(200, { drafts: [{ text: "alpha" }] });
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		result: StakedMediaDraftSource;
	}>(harness.listeners.onMessage, {
		type: "generate",
		payload: { username: "alice", idea: "btc", draft_count: 2 },
	});

	assert.equal(response.ok, true);
	assert.equal(response.result.drafts[0].text, "alpha");
	assert.match(seenUrls[0], /\/api\/v1\/drafts\/generate$/);
});

test("background check_profile converts api 403 into username-specific whitelist message", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "check_profile",
		payload: { username: "alice" },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"User @alice is not allowed. Please contact the administrator.",
	);
});

test("background ingest_profile converts api 403 into username-specific whitelist message", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "ingest_profile",
		payload: { username: "bob" },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"User @bob is not allowed. Please contact the administrator.",
	);
});

test("background generate_content converts api 403 into username-specific whitelist message", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "generate_content",
		payload: { username: "carol", idea: "btc", draft_count: 2 },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"User @carol is not allowed. Please contact the administrator.",
	);
});

test("background analyze_exposure converts api 403 into username-specific whitelist message", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "analyze_exposure",
		payload: { username: "dave", text: "hello" },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"User @dave is not allowed. Please contact the administrator.",
	);
});

test("background suggest_ideas falls back to generic whitelist message on api 403", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "suggest_ideas",
		payload: { domain: "crypto" },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"This user is not allowed. Please contact the administrator.",
	);
});

test("background whitelist message does not duplicate the @ prefix", async () => {
	const harness = createBackgroundHarness({
		fetch: async () => createJsonResponse(403, { detail: "forbidden" }),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string };
	}>(harness.listeners.onMessage, {
		type: "check_profile",
		payload: { username: "@erin" },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 403);
	assert.equal(
		response.error.message,
		"User @erin is not allowed. Please contact the administrator.",
	);
});
