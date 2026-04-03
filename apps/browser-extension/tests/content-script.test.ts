import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);

interface FakeComposerElement {
	attributes: Record<string, string>;
	textContent: string;
	focused: boolean;
	events: FakeEvent[];
	getAttribute(name: string): string | null;
	focus(): void;
	dispatchEvent(event: FakeEvent): boolean;
}

interface FakeDocument {
	querySelectorAll(): FakeComposerElement[];
}

interface ContentScriptModule {
	findComposer(doc?: FakeDocument): FakeComposerElement | null;
	getComposerState(options?: { document?: FakeDocument }): {
		available: boolean;
		message: string;
	};
	insertIntoComposer(
		text: string,
		options?: {
			document?: FakeDocument;
			window?: { getSelection(): null };
			Event?: typeof FakeEvent;
			InputEvent?: typeof FakeEvent;
		},
	): FakeComposerElement;
}

const { findComposer, getComposerState, insertIntoComposer } =
	require("../dist/content-script.js") as ContentScriptModule;

class FakeEvent {
	type: string;

	constructor(type: string, init: Record<string, unknown> = {}) {
		this.type = type;
		Object.assign(this, init);
	}
}

function createElement(
	attributes: Record<string, string> = {},
): FakeComposerElement {
	return {
		attributes: { ...attributes },
		textContent: "",
		focused: false,
		events: [],
		getAttribute(name) {
			return this.attributes[name] ?? null;
		},
		focus() {
			this.focused = true;
		},
		dispatchEvent(event) {
			this.events.push(event);
			return true;
		},
	};
}

function createDocument(elements: FakeComposerElement[]): FakeDocument {
	return {
		querySelectorAll() {
			return elements;
		},
	};
}

test("findComposer ignores search and DM textboxes but accepts tweet composer variants", () => {
	const searchBox = createElement({
		"data-testid": "SearchBox_Search_Input",
		role: "textbox",
		contenteditable: "true",
	});
	const dmComposer = createElement({
		"data-testid": "dmComposerTextInput",
		role: "textbox",
		contenteditable: "true",
	});
	const replyComposer = createElement({
		"data-testid": "tweetTextarea_1",
		role: "textbox",
		contenteditable: "true",
	});

	const composer = findComposer(
		createDocument([searchBox, dmComposer, replyComposer]),
	);
	assert.equal(composer, replyComposer);
});

test("getComposerState reports missing composer without matching unrelated textboxes", () => {
	const searchBox = createElement({
		"data-testid": "SearchBox_Search_Input",
		role: "textbox",
		contenteditable: "true",
	});
	const dmComposer = createElement({
		"data-testid": "dmComposerTextInput",
		role: "textbox",
		contenteditable: "true",
	});

	const state = getComposerState({
		document: createDocument([searchBox, dmComposer]),
	});
	assert.deepEqual(state, {
		available: false,
		message: "Open the X composer to insert drafts.",
	});
});

test("insertIntoComposer writes only into the detected tweet composer", () => {
	const searchBox = createElement({
		"data-testid": "SearchBox_Search_Input",
		role: "textbox",
		contenteditable: "true",
	});
	const tweetComposer = createElement({
		"data-testid": "tweetTextarea_0",
		role: "textbox",
		contenteditable: "true",
	});

	const composer = insertIntoComposer("hello world", {
		document: createDocument([searchBox, tweetComposer]),
		window: { getSelection: () => null },
		Event: FakeEvent,
		InputEvent: FakeEvent,
	});

	assert.equal(composer, tweetComposer);
	assert.equal(tweetComposer.textContent, "hello world");
	assert.equal(searchBox.textContent, "");
	assert.equal(tweetComposer.focused, true);
	assert.deepEqual(
		tweetComposer.events.map((event) => event.type),
		["beforeinput", "input", "change"],
	);
});

test("insertIntoComposer throws when no tweet composer exists", () => {
	const dmComposer = createElement({
		"data-testid": "dmComposerTextInput",
		role: "textbox",
		contenteditable: "true",
	});

	assert.throws(
		() =>
			insertIntoComposer("hello", {
				document: createDocument([dmComposer]),
				window: { getSelection: () => null },
				Event: FakeEvent,
				InputEvent: FakeEvent,
			}),
		/X composer not found/,
	);
});
