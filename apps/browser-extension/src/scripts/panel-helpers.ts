interface StakedMediaPanelHelpersHost {
	StakedMediaPanelHelpers?: unknown;
}

(function (globalRoot, factory) {
	const api = factory();
	globalRoot.StakedMediaPanelHelpers = api;
	if (typeof module !== "undefined" && module.exports) {
		module.exports = api;
	}
})(
	typeof globalThis !== "undefined"
		? (globalThis as StakedMediaPanelHelpersHost)
		: (this as StakedMediaPanelHelpersHost),
	function () {
		interface PanelHelpersApi {
			isWhitelistDeniedError(
				error: { status?: number } | null | undefined,
			): boolean;
			deriveConnectionIndicator(
				input: ConnectionIndicatorInput,
			): ConnectionIndicatorOutput;
			deriveHotEventsStateNotice(input: HotEventsStateNoticeInput): string[];
			buildPanelShell(): string;
		}

		interface ConnectionIndicatorInput {
			health?: { status?: string } | null;
			latencyMs?: number | null;
			healthState?: string;
		}

		interface ConnectionIndicatorOutput {
			className: string;
			title: string;
			latencyText: string;
		}

		interface HotEventsStateNoticeInput {
			refreshing?: boolean;
			isStale?: boolean;
			throttled?: boolean;
			nextRefreshAvailableInSeconds?: number | null;
			lastRefreshedAt?: string;
			lastAttemptedAt?: string;
			lastRefreshError?: string;
			formatTimestamp?: (value: string) => string;
		}

		function isWhitelistDeniedError(
			error: { status?: number } | null | undefined,
		): boolean {
			return Number(error?.status) === 403;
		}

		function deriveConnectionIndicator({
			health,
			latencyMs,
			healthState,
		}: ConnectionIndicatorInput): ConnectionIndicatorOutput {
			if (healthState === "ready" && health?.status === "ok") {
				return {
					className: "smc-status-dot smc-dot-ok",
					title: latencyMs != null ? `Connected ${latencyMs}ms` : "Connected",
					latencyText: latencyMs != null ? `${latencyMs}ms` : "",
				};
			}

			if (healthState === "error") {
				return {
					className: "smc-status-dot smc-dot-err",
					title: "Disconnected",
					latencyText: "",
				};
			}

			return {
				className: "smc-status-dot smc-dot-warn",
				title: "Checking...",
				latencyText: "--",
			};
		}

		function deriveHotEventsStateNotice({
			refreshing,
			isStale,
			throttled,
			nextRefreshAvailableInSeconds,
			lastRefreshedAt,
			lastAttemptedAt,
			lastRefreshError,
			formatTimestamp,
		}: HotEventsStateNoticeInput): string[] {
			const parts: string[] = [];
			const renderTimestamp =
				typeof formatTimestamp === "function"
					? formatTimestamp
					: (value: string) => value;

			if (refreshing) {
				parts.push("Refreshing hot events in background...");
			}
			if (throttled) {
				parts.push(
					Number(nextRefreshAvailableInSeconds) > 0
						? `Refresh cooldown active. Try again in ${Number(nextRefreshAvailableInSeconds)}s.`
						: "Refresh cooldown active. Using the latest cached snapshot.",
				);
			}
			if (isStale) {
				if (lastRefreshedAt) {
					parts.push(
						`Using cached snapshot from ${renderTimestamp(lastRefreshedAt)}.`,
					);
				} else {
					parts.push("Using the latest cached snapshot.");
				}
			}
			if (lastRefreshError) {
				const attemptedAt = lastAttemptedAt
					? ` Latest refresh attempt at ${renderTimestamp(lastAttemptedAt)} failed.`
					: " Latest refresh attempt failed.";
				parts.push(`${attemptedAt} ${lastRefreshError}`.trim());
			}
			return parts;
		}

		function buildPanelShell(): string {
			return `
      <div class="smc-shell">
        <aside class="smc-panel">
          <header class="smc-header">
            <div class="smc-header-left">
              <button class="smc-icon-button smc-back-button" data-action="close-settings" type="button" aria-label="Back to main view" hidden>
                <span aria-hidden="true">&lt;</span>
              </button>
              <h1 class="smc-title" data-slot="header-title"></h1>
            </div>
            <div class="smc-header-right">
              <span class="smc-latency-text" data-slot="latency-text">--</span>
              <span class="smc-status-dot smc-dot-warn" data-slot="connection" title="Checking..."></span>
              <button class="smc-icon-button smc-menu-button" data-action="open-settings" type="button" aria-label="Open settings">
                <span class="smc-menu-icon" aria-hidden="true">
                  <span></span>
                  <span></span>
                  <span></span>
                </span>
              </button>
            </div>
          </header>

          <div class="smc-view smc-view-active" data-view="main">
            <nav class="smc-tab-bar">
              <button class="smc-tab smc-tab-active" data-tab-target="profile" data-i18n="tab.profile" type="button">Profile</button>
              <button class="smc-tab" data-tab-target="draft" data-i18n="tab.draft" type="button">Draft</button>
              <button class="smc-tab" data-tab-target="trending" data-i18n="tab.trending" type="button">Trending</button>
            </nav>

            <section class="smc-section" data-slot="status-section" hidden>
              <div data-slot="status"></div>
            </section>

            <div class="smc-tab-panel smc-tab-panel-active" data-tab-panel="profile">
              <section class="smc-section">
                <div class="smc-username-row">
                  <input class="smc-input" data-field="username" placeholder="@Username" type="text">
                  <button class="smc-button smc-button-secondary" data-action="load-profile" data-i18n="action.load" type="button">Load</button>
                  <button class="smc-button smc-button-secondary" data-action="ingest-profile" data-i18n="action.ingest" type="button">Ingest</button>
                </div>
                <div class="smc-field-message smc-field-message-error" data-slot="username-error" hidden></div>
                <div data-slot="profile-info"></div>
              </section>
            </div>

            <div class="smc-tab-panel" data-tab-panel="draft">
              <section class="smc-section">
                <label class="smc-label">
                  <span data-i18n="label.topicIdea">Topic / Idea</span>
                  <textarea class="smc-textarea" data-field="idea" placeholder="Can Bitcoin be cracked in 9 minutes?&#10;Google warns ECC timeline may arrive earlier&#10;Attack threshold could be 20x lower"></textarea>
                </label>
                <label class="smc-label">
                  <span data-i18n="label.draftCount">Draft Count</span>
                  <input class="smc-input smc-input-short" data-field="draftCount" min="1" max="10" step="1" type="number" value="3">
                </label>
                <div class="smc-button-row">
                  <button class="smc-button smc-button-primary" data-action="generate" data-i18n="action.generate" type="button">Generate</button>
                </div>
              </section>

              <section class="smc-section">
                <div class="smc-section-head">
                  <h2 data-i18n="section.result">Result</h2>
                  <div class="smc-section-head-right">
                    <div data-slot="composer"></div>
                    <button class="smc-link-button" data-action="clear-results" data-i18n="action.clear" type="button">Clear</button>
                  </div>
                </div>
                <div data-slot="results"></div>
              </section>
            </div>

            <div class="smc-tab-panel" data-tab-panel="trending">
              <section class="smc-section smc-section-trending-feed">
                <div class="smc-section-head">
                  <h2 data-i18n="section.hotEvents24h">24h Hot Events</h2>
                  <button class="smc-link-button" data-action="refresh-hot-events" data-i18n="action.refreshHot" type="button">Refresh</button>
                </div>
                <div class="smc-hot-meta" data-slot="hot-events-meta"></div>
                <div data-slot="hot-events"></div>
              </section>

              <section class="smc-section">
                <div data-slot="selected-hot-event-info"></div>
                <label class="smc-label">
                  <span data-i18n="label.takeOptional">What is your take? (optional)</span>
                  <textarea class="smc-textarea smc-textarea-compact" data-field="trendingComment" placeholder="Anything to add before generating?" rows="2"></textarea>
                </label>
                <label class="smc-label">
                  <span data-i18n="label.draftCount">Draft Count</span>
                  <input class="smc-input smc-input-short" data-field="trendingDraftCount" min="1" max="10" step="1" type="number" value="3">
                </label>
                <div class="smc-field-message smc-field-message-warn" data-slot="send-to-draft-hint" hidden></div>
                <div class="smc-button-row">
                  <button class="smc-button smc-button-primary" data-action="generate-trending" data-i18n="action.generate" type="button">Generate</button>
                  <button class="smc-button smc-button-secondary" data-action="send-to-draft" data-i18n="action.sendToDraft" type="button">Send to Draft</button>
                </div>
              </section>

              <section class="smc-section">
                <div class="smc-section-head">
                  <h2 data-i18n="section.trendingResult">Trending Result</h2>
                  <div class="smc-section-head-right">
                    <button class="smc-link-button" data-action="clear-trending-results" data-i18n="action.clear" type="button">Clear</button>
                  </div>
                </div>
                <div data-slot="trending-results"></div>
              </section>
            </div>
          </div>

          <div class="smc-view smc-settings-view" data-view="settings">
            <div class="smc-settings-body">
              <div class="smc-settings-page smc-settings-page-active" data-settings-view="home">
                <section class="smc-section smc-settings-home-section">
                  <div class="smc-settings-list">
                    <button class="smc-settings-item" data-action="open-api-settings" type="button" hidden>
                      <span class="smc-settings-item-main">
                        <span class="smc-settings-item-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24" fill="none">
                            <circle cx="6" cy="12" r="1.75" stroke="currentColor"></circle>
                            <circle cx="18" cy="6" r="1.75" stroke="currentColor"></circle>
                            <circle cx="18" cy="18" r="1.75" stroke="currentColor"></circle>
                            <path d="M7.6 11.2L16.3 6.8M7.6 12.8l8.7 4.4" stroke="currentColor" stroke-linecap="round"></path>
                          </svg>
                        </span>
                        <span class="smc-settings-item-copy">
                          <span class="smc-settings-item-title" data-i18n="settings.apiGeneration">API &amp; Generation</span>
                        </span>
                      </span>
                      <span class="smc-settings-item-chevron" aria-hidden="true">></span>
                    </button>

                    <button class="smc-settings-item" data-action="toggle-open-mode" type="button">
                      <span class="smc-settings-item-main">
                        <span class="smc-settings-item-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24" fill="none">
                            <rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor"></rect>
                            <path d="M10 5v14" stroke="currentColor" stroke-linecap="round"></path>
                          </svg>
                        </span>
                        <span class="smc-settings-item-copy">
                          <span class="smc-settings-item-title" data-slot="s-host-mode-title">Switch to Popup</span>
                        </span>
                      </span>
                    </button>

                    <label class="smc-settings-item smc-settings-item-select" for="smc-theme-select">
                      <span class="smc-settings-item-main">
                        <span class="smc-settings-item-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24" fill="none">
                            <path d="M12 3v2.2M12 18.8V21M4.9 4.9l1.6 1.6M17.5 17.5l1.6 1.6M3 12h2.2M18.8 12H21M4.9 19.1l1.6-1.6M17.5 6.5l1.6-1.6" stroke="currentColor" stroke-linecap="round"></path>
                            <circle cx="12" cy="12" r="4" stroke="currentColor"></circle>
                          </svg>
                        </span>
                        <span class="smc-settings-item-copy">
                          <span class="smc-settings-item-title" data-i18n="label.theme">Theme</span>
                        </span>
                      </span>
                      <select class="smc-settings-select" id="smc-theme-select" data-field="s-theme">
                        <option value="light">Light</option>
                        <option value="dark">Dark</option>
                        <option value="system">System</option>
                      </select>
                    </label>
                    <label class="smc-settings-item smc-settings-item-select" for="smc-language-select">
                      <span class="smc-settings-item-main">
                        <span class="smc-settings-item-icon" aria-hidden="true">
                          <svg viewBox="0 0 24 24" fill="none">
                            <path d="M4 6h8M8 4v2m0 0c0 4-1.6 6.6-4 8m4-8c.9 2.3 2.2 4.2 4 5.6M14 18h6M17 15v6" stroke="currentColor" stroke-linecap="round"></path>
                          </svg>
                        </span>
                        <span class="smc-settings-item-copy">
                          <span class="smc-settings-item-title" data-i18n="label.language">Language</span>
                        </span>
                      </span>
                      <select class="smc-settings-select" id="smc-language-select" data-field="s-language">
                        <option value="auto">Auto (Browser)</option>
                        <option value="en">English</option>
                        <option value="zh-CN">简体中文</option>
                        <option value="zh-TW">繁體中文</option>
                        <option value="ja">日本語</option>
                        <option value="ko">한국어</option>
                        <option value="es">Español</option>
                      </select>
                    </label>
                  </div>
                </section>
              </div>

              <div class="smc-settings-page" data-settings-view="api">
                <section class="smc-section">
                  <label class="smc-label">
                    <span data-i18n="label.apiBaseUrl">API Base URL</span>
                    <input class="smc-input" data-field="s-backendBaseUrl" type="text" placeholder="https://api.sayviner.top:8443">
                  </label>
                  <div class="smc-settings-helper" data-i18n="helper.apiBaseUrlSave">Press Enter or click outside to save the URL.</div>

                  <label class="smc-label">
                    <span data-i18n="label.generationApiMode">Generation API Mode</span>
                  </label>
                  <div class="smc-radio-group">
                    <label class="smc-radio-option">
                      <input type="radio" name="s-apiMode" data-field="s-apiModeDrafts" value="drafts" checked>
                      <span data-i18n="mode.draftsApi">Drafts API (/api/v1/drafts/generate)</span>
                    </label>
                    <label class="smc-radio-option">
                      <input type="radio" name="s-apiMode" data-field="s-apiModeContent" value="content">
                      <span data-i18n="mode.contentApi">Content API (/api/v1/content/generate)</span>
                    </label>
                  </div>
                </section>
              </div>

              <section class="smc-section smc-settings-status-section" hidden>
                <div class="smc-settings-status" data-slot="settings-status"></div>
              </section>
            </div>

            <section class="smc-settings-footer-section">
              <button class="smc-settings-version-button" data-action="unlock-debug" type="button">
                <span class="smc-settings-version-label" data-slot="settings-version"></span>
                <span class="smc-settings-version-mode" data-slot="settings-version-mode"></span>
              </button>
            </section>
          </div>

        </aside>
      </div>
    `;
		}

		const api: PanelHelpersApi = {
			buildPanelShell,
			deriveConnectionIndicator,
			deriveHotEventsStateNotice,
			isWhitelistDeniedError,
		};
		return api;
	},
);
