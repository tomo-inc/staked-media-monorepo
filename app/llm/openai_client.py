from __future__ import annotations

import logging
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

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_id: str | None = None,
        purpose: str = "generation",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise LLMError("OpenAI API key is not configured")

        endpoint = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        body = self._post_json_with_retries(
            endpoint=endpoint,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json_payload={
                "model": self.settings.openai_model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            model=self.settings.openai_model,
            request_id=request_id,
            purpose=purpose,
            timeout_seconds=timeout_seconds,
        )
        choices = body.get("choices") or []
        if not choices:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_missing_choices",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.openai_model,
            )
            raise LLMError("OpenAI response did not include any choices")

        content = choices[0].get("message", {}).get("content", "")
        content_text = _coerce_content_text(content)
        if not content_text:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_empty_content",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.openai_model,
            )
            raise LLMError("OpenAI response content was empty")

        return _parse_json_response(
            content_text,
            provider_name="OpenAI",
            request_id=request_id,
            max_body_chars=self.settings.log_max_body_chars,
        )
