from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

from pydantic import BaseModel, Field

SUPPORTED_LLM_PROVIDERS = {"openai", "gemini"}
RUNTIME_CONFIG_POINTER_PATH = Path("data/runtime-config-path.json")
_DEFAULT_BIND_HOST = "0.0.0.0"  # noqa: S104


class _StrictConfigModel(BaseModel):
    class Config:
        extra = "forbid"


class _ServerConfigModel(_StrictConfigModel):
    host: str = _DEFAULT_BIND_HOST
    port: int = 8000
    reload: bool = False


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


def _default_hot_events_fusion_config() -> _HotEventsFusionConfigModel:
    return _HotEventsFusionConfigModel.parse_obj({})


def _default_app_config_model() -> _AppConfigModel:
    return _AppConfigModel.parse_obj({})


class _AppConfigModel(_StrictConfigModel):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/mvp.db"
    twitter_data_url: str = "http://52.76.50.165:8081"
    twitter_data_proxy: str = ""
    provider_6551_token: str = ""
    llm_http_proxy: str = "http://192.168.1.199:9000"
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    log_level: str = "INFO"
    log_file_path: str = "data/app.log"
    log_max_body_chars: int = 500
    log_enable_file: bool = True
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.0
    llm_score_timeout_seconds: int = 20
    request_timeout_seconds: int = 30
    similarity_threshold: float = 0.92
    persona_sample_size: int = 40
    web_enrichment_enabled: bool = True
    web_enrichment_timeout_seconds: float = 8.0
    web_enrichment_max_items: int = 12
    web_enrichment_recency_hours: int = 24
    max_ingest_tweets: int = 100
    content_rewrite_max_rounds: int = 3
    max_generation_attempts: int = 3
    evaluation_max_workers: int = 4
    variant_max_workers: int = 3
    hot_events_refresh_interval_seconds: int = Field(3600, ge=1)
    hot_events_fusion: _HotEventsFusionConfigModel = Field(default_factory=_default_hot_events_fusion_config)


class _RootConfigModel(_StrictConfigModel):
    server: _ServerConfigModel = Field(default_factory=_ServerConfigModel)
    app: _AppConfigModel = Field(default_factory=_default_app_config_model)


def _parse_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("`database_url` must use sqlite:/// for this MVP")
    return Path(database_url[len(prefix) :]).expanduser()


def _normalize_llm_provider(provider: str) -> str:
    normalized = provider.strip().lower() or "openai"
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
        raise ValueError(f"`llm_provider` must be one of: {supported}")
    return normalized


def _resolve_path(value: str, *, base_dir: Path) -> Path:
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return path


def _resolve_sqlite_url(database_url: str, *, base_dir: Path) -> str:
    path = _parse_sqlite_path(database_url)
    if not path.is_absolute():
        path = (base_dir / path).resolve()
    return f"sqlite:///{path.as_posix()}"


@dataclass(frozen=True)
class ServerSettings:
    host: str = _DEFAULT_BIND_HOST
    port: int = 8000
    reload: bool = False


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
class Settings:
    app_env: str = "development"
    database_url: str = "sqlite:///./data/mvp.db"
    twitter_data_url: str = "http://52.76.50.165:8081"
    twitter_data_proxy: str = ""
    provider_6551_token: str = ""
    llm_http_proxy: str = "http://192.168.1.199:9000"
    llm_provider: str = "openai"
    openai_api_key: str = ""
    openai_model: str = "gpt-4.1-mini"
    openai_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    log_level: str = "INFO"
    log_file_path: str = "data/app.log"
    log_max_body_chars: int = 500
    log_enable_file: bool = True
    llm_max_retries: int = 2
    llm_retry_backoff_seconds: float = 1.0
    llm_score_timeout_seconds: int = 20
    request_timeout_seconds: int = 30
    similarity_threshold: float = 0.92
    persona_sample_size: int = 40
    web_enrichment_enabled: bool = True
    web_enrichment_timeout_seconds: float = 8.0
    web_enrichment_max_items: int = 12
    web_enrichment_recency_hours: int = 24
    max_ingest_tweets: int = 100
    content_rewrite_max_rounds: int = 3
    max_generation_attempts: int = 3
    evaluation_max_workers: int = 4
    variant_max_workers: int = 3
    hot_events_refresh_interval_seconds: int = 3600
    hot_events_fusion: HotEventsFusionSettings = field(default_factory=HotEventsFusionSettings)

    def __post_init__(self) -> None:
        object.__setattr__(self, "llm_provider", _normalize_llm_provider(self.llm_provider))

    @property
    def database_path(self) -> Path:
        return _parse_sqlite_path(self.database_url)

    @property
    def twitter_data_proxies(self) -> dict[str, str] | None:
        if not self.twitter_data_proxy:
            return None
        return {"http": self.twitter_data_proxy, "https": self.twitter_data_proxy}

    @property
    def llm_proxies(self) -> dict[str, str] | None:
        if not self.llm_http_proxy:
            return None
        return {"http": self.llm_http_proxy, "https": self.llm_http_proxy}


@dataclass(frozen=True)
class LoadedConfig:
    config_path: Path
    server: ServerSettings
    app: Settings


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
    base_dir = resolved_path.parent
    app_payload = parsed.app.dict()
    app_payload["database_url"] = _resolve_sqlite_url(app_payload["database_url"], base_dir=base_dir)
    app_payload["log_file_path"] = str(_resolve_path(app_payload["log_file_path"], base_dir=base_dir))
    fusion_payload = app_payload.get("hot_events_fusion") or {}
    if isinstance(fusion_payload, dict):
        app_payload["hot_events_fusion"] = HotEventsFusionSettings(**fusion_payload)
    else:
        raise ValueError("`app.hot_events_fusion` must be a JSON object")

    return LoadedConfig(
        config_path=resolved_path,
        server=ServerSettings(**parsed.server.dict()),
        app=Settings(**app_payload),
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
            "Runtime config pointer is not initialized. Start the app with `python -m app.run -c config.json`."
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
