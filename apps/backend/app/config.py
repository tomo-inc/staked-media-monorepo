from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import Any, cast

from pydantic import BaseModel, Field

SUPPORTED_LLM_PROVIDERS = {"openai", "gemini"}
SUPPORTED_TRANSLATION_LANGUAGES = {"en", "zh-CN", "zh-TW", "ja", "ko", "es"}
RUNTIME_CONFIG_POINTER_PATH = Path("data/runtime-config-path.json")
_DEFAULT_BIND_HOST = "0.0.0.0"  # noqa: S104


class _StrictConfigModel(BaseModel):
    class Config:
        extra = "forbid"


class _ServerConfigModel(_StrictConfigModel):
    host: str = _DEFAULT_BIND_HOST
    port: int = 8000
    reload: bool = False


class _DatabaseConfigModel(_StrictConfigModel):
    url: str = "postgresql://postgres:postgres@localhost:5432/staked_media"


class _TwitterConfigModel(_StrictConfigModel):
    data_url: str = "http://52.76.50.165:8081"
    data_proxy: str = ""
    max_ingest_tweets: int = 100
    persona_sample_size: int = 40


class _OpenAIConfigModel(_StrictConfigModel):
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"


class _GeminiConfigModel(_StrictConfigModel):
    api_key: str = ""
    model: str = "gemini-2.0-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"


class _LLMConfigModel(_StrictConfigModel):
    provider: str = "openai"
    http_proxy: str = "http://192.168.1.199:9000"
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    score_timeout_seconds: int = 20
    request_timeout_seconds: int = 30
    openai: _OpenAIConfigModel = Field(default_factory=_OpenAIConfigModel)
    gemini: _GeminiConfigModel = Field(default_factory=_GeminiConfigModel)


class _LogConfigModel(_StrictConfigModel):
    level: str = "INFO"
    file_path: str = "data/app.log"
    max_body_chars: int = 500
    enable_file: bool = True


class _ContentConfigModel(_StrictConfigModel):
    similarity_threshold: float = 0.92
    rewrite_max_rounds: int = 3
    max_generation_attempts: int = 3
    evaluation_max_workers: int = 4
    variant_max_workers: int = 3


class _WebEnrichmentConfigModel(_StrictConfigModel):
    enabled: bool = True
    timeout_seconds: float = 8.0
    max_items: int = 12
    recency_hours: int = 24


class _HotEventsFusionConfigModel(_StrictConfigModel):
    source_weight_news: float = Field(1.0, ge=0.0)
    source_weight_tweet: float = Field(1.0, ge=0.0)
    tweet_weight_retweet: float = Field(1.5, ge=0.0)
    tweet_weight_like: float = Field(1.0, ge=0.0)
    tweet_weight_reply: float = Field(2.0, ge=0.0)
    tweet_weight_quote: float = Field(2.5, ge=0.0)
    tweet_follower_cap_k: float = Field(50.0, ge=0.0)
    time_decay_half_life_hours: float = Field(12.0, gt=0.0)
    max_heat_score: float = Field(100.0, gt=0.0)


class _HotEventsConfigModel(_StrictConfigModel):
    provider_6551_token: str = ""
    auto_refresh_interval_seconds: int = Field(300, ge=1)
    min_refresh_cooldown_seconds: int = Field(60, ge=0)
    pre_translate_languages: list[str] = Field(default_factory=lambda: ["zh-CN", "en"])
    fusion: _HotEventsFusionConfigModel = Field(default_factory=lambda: cast(Any, _HotEventsFusionConfigModel)())


class _RootConfigModel(_StrictConfigModel):
    app_env: str = "development"
    server: _ServerConfigModel = Field(default_factory=_ServerConfigModel)
    database: _DatabaseConfigModel = Field(default_factory=_DatabaseConfigModel)
    twitter: _TwitterConfigModel = Field(default_factory=_TwitterConfigModel)
    llm: _LLMConfigModel = Field(default_factory=_LLMConfigModel)
    log: _LogConfigModel = Field(default_factory=_LogConfigModel)
    content: _ContentConfigModel = Field(default_factory=_ContentConfigModel)
    web_enrichment: _WebEnrichmentConfigModel = Field(default_factory=_WebEnrichmentConfigModel)
    hot_events: _HotEventsConfigModel = Field(default_factory=lambda: cast(Any, _HotEventsConfigModel)())


def _normalize_llm_provider(provider: str) -> str:
    normalized = provider.strip().lower() or "openai"
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
        raise ValueError(f"`llm.provider` must be one of: {supported}")
    return normalized


def _normalize_translation_languages(values: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in values:
        value = str(raw_value or "").strip()
        if not value:
            continue
        if value not in SUPPORTED_TRANSLATION_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_TRANSLATION_LANGUAGES))
            raise ValueError(f"`hot_events.pre_translate_languages` must contain only supported languages: {supported}")
        if value in seen:
            continue
        seen.add(value)
        normalized.append(value)
    return normalized or ["zh-CN", "en"]


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _pop_legacy_str(values: dict[str, object], key: str) -> str:
    return str(values.pop(key))


def _pop_legacy_int(values: dict[str, object], key: str) -> int:
    value = values.pop(key)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        return int(value)
    raise TypeError(f"{key} must be int-compatible, got {type(value).__name__}")


def _pop_legacy_float(values: dict[str, object], key: str) -> float:
    value = values.pop(key)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        return float(value)
    raise TypeError(f"{key} must be float-compatible, got {type(value).__name__}")


def _pop_legacy_bool(values: dict[str, object], key: str) -> bool:
    return bool(values.pop(key))


@dataclass(frozen=True)
class ServerSettings:
    host: str = _DEFAULT_BIND_HOST
    port: int = 8000
    reload: bool = False


@dataclass(frozen=True)
class DatabaseSettings:
    url: str = "postgresql://postgres:postgres@localhost:5432/staked_media"


@dataclass(frozen=True)
class TwitterSettings:
    data_url: str = "http://52.76.50.165:8081"
    data_proxy: str = ""
    max_ingest_tweets: int = 100
    persona_sample_size: int = 40

    @property
    def data_proxies(self) -> dict[str, str] | None:
        if not self.data_proxy:
            return None
        return {"http": self.data_proxy, "https": self.data_proxy}


@dataclass(frozen=True)
class OpenAISettings:
    api_key: str = ""
    model: str = "gpt-4.1-mini"
    base_url: str = "https://api.openai.com/v1"


@dataclass(frozen=True)
class GeminiSettings:
    api_key: str = ""
    model: str = "gemini-2.0-flash"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"


@dataclass(frozen=True)
class LLMSettings:
    provider: str = "openai"
    http_proxy: str = "http://192.168.1.199:9000"
    max_retries: int = 2
    retry_backoff_seconds: float = 1.0
    score_timeout_seconds: int = 20
    request_timeout_seconds: int = 30
    openai: OpenAISettings = field(default_factory=OpenAISettings)
    gemini: GeminiSettings = field(default_factory=GeminiSettings)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider", _normalize_llm_provider(self.provider))

    @property
    def proxies(self) -> dict[str, str] | None:
        if not self.http_proxy:
            return None
        return {"http": self.http_proxy, "https": self.http_proxy}

    @property
    def selected_model(self) -> str:
        return self.gemini.model if self.provider == "gemini" else self.openai.model


@dataclass(frozen=True)
class LogSettings:
    level: str = "INFO"
    file_path: str = "data/app.log"
    max_body_chars: int = 500
    enable_file: bool = True


@dataclass(frozen=True)
class ContentSettings:
    similarity_threshold: float = 0.92
    rewrite_max_rounds: int = 3
    max_generation_attempts: int = 3
    evaluation_max_workers: int = 4
    variant_max_workers: int = 3


@dataclass(frozen=True)
class WebEnrichmentSettings:
    enabled: bool = True
    timeout_seconds: float = 8.0
    max_items: int = 12
    recency_hours: int = 24


@dataclass(frozen=True)
class HotEventsFusionSettings:
    source_weight_news: float = 1.0
    source_weight_tweet: float = 1.0
    tweet_weight_retweet: float = 1.5
    tweet_weight_like: float = 1.0
    tweet_weight_reply: float = 2.0
    tweet_weight_quote: float = 2.5
    tweet_follower_cap_k: float = 50.0
    time_decay_half_life_hours: float = 12.0
    max_heat_score: float = 100.0


@dataclass(frozen=True)
class HotEventsSettings:
    provider_6551_token: str = ""
    auto_refresh_interval_seconds: int = 300
    min_refresh_cooldown_seconds: int = 60
    pre_translate_languages: list[str] = field(default_factory=lambda: ["zh-CN", "en"])
    fusion: HotEventsFusionSettings = field(default_factory=HotEventsFusionSettings)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "pre_translate_languages",
            _normalize_translation_languages(list(self.pre_translate_languages)),
        )


@dataclass(frozen=True, init=False)
class Settings:
    app_env: str = "development"
    server: ServerSettings = field(default_factory=ServerSettings)
    database: DatabaseSettings = field(default_factory=DatabaseSettings)
    twitter: TwitterSettings = field(default_factory=TwitterSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    log: LogSettings = field(default_factory=LogSettings)
    content: ContentSettings = field(default_factory=ContentSettings)
    web_enrichment: WebEnrichmentSettings = field(default_factory=WebEnrichmentSettings)
    hot_events: HotEventsSettings = field(default_factory=HotEventsSettings)

    def __init__(
        self,
        *,
        app_env: str = "development",
        server: ServerSettings | None = None,
        database: DatabaseSettings | None = None,
        twitter: TwitterSettings | None = None,
        llm: LLMSettings | None = None,
        log: LogSettings | None = None,
        content: ContentSettings | None = None,
        web_enrichment: WebEnrichmentSettings | None = None,
        hot_events: HotEventsSettings | None = None,
        **legacy_kwargs: object,
    ) -> None:
        server_settings = server or ServerSettings()
        database_settings = database or DatabaseSettings()
        twitter_settings = twitter or TwitterSettings()
        llm_settings = llm or LLMSettings()
        log_settings = log or LogSettings()
        content_settings = content or ContentSettings()
        web_enrichment_settings = web_enrichment or WebEnrichmentSettings()
        hot_events_settings = hot_events or HotEventsSettings()

        if "database_url" in legacy_kwargs:
            database_settings = replace(database_settings, url=_pop_legacy_str(legacy_kwargs, "database_url"))
        if "twitter_data_url" in legacy_kwargs:
            twitter_settings = replace(twitter_settings, data_url=_pop_legacy_str(legacy_kwargs, "twitter_data_url"))
        if "twitter_data_proxy" in legacy_kwargs:
            twitter_settings = replace(
                twitter_settings,
                data_proxy=_pop_legacy_str(legacy_kwargs, "twitter_data_proxy"),
            )
        if "max_ingest_tweets" in legacy_kwargs:
            twitter_settings = replace(
                twitter_settings,
                max_ingest_tweets=_pop_legacy_int(legacy_kwargs, "max_ingest_tweets"),
            )
        if "persona_sample_size" in legacy_kwargs:
            twitter_settings = replace(
                twitter_settings,
                persona_sample_size=_pop_legacy_int(legacy_kwargs, "persona_sample_size"),
            )

        openai_settings = llm_settings.openai
        gemini_settings = llm_settings.gemini
        if "llm_provider" in legacy_kwargs:
            llm_settings = replace(llm_settings, provider=_pop_legacy_str(legacy_kwargs, "llm_provider"))
        if "llm_http_proxy" in legacy_kwargs:
            llm_settings = replace(llm_settings, http_proxy=_pop_legacy_str(legacy_kwargs, "llm_http_proxy"))
        if "llm_max_retries" in legacy_kwargs:
            llm_settings = replace(llm_settings, max_retries=_pop_legacy_int(legacy_kwargs, "llm_max_retries"))
        if "llm_retry_backoff_seconds" in legacy_kwargs:
            llm_settings = replace(
                llm_settings,
                retry_backoff_seconds=_pop_legacy_float(legacy_kwargs, "llm_retry_backoff_seconds"),
            )
        if "llm_score_timeout_seconds" in legacy_kwargs:
            llm_settings = replace(
                llm_settings,
                score_timeout_seconds=_pop_legacy_int(legacy_kwargs, "llm_score_timeout_seconds"),
            )
        if "request_timeout_seconds" in legacy_kwargs:
            llm_settings = replace(
                llm_settings,
                request_timeout_seconds=_pop_legacy_int(legacy_kwargs, "request_timeout_seconds"),
            )
        if "openai_api_key" in legacy_kwargs:
            openai_settings = replace(openai_settings, api_key=_pop_legacy_str(legacy_kwargs, "openai_api_key"))
        if "openai_model" in legacy_kwargs:
            openai_settings = replace(openai_settings, model=_pop_legacy_str(legacy_kwargs, "openai_model"))
        if "openai_base_url" in legacy_kwargs:
            openai_settings = replace(openai_settings, base_url=_pop_legacy_str(legacy_kwargs, "openai_base_url"))
        if "gemini_api_key" in legacy_kwargs:
            gemini_settings = replace(gemini_settings, api_key=_pop_legacy_str(legacy_kwargs, "gemini_api_key"))
        if "gemini_model" in legacy_kwargs:
            gemini_settings = replace(gemini_settings, model=_pop_legacy_str(legacy_kwargs, "gemini_model"))
        if "gemini_base_url" in legacy_kwargs:
            gemini_settings = replace(gemini_settings, base_url=_pop_legacy_str(legacy_kwargs, "gemini_base_url"))
        llm_settings = replace(llm_settings, openai=openai_settings, gemini=gemini_settings)

        if "log_level" in legacy_kwargs:
            log_settings = replace(log_settings, level=_pop_legacy_str(legacy_kwargs, "log_level"))
        if "log_file_path" in legacy_kwargs:
            log_settings = replace(log_settings, file_path=_pop_legacy_str(legacy_kwargs, "log_file_path"))
        if "log_max_body_chars" in legacy_kwargs:
            log_settings = replace(log_settings, max_body_chars=_pop_legacy_int(legacy_kwargs, "log_max_body_chars"))
        if "log_enable_file" in legacy_kwargs:
            log_settings = replace(log_settings, enable_file=_pop_legacy_bool(legacy_kwargs, "log_enable_file"))

        if "similarity_threshold" in legacy_kwargs:
            content_settings = replace(
                content_settings,
                similarity_threshold=_pop_legacy_float(legacy_kwargs, "similarity_threshold"),
            )
        if "content_rewrite_max_rounds" in legacy_kwargs:
            content_settings = replace(
                content_settings,
                rewrite_max_rounds=_pop_legacy_int(legacy_kwargs, "content_rewrite_max_rounds"),
            )
        if "max_generation_attempts" in legacy_kwargs:
            content_settings = replace(
                content_settings,
                max_generation_attempts=_pop_legacy_int(legacy_kwargs, "max_generation_attempts"),
            )
        if "evaluation_max_workers" in legacy_kwargs:
            content_settings = replace(
                content_settings,
                evaluation_max_workers=_pop_legacy_int(legacy_kwargs, "evaluation_max_workers"),
            )
        if "variant_max_workers" in legacy_kwargs:
            content_settings = replace(
                content_settings,
                variant_max_workers=_pop_legacy_int(legacy_kwargs, "variant_max_workers"),
            )

        if "web_enrichment_enabled" in legacy_kwargs:
            web_enrichment_settings = replace(
                web_enrichment_settings,
                enabled=_pop_legacy_bool(legacy_kwargs, "web_enrichment_enabled"),
            )
        if "web_enrichment_timeout_seconds" in legacy_kwargs:
            web_enrichment_settings = replace(
                web_enrichment_settings,
                timeout_seconds=_pop_legacy_float(legacy_kwargs, "web_enrichment_timeout_seconds"),
            )
        if "web_enrichment_max_items" in legacy_kwargs:
            web_enrichment_settings = replace(
                web_enrichment_settings,
                max_items=_pop_legacy_int(legacy_kwargs, "web_enrichment_max_items"),
            )
        if "web_enrichment_recency_hours" in legacy_kwargs:
            web_enrichment_settings = replace(
                web_enrichment_settings,
                recency_hours=_pop_legacy_int(legacy_kwargs, "web_enrichment_recency_hours"),
            )

        fusion_settings = hot_events_settings.fusion
        if "provider_6551_token" in legacy_kwargs:
            hot_events_settings = replace(
                hot_events_settings,
                provider_6551_token=_pop_legacy_str(legacy_kwargs, "provider_6551_token"),
            )
        if "hot_events_refresh_interval_seconds" in legacy_kwargs:
            hot_events_settings = replace(
                hot_events_settings,
                auto_refresh_interval_seconds=_pop_legacy_int(
                    legacy_kwargs,
                    "hot_events_refresh_interval_seconds",
                ),
            )
        if "hot_events_fusion" in legacy_kwargs:
            hot_events_fusion = legacy_kwargs.pop("hot_events_fusion")
            if isinstance(hot_events_fusion, HotEventsFusionSettings):
                fusion_settings = hot_events_fusion
            elif isinstance(hot_events_fusion, dict):
                fusion_settings = HotEventsFusionSettings(**hot_events_fusion)
            else:
                raise TypeError("hot_events_fusion must be a dict or HotEventsFusionSettings")
        hot_events_settings = replace(hot_events_settings, fusion=fusion_settings)

        if legacy_kwargs:
            unknown_keys = ", ".join(sorted(str(key) for key in legacy_kwargs))
            raise TypeError(f"Unknown Settings fields: {unknown_keys}")

        object.__setattr__(self, "app_env", app_env)
        object.__setattr__(self, "server", server_settings)
        object.__setattr__(self, "database", database_settings)
        object.__setattr__(self, "twitter", twitter_settings)
        object.__setattr__(self, "llm", llm_settings)
        object.__setattr__(self, "log", log_settings)
        object.__setattr__(self, "content", content_settings)
        object.__setattr__(self, "web_enrichment", web_enrichment_settings)
        object.__setattr__(self, "hot_events", hot_events_settings)

    @property
    def max_ingest_tweets(self) -> int:
        return self.twitter.max_ingest_tweets

    @property
    def persona_sample_size(self) -> int:
        return self.twitter.persona_sample_size

    @property
    def twitter_data_url(self) -> str:
        return self.twitter.data_url

    @property
    def twitter_data_proxy(self) -> str:
        return self.twitter.data_proxy

    @property
    def twitter_data_proxies(self) -> dict[str, str] | None:
        return self.twitter.data_proxies

    @property
    def provider_6551_token(self) -> str:
        return self.hot_events.provider_6551_token

    @property
    def llm_http_proxy(self) -> str:
        return self.llm.http_proxy

    @property
    def llm_provider(self) -> str:
        return self.llm.provider

    @property
    def openai_api_key(self) -> str:
        return self.llm.openai.api_key

    @property
    def openai_model(self) -> str:
        return self.llm.openai.model

    @property
    def openai_base_url(self) -> str:
        return self.llm.openai.base_url

    @property
    def gemini_api_key(self) -> str:
        return self.llm.gemini.api_key

    @property
    def gemini_model(self) -> str:
        return self.llm.gemini.model

    @property
    def gemini_base_url(self) -> str:
        return self.llm.gemini.base_url

    @property
    def llm_max_retries(self) -> int:
        return self.llm.max_retries

    @property
    def llm_retry_backoff_seconds(self) -> float:
        return self.llm.retry_backoff_seconds

    @property
    def llm_score_timeout_seconds(self) -> int:
        return self.llm.score_timeout_seconds

    @property
    def request_timeout_seconds(self) -> int:
        return self.llm.request_timeout_seconds

    @property
    def llm_proxies(self) -> dict[str, str] | None:
        return self.llm.proxies

    @property
    def log_level(self) -> str:
        return self.log.level

    @property
    def log_file_path(self) -> str:
        return self.log.file_path

    @property
    def log_max_body_chars(self) -> int:
        return self.log.max_body_chars

    @property
    def log_enable_file(self) -> bool:
        return self.log.enable_file

    @property
    def similarity_threshold(self) -> float:
        return self.content.similarity_threshold

    @property
    def content_rewrite_max_rounds(self) -> int:
        return self.content.rewrite_max_rounds

    @property
    def max_generation_attempts(self) -> int:
        return self.content.max_generation_attempts

    @property
    def evaluation_max_workers(self) -> int:
        return self.content.evaluation_max_workers

    @property
    def variant_max_workers(self) -> int:
        return self.content.variant_max_workers

    @property
    def web_enrichment_enabled(self) -> bool:
        return self.web_enrichment.enabled

    @property
    def web_enrichment_timeout_seconds(self) -> float:
        return self.web_enrichment.timeout_seconds

    @property
    def web_enrichment_max_items(self) -> int:
        return self.web_enrichment.max_items

    @property
    def web_enrichment_recency_hours(self) -> int:
        return self.web_enrichment.recency_hours

    @property
    def hot_events_refresh_interval_seconds(self) -> int:
        return self.hot_events.auto_refresh_interval_seconds

    @property
    def hot_events_fusion(self) -> HotEventsFusionSettings:
        return self.hot_events.fusion


@dataclass(frozen=True)
class LoadedConfig:
    config_path: Path
    app: Settings

    @property
    def server(self) -> ServerSettings:
        return self.app.server


def _build_settings(parsed: _RootConfigModel, *, base_dir: Path) -> Settings:
    database = DatabaseSettings(url=str(parsed.database.url).strip())
    log = LogSettings(
        level=parsed.log.level,
        file_path=str(_resolve_path(parsed.log.file_path, base_dir=base_dir)),
        max_body_chars=parsed.log.max_body_chars,
        enable_file=parsed.log.enable_file,
    )
    return Settings(
        app_env=parsed.app_env,
        server=ServerSettings(**parsed.server.dict()),
        database=database,
        twitter=TwitterSettings(**parsed.twitter.dict()),
        llm=LLMSettings(
            provider=parsed.llm.provider,
            http_proxy=parsed.llm.http_proxy,
            max_retries=parsed.llm.max_retries,
            retry_backoff_seconds=parsed.llm.retry_backoff_seconds,
            score_timeout_seconds=parsed.llm.score_timeout_seconds,
            request_timeout_seconds=parsed.llm.request_timeout_seconds,
            openai=OpenAISettings(**parsed.llm.openai.dict()),
            gemini=GeminiSettings(**parsed.llm.gemini.dict()),
        ),
        log=log,
        content=ContentSettings(**parsed.content.dict()),
        web_enrichment=WebEnrichmentSettings(**parsed.web_enrichment.dict()),
        hot_events=HotEventsSettings(
            provider_6551_token=parsed.hot_events.provider_6551_token,
            auto_refresh_interval_seconds=parsed.hot_events.auto_refresh_interval_seconds,
            min_refresh_cooldown_seconds=parsed.hot_events.min_refresh_cooldown_seconds,
            pre_translate_languages=list(parsed.hot_events.pre_translate_languages),
            fusion=HotEventsFusionSettings(**parsed.hot_events.fusion.dict()),
        ),
    )


@cache
def _load_config_file_cached(config_path: str) -> LoadedConfig:
    resolved_path = Path(config_path).expanduser().resolve()
    if not resolved_path.exists():
        raise FileNotFoundError(f"Config file not found: {resolved_path}")

    try:
        payload = json.loads(resolved_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config file {resolved_path} contains invalid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise ValueError(f"Config file {resolved_path} must contain a JSON object at the top level")

    parsed = _RootConfigModel.parse_obj(payload)
    return LoadedConfig(
        config_path=resolved_path,
        app=_build_settings(parsed, base_dir=resolved_path.parent),
    )


def load_config_file(config_path: str | Path) -> LoadedConfig:
    return _load_config_file_cached(str(Path(config_path).expanduser().resolve()))


def clear_config_cache() -> None:
    _load_config_file_cached.cache_clear()


def set_runtime_config_path(
    config_path: str | Path,
    *,
    runtime_config_path: str | Path = RUNTIME_CONFIG_POINTER_PATH,
) -> Path:
    resolved_config_path = Path(config_path).expanduser().resolve()
    runtime_path = Path(runtime_config_path).expanduser()
    runtime_path.parent.mkdir(parents=True, exist_ok=True)
    runtime_path.write_text(
        json.dumps({"config_path": str(resolved_config_path)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return runtime_path


def get_runtime_config_path(
    *,
    runtime_config_path: str | Path = RUNTIME_CONFIG_POINTER_PATH,
) -> Path:
    runtime_path = Path(runtime_config_path).expanduser()
    if not runtime_path.exists():
        raise RuntimeError(
            "Runtime config pointer is not initialized. "
            "Start the app with `uv run python -m app.run -c <path-to-config.json>`."
        )

    try:
        payload = json.loads(runtime_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Runtime config pointer {runtime_path} contains invalid JSON: {exc}") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("config_path"), str):
        raise RuntimeError(f"Runtime config pointer {runtime_path} is missing a valid `config_path` entry")

    return Path(payload["config_path"]).expanduser().resolve()


def get_settings(config_path: str | Path | None = None) -> Settings:
    resolved_config_path = config_path if config_path is not None else get_runtime_config_path()
    return load_config_file(resolved_config_path).app


def get_server_settings(config_path: str | Path | None = None) -> ServerSettings:
    resolved_config_path = config_path if config_path is not None else get_runtime_config_path()
    return load_config_file(resolved_config_path).server
