import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);

const { buildPanelShell, deriveConnectionIndicator, isWhitelistDeniedError } =
	require("../dist/panel-helpers.js") as Pick<
		StakedMediaPanelHelpersApi,
		"buildPanelShell" | "deriveConnectionIndicator" | "isWhitelistDeniedError"
	>;

test("deriveConnectionIndicator distinguishes loading from failed health checks", () => {
	const loading = deriveConnectionIndicator({
		health: null,
		latencyMs: null,
		healthState: "loading",
	});
	const failed = deriveConnectionIndicator({
		health: null,
		latencyMs: null,
		healthState: "error",
	});

	assert.equal(loading.title, "Checking...");
	assert.equal(loading.className, "smc-status-dot smc-dot-warn");
	assert.equal(loading.latencyText, "--");

	assert.equal(failed.title, "Disconnected");
	assert.equal(failed.className, "smc-status-dot smc-dot-err");
	assert.equal(failed.latencyText, "");
});

test("deriveConnectionIndicator renders connected state with latency", () => {
	const connected = deriveConnectionIndicator({
		health: { status: "ok" },
		latencyMs: 123,
		healthState: "ready",
	});

	assert.equal(connected.title, "Connected 123ms");
	assert.equal(connected.className, "smc-status-dot smc-dot-ok");
	assert.equal(connected.latencyText, "123ms");
});

test("buildPanelShell places the status banner outside both tabs", () => {
	const markup = buildPanelShell();
	const tabBarIndex = markup.indexOf('class="smc-tab-bar"');
	const statusSectionIndex = markup.indexOf('data-slot="status-section"');
	const profilePanelIndex = markup.indexOf('data-tab-panel="profile"');
	const draftPanelIndex = markup.indexOf('data-tab-panel="draft"');

	assert.notEqual(tabBarIndex, -1);
	assert.notEqual(statusSectionIndex, -1);
	assert.notEqual(profilePanelIndex, -1);
	assert.notEqual(draftPanelIndex, -1);
	assert.ok(statusSectionIndex > tabBarIndex);
	assert.ok(statusSectionIndex < profilePanelIndex);
	assert.ok(statusSectionIndex < draftPanelIndex);
	assert.equal((markup.match(/data-slot="status"/g) || []).length, 1);
});

test("buildPanelShell places the username error directly below the username row", () => {
	const markup = buildPanelShell();
	const usernameRowIndex = markup.indexOf('class="smc-username-row"');
	const usernameErrorIndex = markup.indexOf('data-slot="username-error"');
	const profileInfoIndex = markup.indexOf('data-slot="profile-info"');

	assert.notEqual(usernameRowIndex, -1);
	assert.notEqual(usernameErrorIndex, -1);
	assert.notEqual(profileInfoIndex, -1);
	assert.ok(usernameErrorIndex > usernameRowIndex);
	assert.ok(usernameErrorIndex < profileInfoIndex);
});

test("buildPanelShell includes conversation tab controls", () => {
	const markup = buildPanelShell();

	assert.notEqual(markup.indexOf('data-tab-target="conversation"'), -1);
	assert.notEqual(markup.indexOf('data-tab-panel="conversation"'), -1);
	assert.notEqual(markup.indexOf('data-action="refresh-hot-events"'), -1);
	assert.notEqual(markup.indexOf('data-action="generate-conversation"'), -1);
	assert.notEqual(markup.indexOf('data-action="send-to-draft"'), -1);
	assert.notEqual(markup.indexOf('data-slot="hot-events-meta"'), -1);
	assert.notEqual(markup.indexOf('data-slot="hot-events"'), -1);
	assert.notEqual(markup.indexOf('data-slot="conversation-results"'), -1);
	assert.notEqual(markup.indexOf('data-slot="send-to-draft-hint"'), -1);
	assert.notEqual(markup.indexOf('data-field="s-language"'), -1);
});

test("isWhitelistDeniedError matches API 403 responses only", () => {
	assert.equal(isWhitelistDeniedError({ status: 403 }), true);
	assert.equal(isWhitelistDeniedError({ status: 422 }), false);
	assert.equal(isWhitelistDeniedError({}), false);
	assert.equal(isWhitelistDeniedError(null), false);
});
