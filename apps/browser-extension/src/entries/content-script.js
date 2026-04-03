(function (globalRoot, factory) {
	const api = factory();
	if (typeof module !== "undefined" && module.exports) {
		module.exports = api;
	}
	if (globalRoot?.chrome?.runtime?.onMessage && globalRoot?.document) {
		api.installBridge(globalRoot);
	}
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
	const COMPOSER_TEST_ID_PATTERN = /^tweetTextarea(?:_\d+)?$/;

	function installBridge(root) {
		if (root.__stakedMediaCopilotBridgeLoaded) {
			return;
		}
		root.__stakedMediaCopilotBridgeLoaded = true;

		root.chrome.runtime.onMessage.addListener(
			(message, _sender, sendResponse) => {
				if (message?.type === "get_composer_state") {
					sendResponse(getComposerState({ document: root.document }));
					return false;
				}

				if (message?.type === "insert_text") {
					try {
						insertIntoComposer(assertNonEmpty(message?.payload?.text, "text"), {
							document: root.document,
							window: root,
							Event: root.Event,
							InputEvent: root.InputEvent,
						});
						sendResponse({ ok: true });
					} catch (error) {
						sendResponse({
							ok: false,
							error: {
								message: String(error?.message || error || "Insert failed"),
							},
						});
					}
					return false;
				}

				return false;
			},
		);
	}

	function getComposerState(options = {}) {
		const composer = findComposer(options.document);
		return {
			available: Boolean(composer),
			message: composer
				? "Composer detected"
				: "Open the X composer to insert drafts.",
		};
	}

	function findComposer(doc) {
		const documentRef = doc || globalThis.document;
		if (!documentRef?.querySelectorAll) {
			return null;
		}

		const candidates = documentRef.querySelectorAll(
			'[role="textbox"][contenteditable="true"][data-testid]',
		);
		for (const element of candidates) {
			if (isComposerElement(element)) {
				return element;
			}
		}
		return null;
	}

	function isComposerElement(element) {
		const testId = String(element?.getAttribute?.("data-testid") || "");
		return COMPOSER_TEST_ID_PATTERN.test(testId);
	}

	function insertIntoComposer(text, options = {}) {
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

	function dispatchComposerInput(composer, text, options = {}) {
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

	function assertNonEmpty(value, name) {
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
