interface StakedMediaExtensionSharedHost {
	StakedMediaExtensionShared?: unknown;
}

(function (globalRoot, factory) {
	const api = factory();
	globalRoot.StakedMediaExtensionShared = api;
	if (typeof module !== "undefined" && module.exports) {
		module.exports = api;
	}
})(
	typeof globalThis !== "undefined"
		? (globalThis as StakedMediaExtensionSharedHost)
		: (this as StakedMediaExtensionSharedHost),
	function () {
		const FALLBACK_BACKEND_BASE_URL = "https://api.sayviner.top:8443";

		const ALLOWED_BACKEND_HOSTS: ReadonlySet<string> = new Set([
			"api.sayviner.top",
			"127.0.0.1",
			"localhost",
		]);

		type ThemeMode = "light" | "dark" | "system";
		type ApiMode = "content" | "drafts";
		type HostMode = "sidepanel" | "popup";
		type Locale = "en" | "zh-CN" | "zh-TW" | "ja" | "ko" | "es";
		type LanguageMode = "auto" | Locale;

		interface ExtensionConfig {
			defaultUsername: string;
			backendBaseUrl: string;
			apiMode: ApiMode;
			theme: ThemeMode;
			hostMode: HostMode;
			language: LanguageMode;
		}

		interface NormalizeOptions {
			strictBackendBaseUrl?: boolean;
		}

		interface RuntimeErrorWithStatus extends Error {
			status?: number;
			payload?: unknown;
			path?: string;
			code?: string;
		}

		interface RuntimeResponse<_T = unknown> {
			ok?: boolean;
			error?: {
				message?: string;
				status?: number;
				payload?: unknown;
				path?: string;
				code?: string;
			};
		}

		interface LanguageOption {
			value: LanguageMode;
			label: string;
		}

		type DraftRecord = { text?: string } & Record<string, unknown>;

		interface DraftVariant {
			drafts?: DraftRecord[] | null;
		}

		interface DraftSource {
			drafts?: DraftRecord[] | null;
			variants?: DraftVariant[] | null;
			formatted_drafts?: string[] | null;
		}

		const DEFAULT_CONFIG: Readonly<ExtensionConfig> = Object.freeze({
			defaultUsername: "",
			backendBaseUrl: FALLBACK_BACKEND_BASE_URL,
			apiMode: "drafts",
			theme: "light",
			hostMode: "sidepanel",
			language: "auto",
		});

		const SUPPORTED_LANGUAGE_VALUES: ReadonlySet<string> = new Set([
			"auto",
			"en",
			"zh-cn",
			"zh-tw",
			"ja",
			"ko",
			"es",
		]);

		const CORE_I18N: Record<Locale, Record<string, string>> = {
			en: {
				"app.title": "X Copilot",
				"settings.title": "Settings",
				"settings.apiPageTitle": "API & Generation",
				"settings.apiGeneration": "API & Generation",
				"settings.switchToPopup": "Switch to Popup",
				"settings.switchToSidePanel": "Switch to Side Panel",
				"settings.backToSettings": "Back to settings",
				"settings.backToMainView": "Back to main view",
				"tab.profile": "Profile",
				"tab.draft": "Draft",
				"tab.conversation": "Conversation",
				"section.result": "Result",
				"section.hotEvents24h": "24h Hot Events",
				"section.conversationResult": "Conversation Result",
				"label.topicIdea": "Topic / Idea",
				"label.draftCount": "Draft Count",
				"label.takeOptional": "What is your take? (optional)",
				"label.theme": "Theme",
				"label.language": "Language",
				"label.apiBaseUrl": "API Base URL",
				"label.generationApiMode": "Generation API Mode",
				"helper.apiBaseUrlSave":
					"Press Enter or click outside to save the URL.",
				"mode.draftsApi": "Drafts API (/api/v1/drafts/generate)",
				"mode.contentApi": "Content API (/api/v1/content/generate)",
				"theme.light": "Light",
				"theme.dark": "Dark",
				"theme.system": "System",
				"language.option.auto": "Auto (Browser)",
				"action.load": "Load",
				"action.ingest": "Ingest",
				"action.generate": "Generate",
				"action.generating": "Generating",
				"action.clear": "Clear",
				"action.refreshHot": "Refresh",
				"action.sendToDraft": "Send to Draft",
				"action.select": "Select",
				"action.selected": "Selected",
				"action.copy": "Copy",
				"action.insert": "Insert",
			},
			"zh-CN": {
				"app.title": "X 助手",
				"settings.title": "设置",
				"settings.apiPageTitle": "API 与生成",
				"settings.apiGeneration": "API 与生成",
				"settings.switchToPopup": "切换到弹窗",
				"settings.switchToSidePanel": "切换到侧边栏",
				"settings.backToSettings": "返回设置",
				"settings.backToMainView": "返回主界面",
				"tab.profile": "档案",
				"tab.draft": "草稿",
				"tab.conversation": "对话",
				"section.result": "结果",
				"section.hotEvents24h": "24 小时热点",
				"section.conversationResult": "对话结果",
				"label.topicIdea": "主题 / 想法",
				"label.draftCount": "草稿数量",
				"label.takeOptional": "你的补充观点（可选）",
				"label.theme": "主题",
				"label.language": "语言",
				"label.apiBaseUrl": "API 地址",
				"label.generationApiMode": "生成接口模式",
				"helper.apiBaseUrlSave": "按回车或点击空白处保存地址。",
				"mode.draftsApi": "草稿接口 (/api/v1/drafts/generate)",
				"mode.contentApi": "内容接口 (/api/v1/content/generate)",
				"theme.light": "浅色",
				"theme.dark": "深色",
				"theme.system": "跟随系统",
				"language.option.auto": "自动（跟随浏览器）",
				"action.load": "加载",
				"action.ingest": "采集",
				"action.generate": "生成",
				"action.generating": "生成中",
				"action.clear": "清空",
				"action.refreshHot": "刷新热点",
				"action.sendToDraft": "发送到 Draft",
				"action.select": "选择",
				"action.selected": "已选择",
				"action.copy": "复制",
				"action.insert": "插入",
			},
			"zh-TW": {
				"app.title": "X 助手",
				"settings.title": "設定",
				"settings.apiPageTitle": "API 與生成",
				"settings.apiGeneration": "API 與生成",
				"settings.switchToPopup": "切換到彈窗",
				"settings.switchToSidePanel": "切換到側邊欄",
				"settings.backToSettings": "返回設定",
				"settings.backToMainView": "返回主畫面",
				"tab.profile": "檔案",
				"tab.draft": "草稿",
				"tab.conversation": "對話",
				"section.result": "結果",
				"section.hotEvents24h": "24 小時熱點",
				"section.conversationResult": "對話結果",
				"label.topicIdea": "主題 / 想法",
				"label.draftCount": "草稿數量",
				"label.takeOptional": "你的補充觀點（可選）",
				"label.theme": "主題",
				"label.language": "語言",
				"label.apiBaseUrl": "API 位址",
				"label.generationApiMode": "生成介面模式",
				"helper.apiBaseUrlSave": "按 Enter 或點空白處儲存位址。",
				"mode.draftsApi": "草稿介面 (/api/v1/drafts/generate)",
				"mode.contentApi": "內容介面 (/api/v1/content/generate)",
				"theme.light": "淺色",
				"theme.dark": "深色",
				"theme.system": "跟隨系統",
				"language.option.auto": "自動（跟隨瀏覽器）",
				"action.load": "載入",
				"action.ingest": "匯入",
				"action.generate": "生成",
				"action.generating": "生成中",
				"action.clear": "清除",
				"action.refreshHot": "刷新熱點",
				"action.sendToDraft": "發送到 Draft",
				"action.select": "選擇",
				"action.selected": "已選擇",
				"action.copy": "複製",
				"action.insert": "插入",
			},
			ja: {
				"app.title": "X Copilot",
				"settings.title": "設定",
				"settings.apiPageTitle": "API と生成",
				"settings.apiGeneration": "API と生成",
				"settings.switchToPopup": "ポップアップに切替",
				"settings.switchToSidePanel": "サイドパネルに切替",
				"settings.backToSettings": "設定に戻る",
				"settings.backToMainView": "メイン画面に戻る",
				"tab.profile": "プロフィール",
				"tab.draft": "下書き",
				"tab.conversation": "会話",
				"section.result": "結果",
				"section.hotEvents24h": "24時間ホットイベント",
				"section.conversationResult": "会話結果",
				"label.topicIdea": "トピック / アイデア",
				"label.draftCount": "下書き数",
				"label.takeOptional": "補足意見（任意）",
				"label.theme": "テーマ",
				"label.language": "言語",
				"label.apiBaseUrl": "API Base URL",
				"label.generationApiMode": "生成 API モード",
				"helper.apiBaseUrlSave": "Enter キーまたは外側クリックで保存します。",
				"mode.draftsApi": "Drafts API (/api/v1/drafts/generate)",
				"mode.contentApi": "Content API (/api/v1/content/generate)",
				"theme.light": "ライト",
				"theme.dark": "ダーク",
				"theme.system": "システム",
				"language.option.auto": "自動（ブラウザ）",
				"action.load": "読み込み",
				"action.ingest": "取り込み",
				"action.generate": "生成",
				"action.generating": "生成中",
				"action.clear": "クリア",
				"action.refreshHot": "更新",
				"action.sendToDraft": "Draft へ送信",
				"action.select": "選択",
				"action.selected": "選択済み",
				"action.copy": "コピー",
				"action.insert": "挿入",
			},
			ko: {
				"app.title": "X Copilot",
				"settings.title": "설정",
				"settings.apiPageTitle": "API 및 생성",
				"settings.apiGeneration": "API 및 생성",
				"settings.switchToPopup": "팝업으로 전환",
				"settings.switchToSidePanel": "사이드 패널로 전환",
				"settings.backToSettings": "설정으로 돌아가기",
				"settings.backToMainView": "메인 화면으로 돌아가기",
				"tab.profile": "프로필",
				"tab.draft": "초안",
				"tab.conversation": "대화",
				"section.result": "결과",
				"section.hotEvents24h": "24시간 핫이슈",
				"section.conversationResult": "대화 결과",
				"label.topicIdea": "주제 / 아이디어",
				"label.draftCount": "초안 수",
				"label.takeOptional": "추가 의견 (선택)",
				"label.theme": "테마",
				"label.language": "언어",
				"label.apiBaseUrl": "API Base URL",
				"label.generationApiMode": "생성 API 모드",
				"helper.apiBaseUrlSave": "Enter 키 또는 바깥 클릭으로 저장합니다.",
				"mode.draftsApi": "Drafts API (/api/v1/drafts/generate)",
				"mode.contentApi": "Content API (/api/v1/content/generate)",
				"theme.light": "라이트",
				"theme.dark": "다크",
				"theme.system": "시스템",
				"language.option.auto": "자동 (브라우저)",
				"action.load": "불러오기",
				"action.ingest": "수집",
				"action.generate": "생성",
				"action.generating": "생성 중",
				"action.clear": "지우기",
				"action.refreshHot": "새로고침",
				"action.sendToDraft": "Draft로 보내기",
				"action.select": "선택",
				"action.selected": "선택됨",
				"action.copy": "복사",
				"action.insert": "삽입",
			},
			es: {
				"app.title": "X Copilot",
				"settings.title": "Configuración",
				"settings.apiPageTitle": "API y Generación",
				"settings.apiGeneration": "API y Generación",
				"settings.switchToPopup": "Cambiar a ventana emergente",
				"settings.switchToSidePanel": "Cambiar a panel lateral",
				"settings.backToSettings": "Volver a configuración",
				"settings.backToMainView": "Volver a la vista principal",
				"tab.profile": "Perfil",
				"tab.draft": "Borrador",
				"tab.conversation": "Conversación",
				"section.result": "Resultado",
				"section.hotEvents24h": "Eventos calientes 24h",
				"section.conversationResult": "Resultado de conversación",
				"label.topicIdea": "Tema / Idea",
				"label.draftCount": "Cantidad de borradores",
				"label.takeOptional": "Tu opinión (opcional)",
				"label.theme": "Tema",
				"label.language": "Idioma",
				"label.apiBaseUrl": "URL base de API",
				"label.generationApiMode": "Modo de API de generación",
				"helper.apiBaseUrlSave": "Pulsa Enter o haz clic fuera para guardar.",
				"mode.draftsApi": "API de borradores (/api/v1/drafts/generate)",
				"mode.contentApi": "API de contenido (/api/v1/content/generate)",
				"theme.light": "Claro",
				"theme.dark": "Oscuro",
				"theme.system": "Sistema",
				"language.option.auto": "Automático (navegador)",
				"action.load": "Cargar",
				"action.ingest": "Ingerir",
				"action.generate": "Generar",
				"action.generating": "Generando",
				"action.clear": "Limpiar",
				"action.refreshHot": "Actualizar",
				"action.sendToDraft": "Enviar a Draft",
				"action.select": "Seleccionar",
				"action.selected": "Seleccionado",
				"action.copy": "Copiar",
				"action.insert": "Insertar",
			},
		};

		const LANGUAGE_NATIVE_LABELS: Record<Locale, string> = {
			en: "English",
			"zh-CN": "简体中文",
			"zh-TW": "繁體中文",
			ja: "日本語",
			ko: "한국어",
			es: "Español",
		};

		function normalizeBaseUrl(value: unknown): string {
			return String(value || "")
				.trim()
				.replace(/\/+$/, "");
		}

		function normalizeHostMode(value: unknown): HostMode {
			return value === "popup" ? "popup" : "sidepanel";
		}

		function normalizeApiMode(value: unknown): ApiMode {
			return value === "drafts" ? "drafts" : "content";
		}

		function normalizeTheme(value: unknown): ThemeMode {
			const normalized = String(value || "").trim();
			if (normalized === "dark" || normalized === "system") {
				return normalized;
			}
			return DEFAULT_CONFIG.theme;
		}

		function normalizeLanguage(value: unknown): LanguageMode {
			const normalized = String(value || "")
				.trim()
				.toLowerCase();
			if (!SUPPORTED_LANGUAGE_VALUES.has(normalized)) {
				return "auto";
			}
			if (normalized === "zh-cn") {
				return "zh-CN";
			}
			if (normalized === "zh-tw") {
				return "zh-TW";
			}
			return normalized as LanguageMode;
		}

		function resolveLocale(
			languageSetting: unknown,
			browserLanguage: unknown,
		): Locale {
			const normalizedSetting = normalizeLanguage(languageSetting);
			if (normalizedSetting !== "auto") {
				return normalizedSetting;
			}
			const normalizedBrowserLanguage = String(browserLanguage || "")
				.trim()
				.toLowerCase();
			if (
				normalizedBrowserLanguage.startsWith("zh-tw") ||
				normalizedBrowserLanguage.startsWith("zh-hk") ||
				normalizedBrowserLanguage.startsWith("zh-mo")
			) {
				return "zh-TW";
			}
			if (normalizedBrowserLanguage.startsWith("zh")) {
				return "zh-CN";
			}
			if (normalizedBrowserLanguage.startsWith("ja")) {
				return "ja";
			}
			if (normalizedBrowserLanguage.startsWith("ko")) {
				return "ko";
			}
			if (normalizedBrowserLanguage.startsWith("es")) {
				return "es";
			}
			return "en";
		}

		function t(key: string, locale: Locale): string {
			const dictionary = CORE_I18N[locale] || CORE_I18N.en;
			return dictionary[key] || CORE_I18N.en[key] || key;
		}

		function listLanguageOptions(locale: Locale): LanguageOption[] {
			return [
				{
					value: "auto",
					label: t("language.option.auto", locale),
				},
				{
					value: "en",
					label: LANGUAGE_NATIVE_LABELS.en,
				},
				{
					value: "zh-CN",
					label: LANGUAGE_NATIVE_LABELS["zh-CN"],
				},
				{
					value: "zh-TW",
					label: LANGUAGE_NATIVE_LABELS["zh-TW"],
				},
				{
					value: "ja",
					label: LANGUAGE_NATIVE_LABELS.ja,
				},
				{
					value: "ko",
					label: LANGUAGE_NATIVE_LABELS.ko,
				},
				{
					value: "es",
					label: LANGUAGE_NATIVE_LABELS.es,
				},
			];
		}

		function normalizeBackendBaseUrl(
			value: unknown,
			options?: NormalizeOptions,
		): string {
			const strictBackendBaseUrl = Boolean(options?.strictBackendBaseUrl);
			const candidate =
				normalizeBaseUrl(value || FALLBACK_BACKEND_BASE_URL) ||
				FALLBACK_BACKEND_BASE_URL;

			try {
				const parsed = new URL(candidate);
				if (!/^https?:$/.test(parsed.protocol)) {
					throw new Error("Unsupported backend protocol");
				}
				if (parsed.username || parsed.password) {
					throw new Error("Backend URL credentials are not supported");
				}
				if (!ALLOWED_BACKEND_HOSTS.has(parsed.hostname)) {
					throw new Error(
						`Backend host "${parsed.hostname}" is not in the allowed list. Allowed: ${[...ALLOWED_BACKEND_HOSTS].join(", ")}`,
					);
				}
				if (
					parsed.hostname === "api.sayviner.top" &&
					parsed.protocol !== "https:"
				) {
					throw new Error("Hosted backend requires https");
				}
				if (
					(parsed.hostname === "127.0.0.1" ||
						parsed.hostname === "localhost") &&
					parsed.protocol !== "http:"
				) {
					throw new Error("Local backend requires http");
				}
				const normalizedPath =
					parsed.pathname && parsed.pathname !== "/"
						? parsed.pathname.replace(/\/+$/, "")
						: "";
				return `${parsed.protocol}//${parsed.host}${normalizedPath}`;
			} catch (_error) {
				if (strictBackendBaseUrl) {
					throw new Error(
						"Backend URL must be a valid http(s) URL pointing to an allowed host.",
					);
				}
				return FALLBACK_BACKEND_BASE_URL;
			}
		}

		function sanitizeConfig(
			config: Partial<ExtensionConfig> | null | undefined,
			options?: NormalizeOptions,
		): ExtensionConfig {
			const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
			return {
				defaultUsername:
					typeof merged.defaultUsername === "string"
						? merged.defaultUsername.trim()
						: "",
				backendBaseUrl: normalizeBackendBaseUrl(merged.backendBaseUrl, options),
				apiMode: normalizeApiMode(merged.apiMode),
				theme: normalizeTheme(merged.theme),
				hostMode: normalizeHostMode(merged.hostMode),
				language: normalizeLanguage(merged.language),
			};
		}

		async function routeMessage<TPayload = unknown, TResult = unknown>(
			message: { type?: string; payload?: TPayload } | null | undefined,
			handlers: Record<
				string,
				(payload: TPayload, rawMessage: unknown) => Promise<TResult> | TResult
			>,
		): Promise<TResult> {
			const type = String(message?.type || "");
			const handler = handlers?.[type];
			if (typeof handler !== "function") {
				throw new Error(`Unsupported message type: ${type}`);
			}
			return handler(
				(message?.payload || ({} as TPayload)) as TPayload,
				message,
			);
		}

		function extractDrafts(
			result: DraftSource | null | undefined,
		): DraftRecord[] {
			if (!result) return [];
			if (Array.isArray(result.drafts) && result.drafts.length) {
				return result.drafts;
			}
			if (Array.isArray(result.variants)) {
				for (const variant of result.variants) {
					if (Array.isArray(variant.drafts) && variant.drafts.length) {
						return variant.drafts;
					}
				}
			}
			if (
				Array.isArray(result.formatted_drafts) &&
				result.formatted_drafts.length
			) {
				return result.formatted_drafts.map((text: string) => ({ text }));
			}
			return [];
		}

		function escapeHtml(value: unknown): string {
			return String(value || "")
				.replace(/&/g, "&amp;")
				.replace(/</g, "&lt;")
				.replace(/>/g, "&gt;")
				.replace(/"/g, "&quot;")
				.replace(/'/g, "&#39;");
		}

		function coerceWindowId(value: unknown): number | null {
			const parsed = Number.parseInt(String(value), 10);
			return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
		}

		function sendRuntimeMessage<TResponse = unknown>(
			message: unknown,
		): Promise<TResponse> {
			return new Promise((resolve, reject) => {
				chrome.runtime.sendMessage(
					message,
					(response: RuntimeResponse<TResponse> & TResponse) => {
						const runtimeError = chrome.runtime.lastError;
						if (runtimeError) {
							reject(new Error(runtimeError.message));
							return;
						}
						if (!response?.ok) {
							const error = new Error(
								response?.error?.message || "Request failed",
							) as RuntimeErrorWithStatus;
							if (response?.error?.status) {
								error.status = response.error.status;
							}
							if (response?.error?.payload) {
								error.payload = response.error.payload;
							}
							if (response?.error?.path) {
								error.path = response.error.path;
							}
							if (response?.error?.code) {
								error.code = response.error.code;
							}
							reject(error);
							return;
						}
						resolve(response as TResponse);
					},
				);
			});
		}

		return {
			DEFAULT_CONFIG,
			ALLOWED_BACKEND_HOSTS,
			FALLBACK_BACKEND_BASE_URL,
			coerceWindowId,
			escapeHtml,
			extractDrafts,
			normalizeBaseUrl,
			normalizeHostMode,
			resolveLocale,
			routeMessage,
			sanitizeConfig,
			sendRuntimeMessage,
			t,
			listLanguageOptions,
		};
	},
);
