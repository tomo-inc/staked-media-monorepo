interface ComposerElementLike {
	textContent: string | null;
	getAttribute?(name: string): string | null;
	focus?(): void;
	dispatchEvent?(event: unknown): boolean;
}

interface RangeLike {
	selectNodeContents(node: unknown): void;
	deleteContents(): void;
	insertNode(node: unknown): void;
	setStartAfter(node: unknown): void;
	collapse(toStart?: boolean): void;
}

interface SelectionLike {
	removeAllRanges(): void;
	addRange(range: RangeLike): void;
}

interface DocumentLike {
	querySelectorAll?(selector: string): ArrayLike<ComposerElementLike>;
	createRange?(): RangeLike | null;
	createTextNode?(text: string): unknown;
}

interface EventConstructorLike {
	new (type: string, init?: Record<string, unknown>): unknown;
}

interface ContentScriptRootLike {
	chrome?: ChromeLike;
	document?: DocumentLike;
	Event?: EventConstructorLike;
	InputEvent?: EventConstructorLike;
	getSelection?(): SelectionLike | null;
	__stakedMediaCopilotBridgeLoaded?: boolean;
}

interface ComposerStateOptions {
	document?: DocumentLike;
}

interface InsertComposerOptions extends ComposerStateOptions {
	window?: ContentScriptRootLike;
	Event?: EventConstructorLike;
	InputEvent?: EventConstructorLike;
}

interface ContentScriptMessage {
	type?: string;
	payload?: {
		text?: unknown;
	} | null;
}

interface ContentScriptApi {
	COMPOSER_TEST_ID_PATTERN: RegExp;
	assertNonEmpty(value: unknown, name: string): string;
	dispatchComposerInput(
		composer: ComposerElementLike,
		text: string,
		options?: {
			InputEvent?: EventConstructorLike;
		},
	): void;
	findComposer(doc?: DocumentLike): ComposerElementLike | null;
	getComposerState(options?: ComposerStateOptions): {
		available: boolean;
		message: string;
	};
	insertIntoComposer(
		text: string,
		options?: InsertComposerOptions,
	): ComposerElementLike;
	installBridge(root: ContentScriptRootLike): void;
	isComposerElement(element: ComposerElementLike | null | undefined): boolean;
}

(function (globalRoot: ContentScriptRootLike, factory: () => ContentScriptApi) {
	const api = factory();
	if (typeof module !== "undefined" && module.exports) {
		module.exports = api;
	}
	if (globalRoot?.chrome?.runtime?.onMessage && globalRoot?.document) {
		api.installBridge(globalRoot);
	}
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	const COMPOSER_TEST_ID_PATTERN = /^tweetTextarea(?:_\d+)?$/;

	function installBridge(root: ContentScriptRootLike): void {
		if (root.__stakedMediaCopilotBridgeLoaded) {
			return;
		}
		root.__stakedMediaCopilotBridgeLoaded = true;

		root.chrome.runtime.onMessage.addListener(
			(message: unknown, _sender, sendResponse) => {
				const runtimeMessage = message as ContentScriptMessage;
				if (runtimeMessage?.type === "get_composer_state") {
					sendResponse(getComposerState({ document: root.document }));
					return false;
				}

				if (runtimeMessage?.type === "insert_text") {
					try {
						insertIntoComposer(
							assertNonEmpty(runtimeMessage?.payload?.text, "text"),
							{
								document: root.document,
								window: root,
								Event: root.Event,
								InputEvent: root.InputEvent,
							},
						);
						sendResponse({ ok: true });
					} catch (error) {
						sendResponse({
							ok: false,
							error: {
								message: String(
									(error as Error | undefined)?.message ||
										error ||
										"Insert failed",
								),
							},
						});
					}
					return false;
				}

				return false;
			},
		);
	}

	function getComposerState(options: ComposerStateOptions = {}): {
		available: boolean;
		message: string;
	} {
		const composer = findComposer(options.document);
		return {
			available: Boolean(composer),
			message: composer
				? "Composer detected"
				: "Open the X composer to insert drafts.",
		};
	}

	function findComposer(doc?: DocumentLike): ComposerElementLike | null {
		const documentRef = doc || globalThis.document;
		if (!documentRef?.querySelectorAll) {
			return null;
		}

		const candidates = documentRef.querySelectorAll(
			'[role="textbox"][contenteditable="true"][data-testid]',
		);
		for (const element of Array.from(candidates)) {
			if (isComposerElement(element)) {
				return element;
			}
		}
		return null;
	}

	function isComposerElement(
		element: ComposerElementLike | null | undefined,
	): boolean {
		const testId = String(element?.getAttribute?.("data-testid") || "");
		return COMPOSER_TEST_ID_PATTERN.test(testId);
	}

	function insertIntoComposer(
		text: string,
		options: InsertComposerOptions = {},
	): ComposerElementLike {
		const documentRef = options.document || globalThis.document;
		const windowRef = options.window || globalThis;
		const EventCtor = options.Event || globalThis.Event;
		const InputEventCtor = options.InputEvent || globalThis.InputEvent;
		const composer = findComposer(documentRef);
		if (!composer) {
			throw new Error("X composer not found. Open the composer first.");
		}

		composer.focus?.();
		const selection = windowRef?.getSelection?.();
		const range = documentRef?.createRange?.();
		if (!selection || !range) {
			composer.textContent = text;
			dispatchComposerInput(composer, text, { InputEvent: InputEventCtor });
			composer.dispatchEvent?.(new EventCtor("change", { bubbles: true }));
			return composer;
		}

		range.selectNodeContents(composer);
		selection.removeAllRanges();
		selection.addRange(range);
		range.deleteContents();

		const textNode = documentRef.createTextNode(text);
		range.insertNode(textNode);
		range.setStartAfter(textNode);
		range.collapse(true);
		selection.removeAllRanges();
		selection.addRange(range);

		dispatchComposerInput(composer, text, { InputEvent: InputEventCtor });
		composer.dispatchEvent?.(new EventCtor("change", { bubbles: true }));
		return composer;
	}

	function dispatchComposerInput(
		composer: ComposerElementLike,
		text: string,
		options: {
			InputEvent?: EventConstructorLike;
		} = {},
	): void {
		const InputEventCtor = options.InputEvent || globalThis.InputEvent;
		composer.dispatchEvent?.(
			new InputEventCtor("beforeinput", {
				bubbles: true,
				cancelable: true,
				inputType: "insertText",
				data: text,
			}),
		);
		composer.dispatchEvent?.(
			new InputEventCtor("input", {
				bubbles: true,
				cancelable: true,
				inputType: "insertText",
				data: text,
			}),
		);
	}

	function assertNonEmpty(value: unknown, name: string): string {
		const normalized = String(value || "").trim();
		if (!normalized) {
			throw new Error(`${name} is required`);
		}
		return normalized;
	}

	return {
		COMPOSER_TEST_ID_PATTERN,
		assertNonEmpty,
		dispatchComposerInput,
		findComposer,
		getComposerState,
		insertIntoComposer,
		installBridge,
		isComposerElement,
	};
});
