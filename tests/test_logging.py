from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import Settings
from app.llm import GeminiClient, LLMError
from app.logging_utils import configure_logging, format_log_event, get_logger, log_event


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_body: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self) -> dict:
        return self._json_body


class LoggingTestCase(unittest.TestCase):
    def test_configure_logging_writes_to_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "app.log"
            settings = Settings(
                openai_api_key="test-key",
                log_file_path=str(log_path),
                log_enable_file=True,
            )

            configure_logging(settings)
            log_event(get_logger("app.test"), logging.INFO, "test_log_written", marker="ok")
            for handler in logging.getLogger("app").handlers:
                handler.flush()

            self.assertTrue(log_path.exists())
            contents = log_path.read_text(encoding="utf-8")
            self.assertIn('"event":"test_log_written"', contents)
            self.assertIn('"marker":"ok"', contents)

    def test_configure_logging_is_idempotent_for_same_signature(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "app.log"
            settings = Settings(
                openai_api_key="test-key",
                log_file_path=str(log_path),
                log_enable_file=True,
                log_level="INFO",
            )

            configure_logging(settings)
            parent_logger = logging.getLogger("app")
            handler_ids = [id(handler) for handler in parent_logger.handlers]

            # Second call should not add or replace handlers.
            configure_logging(settings)
            handler_ids_after = [id(handler) for handler in parent_logger.handlers]

            self.assertEqual(handler_ids_after, handler_ids)

            for logger_name in ("uvicorn.error", "uvicorn.access", "uvicorn.asgi", "fastapi"):
                logger = logging.getLogger(logger_name)
                self.assertEqual([id(handler) for handler in logger.handlers], handler_ids)
                self.assertEqual(logger.level, parent_logger.level)
                self.assertFalse(logger.propagate)

    def test_format_log_event_drops_none_fields(self) -> None:
        payload = format_log_event("test_event", present="ok", missing=None)
        self.assertIn('"event":"test_event"', payload)
        self.assertIn('"present":"ok"', payload)
        self.assertNotIn("missing", payload)

    def test_uvicorn_and_fastapi_logs_use_shared_timestamped_handlers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            log_path = Path(temp_dir) / "app.log"
            settings = Settings(
                openai_api_key="test-key",
                log_file_path=str(log_path),
                log_enable_file=True,
                log_level="INFO",
            )

            configure_logging(settings)
            logging.getLogger("uvicorn.error").info("uvicorn error entry")
            logging.getLogger("uvicorn.access").info('127.0.0.1 - "GET /healthz HTTP/1.1" 200')
            logging.getLogger("fastapi").warning("fastapi warning entry")
            for handler in logging.getLogger("app").handlers:
                handler.flush()

            contents = log_path.read_text(encoding="utf-8")
            self.assertRegex(contents, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} INFO uvicorn\.error uvicorn error entry")
            self.assertRegex(
                contents,
                r'\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} INFO uvicorn\.access 127\.0\.0\.1 - "GET /healthz HTTP/1\.1" 200',
            )
            self.assertRegex(contents, r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2},\d{3} WARNING fastapi fastapi warning entry")
            self.assertEqual(contents.count("uvicorn error entry"), 1)
            self.assertEqual(contents.count("fastapi warning entry"), 1)

    @patch("app.llm.base_client.requests.post")
    def test_invalid_json_logs_redacted_snippet_without_api_key(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": "x" * 200}
                            ]
                        }
                    }
                ]
            }
        )
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="super-secret-key",
                log_enable_file=False,
                log_max_body_chars=20,
            )
        )

        with self.assertLogs("app.llm", level="WARNING") as captured:
            with self.assertRaisesRegex(LLMError, "Gemini returned invalid JSON"):
                client._chat_completion_json(
                    system_prompt="Return JSON",
                    user_prompt='{"candidate_text":"hello"}',
                    temperature=0.3,
                )

        joined = "\n".join(captured.output)
        self.assertIn('"event":"llm_provider_invalid_json"', joined)
        self.assertIn("xxxxxxxx", joined)
        self.assertIn("...", joined)
        self.assertNotIn("super-secret-key", joined)
        self.assertNotIn("x" * 50, joined)


if __name__ == "__main__":
    unittest.main()
