from __future__ import annotations

import logging
from typing import Any

from app.config import Settings
from app.logging_utils import get_logger, log_event

from .base_client import LLMClient
from .errors import LLMError
from .utils import _coerce_content_text, _parse_json_response

logger = get_logger(__name__)


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, provider_name="gemini")

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
        if not self.settings.llm.gemini.api_key:
            raise LLMError("Gemini API key is not configured")

        endpoint = (
            f"{self.settings.llm.gemini.base_url.rstrip('/')}/models/{self.settings.llm.gemini.model}:generateContent"
        )
        body = self._post_json_with_retries(
            endpoint=endpoint,
            params={"key": self.settings.llm.gemini.api_key},
            headers={"Content-Type": "application/json"},
            json_payload={
                "system_instruction": {
                    "parts": [{"text": system_prompt}],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "responseMimeType": "application/json",
                },
            },
            model=self.settings.llm.gemini.model,
            request_id=request_id,
            purpose=purpose,
            timeout_seconds=timeout_seconds,
        )
        candidates = body.get("candidates") or []
        if not candidates:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_missing_candidates",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.llm.gemini.model,
            )
            raise LLMError("Gemini response did not include any candidates")

        content = candidates[0].get("content", {}).get("parts", [])
        content_text = _coerce_content_text(content)
        if not content_text:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_empty_content",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.llm.gemini.model,
            )
            raise LLMError("Gemini response content was empty")

        return _parse_json_response(
            content_text,
            provider_name="Gemini",
            request_id=request_id,
            max_body_chars=self.settings.log.max_body_chars,
        )
