from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


SUPPORTED_LLM_PROVIDERS = {"openai", "gemini"}


def load_dotenv(dotenv_path: str = ".env") -> None:
    path = Path(dotenv_path)
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        os.environ.setdefault(key, value)


def _parse_sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("DATABASE_URL must use sqlite:/// for this MVP")
    return Path(database_url[len(prefix) :]).expanduser()


def _normalize_llm_provider(provider: str) -> str:
    normalized = provider.strip().lower() or "openai"
    if normalized not in SUPPORTED_LLM_PROVIDERS:
        supported = ", ".join(sorted(SUPPORTED_LLM_PROVIDERS))
        raise ValueError(f"LLM_PROVIDER must be one of: {supported}")
    return normalized


@dataclass(frozen=True)
class Settings:
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings(
        app_env=os.getenv("APP_ENV", "development"),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./data/mvp.db"),
        twitter_data_url=os.getenv("TWITTER_DATA_URL", "http://52.76.50.165:8081"),
        twitter_data_proxy=os.getenv("TWITTER_DATA_PROXY", ""),
        llm_http_proxy=os.getenv("LLM_HTTP_PROXY", "http://192.168.1.199:9000"),
        llm_provider=os.getenv("LLM_PROVIDER", "openai"),
        openai_api_key=os.getenv("OPENAI_API_KEY", ""),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-2.0-flash"),
        gemini_base_url=os.getenv(
            "GEMINI_BASE_URL",
            "https://generativelanguage.googleapis.com/v1beta",
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file_path=os.getenv("LOG_FILE_PATH", "data/app.log"),
        log_max_body_chars=int(os.getenv("LOG_MAX_BODY_CHARS", "500")),
        log_enable_file=os.getenv("LOG_ENABLE_FILE", "true").strip().lower() in {"1", "true", "yes", "on"},
        llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "2")),
        llm_retry_backoff_seconds=float(os.getenv("LLM_RETRY_BACKOFF_SECONDS", "1.0")),
        llm_score_timeout_seconds=int(os.getenv("LLM_SCORE_TIMEOUT_SECONDS", "20")),
        request_timeout_seconds=int(os.getenv("REQUEST_TIMEOUT_SECONDS", "30")),
        similarity_threshold=float(os.getenv("SIMILARITY_THRESHOLD", "0.92")),
        persona_sample_size=int(os.getenv("PERSONA_SAMPLE_SIZE", "40")),
        web_enrichment_enabled=os.getenv("WEB_ENRICHMENT_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"},
        web_enrichment_timeout_seconds=float(os.getenv("WEB_ENRICHMENT_TIMEOUT_SECONDS", "8")),
        web_enrichment_max_items=int(os.getenv("WEB_ENRICHMENT_MAX_ITEMS", "12")),
        web_enrichment_recency_hours=int(os.getenv("WEB_ENRICHMENT_RECENCY_HOURS", "24")),
        max_ingest_tweets=int(os.getenv("MAX_INGEST_TWEETS", "100")),
        content_rewrite_max_rounds=int(os.getenv("CONTENT_REWRITE_MAX_ROUNDS", "3")),
        max_generation_attempts=int(os.getenv("MAX_GENERATION_ATTEMPTS", "3")),
        evaluation_max_workers=int(os.getenv("EVALUATION_MAX_WORKERS", "4")),
        variant_max_workers=int(os.getenv("VARIANT_MAX_WORKERS", "3")),
    )
