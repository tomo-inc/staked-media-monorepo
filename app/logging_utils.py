from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

from app.config import Settings


_LOGGER_SIGNATURE: tuple[str, str, bool] | None = None


def configure_logging(settings: Settings) -> None:
    global _LOGGER_SIGNATURE

    signature = (
        settings.log_level.upper(),
        settings.log_file_path,
        settings.log_enable_file,
    )
    logger = logging.getLogger("app")
    if _LOGGER_SIGNATURE == signature and logger.handlers:
        return

    logger.setLevel(_resolve_log_level(settings.log_level))
    logger.propagate = False

    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(logger.level)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    if settings.log_enable_file:
        log_path = Path(settings.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logger.level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    _LOGGER_SIGNATURE = signature


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def format_log_event(event: str, **fields: Any) -> str:
    payload = {"event": event}
    for key, value in fields.items():
        if value is None:
            continue
        payload[key] = _coerce_log_value(value)
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def log_event(logger: logging.Logger, level: int, event: str, **fields: Any) -> None:
    logger.log(level, format_log_event(event, **fields))


def redact_for_log(value: Any, max_chars: int) -> str:
    text = str(value or "").replace("\n", "\\n")
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return text[:max_chars]
    return f"{text[: max_chars - 3]}..."


def _resolve_log_level(level_name: str) -> int:
    return getattr(logging, level_name.strip().upper(), logging.INFO)


def _coerce_log_value(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [_coerce_log_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _coerce_log_value(item) for key, item in value.items()}
    return str(value)
