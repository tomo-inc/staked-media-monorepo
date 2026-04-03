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

		function buildPanelShell(): string {
			return `
      <div class="smc-shell">
        <aside class="smc-panel">
          <header class="smc-header">
            <div class="smc-header-left">
              <button class="smc-icon-button smc-back-button" data-action="close-settings" type="button" aria-label="Back to main view" hidden>
                <span aria-hidden="true">&lt;</span>
              </button>
              <h1 class="smc-title" data-slot="header-title">X Copilot</h1>
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
              <button class="smc-tab smc-tab-active" data-tab-target="profile" type="button">Profile</button>
              <button class="smc-tab" data-tab-target="draft" type="button">Draft</button>
            </nav>

            <section class="smc-section" data-slot="status-section" hidden>
              <div data-slot="status"></div>
            </section>

            <div class="smc-tab-panel smc-tab-panel-active" data-tab-panel="profile">
              <section class="smc-section">
                <div class="smc-username-row">
                  <input class="smc-input" data-field="username" placeholder="@Username" type="text">
                  <button class="smc-button smc-button-secondary" data-action="load-profile" type="button">Load</button>
                  <button class="smc-button smc-button-secondary" data-action="ingest-profile" type="button">Ingest</button>
                </div>
                <div class="smc-field-message smc-field-message-error" data-slot="username-error" hidden></div>
                <div data-slot="profile-info"></div>
              </section>
            </div>

            <div class="smc-tab-panel" data-tab-panel="draft">
              <section class="smc-section">
                <label class="smc-label">
                  Topic / Idea
                  <textarea class="smc-textarea" data-field="idea" placeholder="Can Bitcoin be cracked in 9 minutes?&#10;Google warns ECC timeline may arrive earlier&#10;Attack threshold could be 20x lower"></textarea>
                </label>
                <label class="smc-label">
                  Draft Count
                  <input class="smc-input smc-input-short" data-field="draftCount" min="1" max="10" step="1" type="number" value="3">
                </label>
                <div class="smc-button-row">
                  <button class="smc-button smc-button-primary" data-action="generate" type="button">Generate</button>
                </div>
              </section>

              <section class="smc-section">
                <div class="smc-section-head">
                  <h2>Result</h2>
                  <div class="smc-section-head-right">
                    <div data-slot="composer"></div>
                    <button class="smc-link-button" data-action="clear-results" type="button">Clear</button>
                  </div>
                </div>
                <div data-slot="results"></div>
              </section>
            </div>
          </div>

          <div class="smc-view" data-view="settings">
            <div class="smc-settings-page smc-settings-page-active" data-settings-view="home">
              <section class="smc-section smc-settings-home-section">
                <div class="smc-settings-list">
                  <button class="smc-settings-item" data-action="open-api-settings" type="button">
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
                        <span class="smc-settings-item-title">API &amp; Generation</span>
                      </span>
                    </span>
                    <span class="smc-settings-item-chevron" aria-hidden="true">›</span>
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
                        <span class="smc-settings-item-title">Theme</span>
                      </span>
                    </span>
                    <select class="smc-settings-select" id="smc-theme-select" data-field="s-theme">
                      <option value="light">Light</option>
                      <option value="dark">Dark</option>
                      <option value="system">System</option>
                    </select>
                  </label>
                </div>
              </section>
            </div>

            <div class="smc-settings-page" data-settings-view="api">
              <section class="smc-section">
                <label class="smc-label">
                  API Base URL
                  <input class="smc-input" data-field="s-backendBaseUrl" type="text" placeholder="https://api.sayviner.top:8443">
                </label>
                <div class="smc-settings-helper">Press Enter or click outside to save the URL.</div>

                <label class="smc-label">
                  Generation API Mode
                </label>
                <div class="smc-radio-group">
                  <label class="smc-radio-option">
                    <input type="radio" name="s-apiMode" data-field="s-apiModeDrafts" value="drafts" checked>
                    Drafts API (/api/v1/drafts/generate)
                  </label>
                  <label class="smc-radio-option">
                    <input type="radio" name="s-apiMode" data-field="s-apiModeContent" value="content">
                    Content API (/api/v1/content/generate)
                  </label>
                </div>
              </section>
            </div>

            <section class="smc-section smc-settings-status-section" hidden>
              <div class="smc-settings-status" data-slot="settings-status"></div>
            </section>
          </div>

        </aside>
      </div>
    `;
		}

		const api: PanelHelpersApi = {
			buildPanelShell,
			deriveConnectionIndicator,
			isWhitelistDeniedError,
		};
		return api;
	},
);
