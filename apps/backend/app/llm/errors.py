from __future__ import annotations


class LLMError(RuntimeError):
    """Raised when the configured LLM integration fails."""


class LLMTransportError(LLMError):
    """Raised when the LLM transport fails after transient retry handling."""

    def __init__(self, message: str, *, category: str):
        super().__init__(message)
        self.category = category


OpenAIError = LLMError
