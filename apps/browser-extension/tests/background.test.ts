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

function createTextResponse(
	status: number,
	body: string,
): {
	ok: boolean;
	status: number;
	text(): Promise<string>;
} {
	return {
		ok: status >= 200 && status < 300,
		status,
		async text() {
			return body;
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

test("background save_config accepts localhost backend hosts", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		config: StakedMediaExtensionConfig;
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "http://127.0.0.1:8000" },
	});

	assert.equal(response.ok, true);
	assert.equal(response.config.backendBaseUrl, "http://127.0.0.1:8000");
	assert.equal(harness.storage.backendBaseUrl, "http://127.0.0.1:8000");
});

test("background save_config accepts localhost alias", async () => {
	const harness = createBackgroundHarness();
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		config: StakedMediaExtensionConfig;
	}>(harness.listeners.onMessage, {
		type: "save_config",
		payload: { backendBaseUrl: "http://localhost:9000" },
	});

	assert.equal(response.ok, true);
	assert.equal(response.config.backendBaseUrl, "http://localhost:9000");
	assert.equal(harness.storage.backendBaseUrl, "http://localhost:9000");
});

test("background get_config keeps persisted localhost backend url", async () => {
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "http://127.0.0.1:8000" },
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		config: StakedMediaExtensionConfig;
	}>(harness.listeners.onMessage, {
		type: "get_config",
	});

	assert.equal(response.ok, true);
	assert.equal(response.config.backendBaseUrl, "http://127.0.0.1:8000");
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

test("background check_profile redacts api 403 into the shared public error message", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background generate redacts html error pages into the shared public error message", async () => {
	const harness = createBackgroundHarness({
		fetch: async () =>
			createTextResponse(
				524,
				"<!DOCTYPE html><html><head><title>sayviner.top | 524: A timeout occurred</title></head><body>A timeout occurred</body></html>",
			),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { status: number; message: string; payload?: unknown };
	}>(harness.listeners.onMessage, {
		type: "generate",
		payload: { username: "alice", idea: "btc", draft_count: 2 },
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 524);
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
	assert.equal(response.error.payload, undefined);
});

test("background check_profile persists the loaded username", async () => {
	const harness = createBackgroundHarness({
		fetch: async () =>
			createJsonResponse(200, {
				profile: { username: "alice", followers_count: 12 },
				stored_tweet_count: 34,
				latest_persona_snapshot: { persona: { author_summary: "summary" } },
			}),
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		profile: {
			exists: boolean;
			username: string;
			storedTweetCount: number;
			personaReady: boolean;
		};
	}>(harness.listeners.onMessage, {
		type: "check_profile",
		payload: { username: "alice" },
	});

	assert.equal(response.ok, true);
	assert.equal(response.profile.exists, true);
	assert.equal(response.profile.username, "alice");
	assert.equal(harness.storage.defaultUsername, "alice");
});

test("background ingest_profile redacts api 403 into the shared public error message", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background generate_content redacts api 403 into the shared public error message", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background analyze_exposure redacts api 403 into the shared public error message", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background suggest_ideas redacts api 403 into the shared public error message", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background whitelist redaction does not depend on username formatting", async () => {
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
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
});

test("background get_hot_events calls hot-events endpoint with refresh query", async () => {
	const seenUrls: string[] = [];
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "https://api.sayviner.top:8443" },
		fetch: async (url) => {
			seenUrls.push(String(url));
			return createJsonResponse(200, {
				hours: 24,
				count: 1,
				items: [{ id: "event-1", title: "Hot event" }],
				warnings: ["opentwitter unavailable: timeout"],
				source_status: {
					opennews: { status: "ok", count: 1, error: "" },
					opentwitter: { status: "error", count: 0, error: "timeout" },
				},
			});
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		result: {
			hours: number;
			count: number;
			items: Array<{ id: string; title: string }>;
			warnings: string[];
			source_status: Record<
				string,
				{ status: string; count: number; error: string }
			>;
		};
	}>(harness.listeners.onMessage, {
		type: "get_hot_events",
		payload: { hours: 24, limit: 50, refresh: true },
	});

	assert.equal(response.ok, true);
	assert.equal(response.result.count, 1);
	assert.equal(response.result.items[0]?.id, "event-1");
	assert.equal(response.result.warnings[0], "opentwitter unavailable: timeout");
	assert.equal(response.result.source_status.opentwitter?.status, "error");
	assert.match(seenUrls[0], /^https:\/\/api\.sayviner\.top:8443\//);
	assert.match(
		seenUrls[0],
		/\/api\/v1\/content\/hot-events\?hours=24&limit=50&refresh=true&lang=en$/,
	);
});

test("background check_local_trending_capability reports missing trending route on configured backend", async () => {
	const seenUrls: string[] = [];
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "https://api.sayviner.top:8443" },
		fetch: async (url) => {
			const normalizedUrl = String(url);
			seenUrls.push(normalizedUrl);
			if (normalizedUrl.endsWith("/openapi.json")) {
				return createJsonResponse(200, {
					paths: {
						"/api/v1/content/hot-events": {
							get: {},
						},
					},
				});
			}
			return createJsonResponse(500, { detail: "unexpected endpoint" });
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		result: { supported: boolean; message: string };
	}>(harness.listeners.onMessage, {
		type: "check_local_trending_capability",
	});

	assert.equal(response.ok, true);
	assert.equal(response.result.supported, false);
	assert.match(response.result.message, /outdated/i);
	assert.match(
		seenUrls[0],
		/^https:\/\/api\.sayviner\.top:8443\/openapi\.json$/,
	);
});

test("background trending_generate posts event payload to configured trending endpoint", async () => {
	const seenUrls: string[] = [];
	const seenBodies: Array<Record<string, unknown>> = [];
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "http://127.0.0.1:8000" },
		fetch: async (url, init) => {
			seenUrls.push(String(url));
			const requestInit = (init || {}) as { body?: string };
			seenBodies.push(JSON.parse(String(requestInit.body || "{}")));
			return createJsonResponse(200, {
				mode: "B",
				drafts: [{ text: "Trending draft" }],
			});
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		result: { mode: string; drafts: Array<{ text: string }> };
	}>(harness.listeners.onMessage, {
		type: "trending_generate",
		payload: {
			username: "lin",
			event_id: "web3:event-1",
			event_payload: { id: "web3:event-1", title: "Hot event" },
			comment: "Need a contrarian take.",
			draft_count: 2,
		},
	});

	assert.equal(response.ok, true);
	assert.equal(response.result.mode, "B");
	assert.equal(response.result.drafts[0]?.text, "Trending draft");
	assert.match(seenUrls[0], /^http:\/\/127\.0\.0\.1:8000\//);
	assert.match(seenUrls[0], /\/api\/v1\/trending\/generate$/);
	assert.equal(seenBodies[0]?.username, "lin");
	assert.equal(seenBodies[0]?.event_id, "web3:event-1");
	assert.equal(seenBodies[0]?.draft_count, 2);
	assert.equal(
		(seenBodies[0]?.event_payload as { title?: string })?.title,
		"Hot event",
	);
	assert.equal(harness.storage.defaultUsername, "lin");
});

test("background trending_generate ingests profile on configured backend and retries once", async () => {
	const seenUrls: string[] = [];
	const seenBodies: Array<Record<string, unknown>> = [];
	let trendingAttempts = 0;
	let ingestAttempts = 0;
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "http://127.0.0.1:8000" },
		fetch: async (url, init) => {
			const normalizedUrl = String(url);
			seenUrls.push(normalizedUrl);
			const requestInit = (init || {}) as { body?: string };
			seenBodies.push(JSON.parse(String(requestInit.body || "{}")));
			if (normalizedUrl.endsWith("/openapi.json")) {
				return createJsonResponse(200, {
					paths: {
						"/api/v1/trending/generate": {
							post: {},
						},
					},
				});
			}
			if (normalizedUrl.endsWith("/api/v1/trending/generate")) {
				trendingAttempts += 1;
				if (trendingAttempts === 1) {
					return createJsonResponse(409, {
						detail: "Persona not found. Run /api/v1/profiles/ingest first",
					});
				}
				return createJsonResponse(200, {
					mode: "B",
					drafts: [{ text: "Trending draft after rebuild" }],
				});
			}
			if (normalizedUrl.endsWith("/api/v1/profiles/ingest")) {
				ingestAttempts += 1;
				return createJsonResponse(200, {
					username: "lin",
					persona_snapshot_id: 101,
				});
			}
			return createJsonResponse(500, { detail: "unexpected endpoint" });
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: boolean;
		result: { mode: string; drafts: Array<{ text: string }> };
	}>(harness.listeners.onMessage, {
		type: "trending_generate",
		payload: {
			username: "lin",
			event_id: "web3:event-2",
			event_payload: { id: "web3:event-2", title: "Hot event 2" },
			comment: "Need a practical angle.",
			draft_count: 2,
		},
	});

	assert.equal(response.ok, true);
	assert.equal(response.result.mode, "B");
	assert.equal(response.result.drafts[0]?.text, "Trending draft after rebuild");
	assert.equal(trendingAttempts, 2);
	assert.equal(ingestAttempts, 1);
	assert.match(
		seenUrls[0],
		/^http:\/\/127\.0\.0\.1:8000\/api\/v1\/trending\/generate$/,
	);
	assert.match(seenUrls[1], /^http:\/\/127\.0\.0\.1:8000\/openapi\.json$/);
	assert.match(
		seenUrls[2],
		/^http:\/\/127\.0\.0\.1:8000\/api\/v1\/profiles\/ingest$/,
	);
	assert.match(
		seenUrls[3],
		/^http:\/\/127\.0\.0\.1:8000\/api\/v1\/trending\/generate$/,
	);
	assert.equal(seenBodies[2]?.username, "lin");
	assert.equal(harness.storage.defaultUsername, "lin");
});

test("background trending_generate redacts ingest recovery failures into the shared public error message", async () => {
	let trendingAttempts = 0;
	let ingestAttempts = 0;
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "http://127.0.0.1:8000" },
		fetch: async (url) => {
			const normalizedUrl = String(url);
			if (normalizedUrl.endsWith("/openapi.json")) {
				return createJsonResponse(200, {
					paths: {
						"/api/v1/trending/generate": {
							post: {},
						},
					},
				});
			}
			if (normalizedUrl.endsWith("/api/v1/trending/generate")) {
				trendingAttempts += 1;
				return createJsonResponse(409, {
					detail: "Persona not found. Run /api/v1/profiles/ingest first",
				});
			}
			if (normalizedUrl.endsWith("/api/v1/profiles/ingest")) {
				ingestAttempts += 1;
				return createJsonResponse(502, {
					detail: "Upstream unavailable",
				});
			}
			return createJsonResponse(500, { detail: "unexpected endpoint" });
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: {
			status: number;
			path: string;
			message: string;
			payload?: unknown;
		};
	}>(harness.listeners.onMessage, {
		type: "trending_generate",
		payload: {
			username: "lin",
			event_id: "web3:event-2",
			event_payload: { id: "web3:event-2", title: "Hot event 2" },
			comment: "Need a practical angle.",
			draft_count: 2,
		},
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.status, 502);
	assert.equal(response.error.path, "/api/v1/profiles/ingest");
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
	assert.equal(response.error.payload, undefined);
	assert.equal(trendingAttempts, 1);
	assert.equal(ingestAttempts, 1);
});

test("background trending_generate redacts outdated backend errors into the shared public error message", async () => {
	let trendingAttempts = 0;
	const harness = createBackgroundHarness({
		storage: { backendBaseUrl: "http://127.0.0.1:8000" },
		fetch: async (url) => {
			const normalizedUrl = String(url);
			if (normalizedUrl.endsWith("/api/v1/trending/generate")) {
				trendingAttempts += 1;
				return createJsonResponse(409, {
					detail: "Persona not found. Run /api/v1/profiles/ingest first",
				});
			}
			if (normalizedUrl.endsWith("/openapi.json")) {
				return createJsonResponse(200, {
					paths: {
						"/api/v1/content/hot-events": {
							get: {},
						},
					},
				});
			}
			return createJsonResponse(500, { detail: "unexpected endpoint" });
		},
	});
	await flushTasks();

	const response = await dispatchRuntimeMessage<{
		ok: false;
		error: { path: string; code: string; message: string };
	}>(harness.listeners.onMessage, {
		type: "trending_generate",
		payload: {
			username: "lin",
			event_id: "web3:event-9",
			event_payload: { id: "web3:event-9", title: "Hot event 9" },
			comment: "Need a practical angle.",
			draft_count: 2,
		},
	});

	assert.equal(response.ok, false);
	assert.equal(response.error.path, "/openapi.json");
	assert.equal(response.error.message, shared.DEFAULT_PUBLIC_ERROR_MESSAGE);
	assert.equal(trendingAttempts, 1);
});
