from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


SUPPORTED_LLM_PROVIDERS = {"openai", "gemini"}
RUNTIME_CONFIG_POINTER_PATH = Path("data/runtime-config-path.json")


class _StrictConfigModel(BaseModel):
    class Config:
        extra = "forbid"


class _ServerConfigModel(_StrictConfigModel):
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


class _AppConfigModel(_StrictConfigModel):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/mvp.db"
    twitter_data_url: str = "http://52.76.50.165:8081"
    twitter_data_proxy: str = ""
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


class _RootConfigModel(_StrictConfigModel):
    server: _ServerConfigModel = Field(default_factory=_ServerConfigModel)
    app: _AppConfigModel = Field(default_factory=_AppConfigModel)


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
    host: str = "0.0.0.0"
    port: int = 8000
    reload: bool = False


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    database_url: str = "sqlite:///./data/mvp.db"
    twitter_data_url: str = "http://52.76.50.165:8081"
    twitter_data_proxy: str = ""
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

    def __post_init__(self) -> None:
        object.__setattr__(self, "llm_provider", _normalize_llm_provider(self.llm_provider))

    @property
    def database_path(self) -> Path:
        return _parse_sqlite_path(self.database_url)

    @property
    def twitter_data_proxies(self) -> Optional[dict[str, str]]:
        if not self.twitter_data_proxy:
            return None
        return {"http": self.twitter_data_proxy, "https": self.twitter_data_proxy}

    @property
    def llm_proxies(self) -> Optional[dict[str, str]]:
        if not self.llm_http_proxy:
            return None
        return {"http": self.llm_http_proxy, "https": self.llm_http_proxy}


@dataclass(frozen=True)
class LoadedConfig:
    config_path: Path
    server: ServerSettings
    app: Settings


@lru_cache(maxsize=None)
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
