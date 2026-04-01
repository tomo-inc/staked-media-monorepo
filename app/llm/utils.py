from __future__ import annotations

import json
import logging
import re
from typing import Any

from app.logging_utils import get_logger, log_event, redact_for_log
from app.persona import clean_text

from .errors import LLMError


GENERATION_GUARDRAIL_KEYS = (
    "preferred_openings",
    "preferred_formats",
    "compression_rules",
    "anti_patterns",
    "language_notes",
)
TARGET_DRAFT_SCORE = 9.0
MIN_RULE_SCORE_FOR_LLM_REVIEW = 7.0


logger = get_logger(__name__)


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if clean_text(str(item))]
    if isinstance(value, str):
        text = clean_text(value)
        return [text] if text else []
    text = clean_text(str(value))
    return [text] if text else []


def _normalize_generation_guardrails(value: Any) -> dict[str, list[str]]:
    if not value:
        return {}

    normalized = {key: [] for key in GENERATION_GUARDRAIL_KEYS}
    if isinstance(value, dict):
        for key in GENERATION_GUARDRAIL_KEYS:
            normalized[key] = _as_string_list(value.get(key))
    else:
        normalized["anti_patterns"] = _as_string_list(value)

    return {key: items for key, items in normalized.items() if items}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _coerce_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict):
                parts.append(str(chunk.get("text", "")))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content or "")


def _parse_json_response(
    content: str,
    *,
    provider_name: str,
    request_id: str | None = None,
    max_body_chars: int = 500,
) -> dict[str, Any]:
    candidates: list[tuple[str, str]] = [("raw", content)]
    fenced_content = _strip_json_fence(content)
    if fenced_content and fenced_content != content:
        candidates.append(("fence_stripped", fenced_content))

    extracted_candidates: list[tuple[str, str]] = []
    for strategy, candidate_text in candidates:
        extracted = _extract_first_json_value(candidate_text)
        if extracted and extracted != candidate_text:
            extracted_candidates.append((f"{strategy}_extracted", extracted))
    candidates.extend(extracted_candidates)

    seen_texts: set[str] = set()
    last_error: json.JSONDecodeError | None = None
    for strategy, candidate_text in candidates:
        if candidate_text in seen_texts:
            continue
        seen_texts.add(candidate_text)
        try:
            payload = json.loads(candidate_text)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        log_event(
            logger,
            logging.INFO,
            "llm_provider_json_parsed",
            request_id=request_id,
            provider=provider_name.lower(),
            payload_type=type(payload).__name__,
            parse_strategy=strategy,
        )
        return payload

    exc = last_error or json.JSONDecodeError("Could not parse JSON", content, 0)
    log_event(
        logger,
        logging.WARNING,
        "llm_provider_invalid_json",
        request_id=request_id,
        provider=provider_name.lower(),
        response_snippet=redact_for_log(content, max_body_chars),
    )
    raise LLMError(f"{provider_name} returned invalid JSON: {content[:500]}") from exc


def _strip_json_fence(content: str) -> str | None:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    stripped = match.group(1).strip()
    if stripped.lower().startswith("json\n"):
        stripped = stripped[5:].strip()
    return stripped or None


def _extract_first_json_value(content: str) -> str | None:
    start = None
    opening_char = ""
    for index, char in enumerate(content):
        if char in "[{":
            start = index
            opening_char = char
            break
    if start is None:
        return None

    stack = ["]" if opening_char == "[" else "}"]
    in_string = False
    escaped = False

    for index in range(start + 1, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            stack.append("}")
            continue
        if char == "[":
            stack.append("]")
            continue
        if char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return content[start : index + 1]

    return None
