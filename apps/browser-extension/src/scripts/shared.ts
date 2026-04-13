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
		const DEFAULT_PUBLIC_ERROR_MESSAGE =
			"Service is temporarily unavailable. Please try again later.";

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
				"app.title": "FoxSpark",
				"app.titleNoProfile": "Load a profile to start",
				"settings.apiPageTitle": "API & Generation",
				"settings.apiGeneration": "API & Generation",
				"settings.versionLabel": "Version",
				"settings.debugMode": "Debug mode",
				"settings.productionMode": "Production mode",
				"settings.switchToPopup": "Switch to Popup",
				"settings.switchToSidePanel": "Switch to Side Panel",
				"settings.backToSettings": "Back to settings",
				"settings.backToMainView": "Back to main view",
				"tab.profile": "Profile",
				"tab.draft": "Draft",
				"tab.trending": "Trending",
				"section.result": "Result",
				"section.hotEvents24h": "24h Hot Events",
				"section.trendingResult": "Trending Result",
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
				"action.generating": "Thinking",
				"action.clear": "Clear",
				"action.refreshHot": "Refresh",
				"action.sendToDraft": "Send to Draft",
				"action.select": "Select",
				"action.selected": "Selected",
				"action.copy": "Copy",
				"action.insert": "Insert",
				"action.showOriginal": "Show Original",
				"action.showTranslation": "Show Translation",
				"action.showOriginalEvent": "Show original for this event",
				"action.showTranslationEvent": "Show translated version for this event",
				"action.showMore": "show more",
				"action.showLess": "show less",
				"hint.hotEventSelected":
					"Event selected - enter your perspective below and hit Generate.",
				"hint.selectHotEventBeforeGenerate": "Pick a hot event to continue.",
				"hint.sendSelectedEventToDraft":
					"We'll send the selected event and your take to Draft.",
				"error.profileNotReady": "Profile is not ready. Please ingest first.",
				"error.invalidInput": "Invalid input. Please check and try again.",
				"error.userNotAllowed":
					"This user is not authorized. Contact the administrator.",
				"error.serviceUnavailable": DEFAULT_PUBLIC_ERROR_MESSAGE,
				"profile.usernameRequired": "Username is required.",
				"profile.loading": "Loading profile...",
				"profile.notFound":
					"Profile not found. Click Ingest to fetch tweets and build persona.",
				"profile.personaMissing":
					"Profile loaded, but persona is missing. Click Ingest to build persona.",
				"profile.cardTitle": "Profile",
				"profile.followers": "Followers",
				"profile.following": "Following",
				"profile.tweets": "Tweets",
				"profile.persona": "Persona",
				"profile.personaReady": "Ready",
				"profile.personaMissingStatus": "Missing",
				"profile.personaPortrait": "Persona Portrait",
				"profile.summary": "Summary",
				"profile.voice": "Voice",
				"profile.topics": "Topics",
				"profile.ingestSuccess": "Ingested {count} tweets. Persona ready.",
			},
			"zh-CN": {
				"app.title": "FoxSpark",
				"app.titleNoProfile": "加载用户以开始",
				"settings.apiPageTitle": "API 与生成",
				"settings.apiGeneration": "API 与生成",
				"settings.versionLabel": "版本",
				"settings.debugMode": "调试模式",
				"settings.productionMode": "生产模式",
				"settings.switchToPopup": "切换到弹窗",
				"settings.switchToSidePanel": "切换到侧边栏",
				"settings.backToSettings": "返回设置",
				"settings.backToMainView": "返回主界面",
				"tab.profile": "档案",
				"tab.draft": "草稿",
				"tab.trending": "热点",
				"section.result": "结果",
				"section.hotEvents24h": "24 小时热点",
				"section.trendingResult": "热点结果",
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
				"action.generating": "思考中",
				"action.clear": "清空",
				"action.refreshHot": "刷新热点",
				"action.sendToDraft": "发送到 Draft",
				"action.select": "选择",
				"action.selected": "已选择",
				"action.copy": "复制",
				"action.insert": "插入",
				"action.showOriginal": "显示原文",
				"action.showTranslation": "显示翻译",
				"action.showOriginalEvent": "显示该事件原文",
				"action.showTranslationEvent": "显示该事件翻译",
				"action.showMore": "展开",
				"action.showLess": "收起",
				"hint.hotEventSelected":
					"已选择热点事件 - 在下方输入你的观点后点击生成。",
				"hint.selectHotEventBeforeGenerate": "请选择一个热点事件后继续。",
				"hint.sendSelectedEventToDraft":
					"我们会将已选事件和你的观点发送到 Draft。",
				"error.profileNotReady": "用户资料未就绪，请先采集。",
				"error.invalidInput": "输入有误，请检查后重试。",
				"error.userNotAllowed": "此用户未被授权，请联系管理员。",
				"error.serviceUnavailable": "服务暂时不可用，请稍后再试。",
				"profile.usernameRequired": "用户名不能为空。",
				"profile.loading": "正在加载档案...",
				"profile.notFound": "未找到档案。点击“采集”以抓取推文并生成人设。",
				"profile.personaMissing":
					"档案已加载，但人设缺失。点击“采集”以生成人设。",
				"profile.cardTitle": "档案",
				"profile.followers": "粉丝",
				"profile.following": "关注",
				"profile.tweets": "推文",
				"profile.persona": "人设",
				"profile.personaReady": "已就绪",
				"profile.personaMissingStatus": "缺失",
				"profile.personaPortrait": "人设画像",
				"profile.summary": "总结",
				"profile.voice": "风格",
				"profile.topics": "主题",
				"profile.ingestSuccess": "已采集 {count} 条推文，人设已就绪。",
			},
			"zh-TW": {
				"app.title": "FoxSpark",
				"app.titleNoProfile": "載入用戶以開始",
				"settings.apiPageTitle": "API 與生成",
				"settings.apiGeneration": "API 與生成",
				"settings.versionLabel": "版本",
				"settings.debugMode": "偵錯模式",
				"settings.productionMode": "正式模式",
				"settings.switchToPopup": "切換到彈窗",
				"settings.switchToSidePanel": "切換到側邊欄",
				"settings.backToSettings": "返回設定",
				"settings.backToMainView": "返回主畫面",
				"tab.profile": "檔案",
				"tab.draft": "草稿",
				"tab.trending": "熱門",
				"section.result": "結果",
				"section.hotEvents24h": "24 小時熱點",
				"section.trendingResult": "熱門結果",
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
				"action.generating": "思考中",
				"action.clear": "清除",
				"action.refreshHot": "刷新熱點",
				"action.sendToDraft": "發送到 Draft",
				"action.select": "選擇",
				"action.selected": "已選擇",
				"action.copy": "複製",
				"action.insert": "插入",
				"action.showOriginal": "顯示原文",
				"action.showTranslation": "顯示翻譯",
				"action.showOriginalEvent": "顯示該事件原文",
				"action.showTranslationEvent": "顯示該事件翻譯",
				"action.showMore": "展開",
				"action.showLess": "收起",
				"hint.hotEventSelected":
					"已選擇熱門事件 - 在下方輸入你的觀點後點擊生成。",
				"hint.selectHotEventBeforeGenerate": "請先選擇一個熱門事件再繼續。",
				"hint.sendSelectedEventToDraft":
					"我們會將已選事件和你的觀點發送到 Draft。",
				"error.profileNotReady": "使用者資料尚未就緒，請先匯入。",
				"error.invalidInput": "輸入有誤，請檢查後重試。",
				"error.userNotAllowed": "此使用者未被授權，請聯繫管理員。",
				"error.serviceUnavailable": "服務暫時不可用，請稍後再試。",
				"profile.usernameRequired": "使用者名稱不可為空。",
				"profile.loading": "正在載入檔案...",
				"profile.notFound": "找不到檔案。點擊「匯入」以抓取推文並建立人設。",
				"profile.personaMissing":
					"檔案已載入，但人設缺失。點擊「匯入」以建立人設。",
				"profile.cardTitle": "檔案",
				"profile.followers": "粉絲",
				"profile.following": "追蹤中",
				"profile.tweets": "推文",
				"profile.persona": "人設",
				"profile.personaReady": "已就緒",
				"profile.personaMissingStatus": "缺失",
				"profile.personaPortrait": "人設畫像",
				"profile.summary": "摘要",
				"profile.voice": "風格",
				"profile.topics": "主題",
				"profile.ingestSuccess": "已匯入 {count} 則推文，人設已就緒。",
			},
			ja: {
				"app.title": "FoxSpark",
				"app.titleNoProfile": "プロフィールを読み込んでください",
				"settings.apiPageTitle": "API と生成",
				"settings.apiGeneration": "API と生成",
				"settings.versionLabel": "バージョン",
				"settings.debugMode": "デバッグモード",
				"settings.productionMode": "本番モード",
				"settings.switchToPopup": "ポップアップに切替",
				"settings.switchToSidePanel": "サイドパネルに切替",
				"settings.backToSettings": "設定に戻る",
				"settings.backToMainView": "メイン画面に戻る",
				"tab.profile": "プロフィール",
				"tab.draft": "下書き",
				"tab.trending": "トレンド",
				"section.result": "結果",
				"section.hotEvents24h": "24時間ホットイベント",
				"section.trendingResult": "トレンド結果",
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
				"action.generating": "考え中",
				"action.clear": "クリア",
				"action.refreshHot": "更新",
				"action.sendToDraft": "Draft へ送信",
				"action.select": "選択",
				"action.selected": "選択済み",
				"action.copy": "コピー",
				"action.insert": "挿入",
				"action.showOriginal": "原文を表示",
				"action.showTranslation": "翻訳を表示",
				"action.showOriginalEvent": "このイベントの原文を表示",
				"action.showTranslationEvent": "このイベントの翻訳を表示",
				"action.showMore": "もっと見る",
				"action.showLess": "折りたたむ",
				"hint.hotEventSelected":
					"イベントを選択しました。下に視点を入力して Generate を押してください。",
				"hint.selectHotEventBeforeGenerate":
					"続けるにはホットイベントを選択してください。",
				"hint.sendSelectedEventToDraft":
					"選択したイベントとあなたの視点を Draft に送信します。",
				"error.profileNotReady":
					"プロフィールが準備できていません。先に取り込みを行ってください。",
				"error.invalidInput":
					"入力に誤りがあります。確認してもう一度お試しください。",
				"error.userNotAllowed":
					"このユーザーは許可されていません。管理者にお問い合わせください。",
				"error.serviceUnavailable":
					"サービスは一時的に利用できません。しばらくしてからもう一度お試しください。",
				"profile.usernameRequired": "ユーザー名は必須です。",
				"profile.loading": "プロフィールを読み込み中...",
				"profile.notFound":
					"プロフィールが見つかりません。取り込みを押してポストを取得し、ペルソナを作成してください。",
				"profile.personaMissing":
					"プロフィールは読み込まれましたが、ペルソナがありません。取り込みを押してペルソナを作成してください。",
				"profile.cardTitle": "プロフィール",
				"profile.followers": "フォロワー",
				"profile.following": "フォロー中",
				"profile.tweets": "投稿",
				"profile.persona": "ペルソナ",
				"profile.personaReady": "準備完了",
				"profile.personaMissingStatus": "未作成",
				"profile.personaPortrait": "ペルソナ像",
				"profile.summary": "要約",
				"profile.voice": "文体",
				"profile.topics": "トピック",
				"profile.ingestSuccess":
					"{count} 件の投稿を取り込み、ペルソナを作成しました。",
			},
			ko: {
				"app.title": "FoxSpark",
				"app.titleNoProfile": "프로필을 불러오세요",
				"settings.apiPageTitle": "API 및 생성",
				"settings.apiGeneration": "API 및 생성",
				"settings.versionLabel": "버전",
				"settings.debugMode": "디버그 모드",
				"settings.productionMode": "프로덕션 모드",
				"settings.switchToPopup": "팝업으로 전환",
				"settings.switchToSidePanel": "사이드 패널로 전환",
				"settings.backToSettings": "설정으로 돌아가기",
				"settings.backToMainView": "메인 화면으로 돌아가기",
				"tab.profile": "프로필",
				"tab.draft": "초안",
				"tab.trending": "트렌딩",
				"section.result": "결과",
				"section.hotEvents24h": "24시간 핫이슈",
				"section.trendingResult": "트렌딩 결과",
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
				"action.generating": "생각 중",
				"action.clear": "지우기",
				"action.refreshHot": "새로고침",
				"action.sendToDraft": "Draft로 보내기",
				"action.select": "선택",
				"action.selected": "선택됨",
				"action.copy": "복사",
				"action.insert": "삽입",
				"action.showOriginal": "원문 보기",
				"action.showTranslation": "번역 보기",
				"action.showOriginalEvent": "이 이벤트 원문 보기",
				"action.showTranslationEvent": "이 이벤트 번역 보기",
				"action.showMore": "더 보기",
				"action.showLess": "접기",
				"hint.hotEventSelected":
					"이벤트가 선택되었습니다. 아래에 관점을 입력한 뒤 Generate를 누르세요.",
				"hint.selectHotEventBeforeGenerate":
					"계속하려면 먼저 핫 이벤트를 선택하세요.",
				"hint.sendSelectedEventToDraft":
					"선택한 이벤트와 당신의 관점을 Draft로 보냅니다.",
				"error.profileNotReady":
					"프로필이 준비되지 않았습니다. 먼저 수집을 실행하세요.",
				"error.invalidInput":
					"입력이 올바르지 않습니다. 확인 후 다시 시도해 주세요.",
				"error.userNotAllowed":
					"이 사용자는 허용되지 않았습니다. 관리자에게 문의하세요.",
				"error.serviceUnavailable":
					"서비스를 일시적으로 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.",
				"profile.usernameRequired": "사용자 이름은 필수입니다.",
				"profile.loading": "프로필을 불러오는 중...",
				"profile.notFound":
					"프로필을 찾을 수 없습니다. 수집을 눌러 게시물을 가져오고 페르소나를 생성하세요.",
				"profile.personaMissing":
					"프로필은 불러왔지만 페르소나가 없습니다. 수집을 눌러 페르소나를 생성하세요.",
				"profile.cardTitle": "프로필",
				"profile.followers": "팔로워",
				"profile.following": "팔로잉",
				"profile.tweets": "게시물",
				"profile.persona": "페르소나",
				"profile.personaReady": "준비됨",
				"profile.personaMissingStatus": "없음",
				"profile.personaPortrait": "페르소나 프로필",
				"profile.summary": "요약",
				"profile.voice": "톤",
				"profile.topics": "주제",
				"profile.ingestSuccess":
					"게시물 {count}개를 수집했고 페르소나가 준비되었습니다.",
			},
			es: {
				"app.title": "FoxSpark",
				"app.titleNoProfile": "Carga un perfil para empezar",
				"settings.apiPageTitle": "API y Generación",
				"settings.apiGeneration": "API y Generación",
				"settings.versionLabel": "Versión",
				"settings.debugMode": "Modo depuración",
				"settings.productionMode": "Modo producción",
				"settings.switchToPopup": "Cambiar a ventana emergente",
				"settings.switchToSidePanel": "Cambiar a panel lateral",
				"settings.backToSettings": "Volver a configuración",
				"settings.backToMainView": "Volver a la vista principal",
				"tab.profile": "Perfil",
				"tab.draft": "Borrador",
				"tab.trending": "Tendencias",
				"section.result": "Resultado",
				"section.hotEvents24h": "Eventos calientes 24h",
				"section.trendingResult": "Resultado de tendencias",
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
				"action.generating": "Pensando",
				"action.clear": "Limpiar",
				"action.refreshHot": "Actualizar",
				"action.sendToDraft": "Enviar a Draft",
				"action.select": "Seleccionar",
				"action.selected": "Seleccionado",
				"action.copy": "Copiar",
				"action.insert": "Insertar",
				"action.showOriginal": "Ver original",
				"action.showTranslation": "Ver traducción",
				"action.showOriginalEvent": "Ver original de este evento",
				"action.showTranslationEvent": "Ver versión traducida de este evento",
				"action.showMore": "ver más",
				"action.showLess": "ver menos",
				"hint.hotEventSelected":
					"Evento seleccionado - escribe tu perspectiva abajo y pulsa Generate.",
				"hint.selectHotEventBeforeGenerate":
					"Elige un evento caliente para continuar.",
				"hint.sendSelectedEventToDraft":
					"Enviaremos el evento seleccionado y tu opinión a Draft.",
				"error.profileNotReady": "El perfil no está listo. Ingiere primero.",
				"error.invalidInput": "Entrada no válida. Revisa e inténtalo de nuevo.",
				"error.userNotAllowed":
					"Este usuario no está autorizado. Contacta al administrador.",
				"error.serviceUnavailable":
					"El servicio no está disponible temporalmente. Inténtalo de nuevo más tarde.",
				"profile.usernameRequired": "El nombre de usuario es obligatorio.",
				"profile.loading": "Cargando perfil...",
				"profile.notFound":
					"No se encontró el perfil. Haz clic en Ingerir para obtener publicaciones y crear la persona.",
				"profile.personaMissing":
					"El perfil se cargó, pero falta la persona. Haz clic en Ingerir para crearla.",
				"profile.cardTitle": "Perfil",
				"profile.followers": "Seguidores",
				"profile.following": "Siguiendo",
				"profile.tweets": "Publicaciones",
				"profile.persona": "Persona",
				"profile.personaReady": "Lista",
				"profile.personaMissingStatus": "Falta",
				"profile.personaPortrait": "Retrato de la persona",
				"profile.summary": "Resumen",
				"profile.voice": "Voz",
				"profile.topics": "Temas",
				"profile.ingestSuccess":
					"Se ingirieron {count} publicaciones. La persona está lista.",
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
			DEFAULT_PUBLIC_ERROR_MESSAGE,
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
