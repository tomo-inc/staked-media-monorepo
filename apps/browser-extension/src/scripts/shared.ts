(function (globalRoot, factory) {
  const api = factory();
  globalRoot.StakedMediaExtensionShared = api;
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
})(typeof globalThis !== "undefined" ? (globalThis as any) : (this as any), function () {
  const FALLBACK_BACKEND_BASE_URL = "https://api.sayviner.top:8443";

  const ALLOWED_BACKEND_HOSTS: ReadonlySet<string> = new Set([
    "127.0.0.1",
    "localhost",
    "api.sayviner.top"
  ]);

  type ThemeMode = "light" | "dark" | "system";
  type ApiMode = "content" | "drafts";
  type HostMode = "sidepanel" | "popup";

  interface ExtensionConfig {
    defaultUsername: string;
    backendBaseUrl: string;
    apiMode: ApiMode;
    theme: ThemeMode;
    hostMode: HostMode;
  }

  interface NormalizeOptions {
    strictBackendBaseUrl?: boolean;
  }

  interface RuntimeErrorWithStatus extends Error {
    status?: number;
    payload?: unknown;
  }

  interface RuntimeResponse<T = unknown> {
    ok?: boolean;
    error?: {
      message?: string;
      status?: number;
      payload?: unknown;
    };
  }

  const DEFAULT_CONFIG: Readonly<ExtensionConfig> = Object.freeze({
    defaultUsername: "",
    backendBaseUrl: FALLBACK_BACKEND_BASE_URL,
    apiMode: "content",
    theme: "light",
    hostMode: "sidepanel"
  });

  function normalizeBaseUrl(value: unknown): string {
    return String(value || "").trim().replace(/\/+$/, "");
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

  function normalizeBackendBaseUrl(value: unknown, options?: NormalizeOptions): string {
    const strictBackendBaseUrl = Boolean(options?.strictBackendBaseUrl);
    const candidate = normalizeBaseUrl(value || FALLBACK_BACKEND_BASE_URL) || FALLBACK_BACKEND_BASE_URL;

    try {
      const parsed = new URL(candidate);
      if (!/^https?:$/.test(parsed.protocol)) {
        throw new Error("Unsupported backend protocol");
      }
      if (parsed.username || parsed.password) {
        throw new Error("Backend URL credentials are not supported");
      }
      if (!ALLOWED_BACKEND_HOSTS.has(parsed.hostname)) {
        throw new Error(`Backend host "${parsed.hostname}" is not in the allowed list. Allowed: ${[...ALLOWED_BACKEND_HOSTS].join(", ")}`);
      }
      const normalizedPath = parsed.pathname && parsed.pathname !== "/" ? parsed.pathname.replace(/\/+$/, "") : "";
      return `${parsed.protocol}//${parsed.host}${normalizedPath}`;
    } catch (_error) {
      if (strictBackendBaseUrl) {
        throw new Error("Backend URL must be a valid http(s) URL pointing to an allowed host.");
      }
      return FALLBACK_BACKEND_BASE_URL;
    }
  }

  function sanitizeConfig(config: Partial<ExtensionConfig> | null | undefined, options?: NormalizeOptions): ExtensionConfig {
    const merged = { ...DEFAULT_CONFIG, ...(config || {}) };
    return {
      defaultUsername: typeof merged.defaultUsername === "string" ? merged.defaultUsername.trim() : "",
      backendBaseUrl: normalizeBackendBaseUrl(merged.backendBaseUrl, options),
      apiMode: normalizeApiMode(merged.apiMode),
      theme: normalizeTheme(merged.theme),
      hostMode: normalizeHostMode(merged.hostMode)
    };
  }

  async function routeMessage<TPayload = unknown, TResult = unknown>(
    message: { type?: string; payload?: TPayload } | null | undefined,
    handlers: Record<string, (payload: TPayload, rawMessage: unknown) => Promise<TResult> | TResult>
  ): Promise<TResult> {
    const type = String(message?.type || "");
    const handler = handlers?.[type];
    if (typeof handler !== "function") {
      throw new Error(`Unsupported message type: ${type}`);
    }
    return handler((message?.payload || ({} as TPayload)) as TPayload, message);
  }

  function extractDrafts(result: any): Array<{ text?: string } & Record<string, unknown>> {
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
    if (Array.isArray(result.formatted_drafts) && result.formatted_drafts.length) {
      return result.formatted_drafts.map((text: string) => ({ text }));
    }
    return [];
  }

  function escapeHtml(value: unknown): string {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function coerceWindowId(value: unknown): number | null {
    const parsed = Number.parseInt(String(value), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }

  function sendRuntimeMessage<TResponse = unknown>(message: unknown): Promise<TResponse> {
    return new Promise((resolve, reject) => {
      (chrome as any).runtime.sendMessage(message, (response: RuntimeResponse<TResponse> & TResponse) => {
        const runtimeError = (chrome as any).runtime.lastError;
        if (runtimeError) {
          reject(new Error(runtimeError.message));
          return;
        }
        if (!response?.ok) {
          const error = new Error(response?.error?.message || "Request failed") as RuntimeErrorWithStatus;
          if (response?.error?.status) {
            error.status = response.error.status;
          }
          if (response?.error?.payload) {
            error.payload = response.error.payload;
          }
          reject(error);
          return;
        }
        resolve(response as TResponse);
      });
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
    routeMessage,
    sanitizeConfig,
    sendRuntimeMessage
  };
});
