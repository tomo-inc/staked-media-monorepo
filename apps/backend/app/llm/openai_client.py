from __future__ import annotations

import logging
import re
from typing import Any

from app.config import Settings
from app.logging_utils import get_logger, log_event

from .base_client import LLMClient
from .errors import LLMError
from .utils import _coerce_content_text, _parse_json_response

logger = get_logger(__name__)


class OpenAIClient(LLMClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, provider_name="openai")

    @staticmethod
    def _ensure_json_instruction(system_prompt: str) -> str:
        if "json" in system_prompt.lower():
            return system_prompt
        return f"{system_prompt.rstrip()}\n\nReturn a valid JSON object only."

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_id: str | None = None,
        purpose: str = "generation",
        timeout_seconds: float | None = None,
    ) -> Any:
        if not self.settings.llm.openai.api_key:
            raise LLMError("OpenAI API key is not configured")

        endpoint = f"{self.settings.llm.openai.base_url.rstrip('/')}/chat/completions"
        normalized_system_prompt = self._ensure_json_instruction(system_prompt)
        headers = {
            "Authorization": f"Bearer {self.settings.llm.openai.api_key}",
            "Content-Type": "application/json",
        }
        base_payload = {
            "model": self.settings.llm.openai.model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": normalized_system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        content_text = ""
        for use_json_mode in (True, False):
            json_payload = dict(base_payload)
            if use_json_mode:
                json_payload["response_format"] = {"type": "json_object"}

            try:
                body = self._post_json_with_retries(
                    endpoint=endpoint,
                    headers=headers,
                    json_payload=json_payload,
                    model=self.settings.llm.openai.model,
                    request_id=request_id,
                    purpose=purpose,
                    timeout_seconds=timeout_seconds,
                )
            except LLMError as exc:
                message = str(exc).lower()
                if use_json_mode and ("json_object" in message or "text.format" in message):
                    log_event(
                        logger,
                        logging.WARNING,
                        "llm_provider_json_mode_fallback",
                        request_id=request_id,
                        provider=self.provider_name,
                        model=self.settings.llm.openai.model,
                        reason="response_format_unsupported",
                    )
                    continue
                raise

            choices = body.get("choices") or []
            if not choices:
                log_event(
                    logger,
                    logging.ERROR,
                    "llm_provider_missing_choices",
                    request_id=request_id,
                    provider=self.provider_name,
                    model=self.settings.llm.openai.model,
                )
                raise LLMError("OpenAI response did not include any choices")

            content = choices[0].get("message", {}).get("content", "")
            content_text = _coerce_content_text(content)
            if content_text:
                break
            if use_json_mode:
                log_event(
                    logger,
                    logging.WARNING,
                    "llm_provider_json_mode_fallback",
                    request_id=request_id,
                    provider=self.provider_name,
                    model=self.settings.llm.openai.model,
                    reason="empty_content",
                )

        if not content_text:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_empty_content",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.llm.openai.model,
            )
            raise LLMError("OpenAI response content was empty")

        try:
            return _parse_json_response(
                content_text,
                provider_name="OpenAI",
                request_id=request_id,
                max_body_chars=self.settings.log.max_body_chars,
            )
        except LLMError:
            recovered_payload = None
            if purpose == "draft_generation":
                recovered_payload = self._recover_plaintext_drafts(content_text)
            if not recovered_payload:
                raise
            log_event(
                logger,
                logging.WARNING,
                "llm_provider_plaintext_drafts_recovered",
                request_id=request_id,
                provider=self.provider_name,
                recovered_count=len(recovered_payload.get("drafts", [])),
            )
            return recovered_payload

    @staticmethod
    def _recover_plaintext_drafts(content_text: str) -> dict[str, Any] | None:
        numbered_pattern = re.compile(
            r"(?:^|\n)\s*\d{1,2}[\.、\)]\s*(.*?)(?=(?:\n\s*\d{1,2}[\.、\)])|\Z)",
            flags=re.DOTALL,
        )
        bullet_pattern = re.compile(r"(?:^|\n)\s*[-*•]\s*(.+)")

        candidates: list[str] = []

        numbered_matches = numbered_pattern.findall(content_text)
        for chunk in numbered_matches:
            normalized = OpenAIClient._normalize_plaintext_candidate(chunk)
            if normalized:
                candidates.append(normalized)

        if not candidates:
            bullet_matches = bullet_pattern.findall(content_text)
            for chunk in bullet_matches:
                normalized = OpenAIClient._normalize_plaintext_candidate(chunk)
                if normalized:
                    candidates.append(normalized)

        if not candidates:
            paragraph_chunks = [part for part in re.split(r"\n\s*\n+", content_text) if part.strip()]
            for chunk in paragraph_chunks:
                normalized = OpenAIClient._normalize_plaintext_candidate(chunk)
                if normalized:
                    candidates.append(normalized)

        if not candidates:
            return None

        deduped: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            lowered = candidate.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            deduped.append(candidate)

        drafts = [
            {
                "text": text,
                "tone_tags": [],
                "rationale": "Recovered from non-JSON OpenAI output",
            }
            for text in deduped
        ]
        return {"drafts": drafts} if drafts else None

    @staticmethod
    def _normalize_plaintext_candidate(text: str) -> str:
        compact = "\n".join(line.strip() for line in text.splitlines()).strip()
        compact = re.sub(r"\s+", " ", compact)
        compact = compact.strip("`\"' ")
        return compact
