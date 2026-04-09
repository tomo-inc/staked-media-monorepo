from __future__ import annotations

from app.config import Settings

from .base_client import LLMClient
from .gemini_client import GeminiClient
from .openai_client import OpenAIClient


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm.provider == "gemini":
        return GeminiClient(settings)
    return OpenAIClient(settings)
