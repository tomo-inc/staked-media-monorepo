from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.config import (
    _DEFAULT_BIND_HOST,
    clear_config_cache,
    get_runtime_config_path,
    load_config_file,
    set_runtime_config_path,
)


class ConfigTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        clear_config_cache()

    def test_load_config_file_reads_grouped_json_and_resolves_relative_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "server": {
                            "host": "127.0.0.1",
                            "port": 9100,
                            "reload": True,
                        },
                        "app": {
                            "llm_provider": " GEMINI ",
                            "gemini_api_key": "gemini-key",
                            "database_url": "sqlite:///./db/mvp.db",
                            "log_file_path": "logs/app.log",
                        },
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_config_file(config_path)

            self.assertEqual(loaded.config_path, config_path.resolve())
            self.assertEqual(loaded.server.host, "127.0.0.1")
            self.assertEqual(loaded.server.port, 9100)
            self.assertTrue(loaded.server.reload)
            self.assertEqual(loaded.app.llm_provider, "gemini")
            self.assertEqual(loaded.app.gemini_api_key, "gemini-key")
            self.assertEqual(loaded.app.database_path, (config_path.parent / "db" / "mvp.db").resolve())
            self.assertEqual(Path(loaded.app.log_file_path), (config_path.parent / "logs" / "app.log").resolve())

    def test_load_config_file_uses_defaults_for_missing_sections(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "app": {
                            "openai_api_key": "openai-key",
                        }
                    }
                ),
                encoding="utf-8",
            )

            loaded = load_config_file(config_path)

            self.assertEqual(loaded.server.host, _DEFAULT_BIND_HOST)
            self.assertEqual(loaded.server.port, 8000)
            self.assertFalse(loaded.server.reload)
            self.assertEqual(loaded.app.openai_api_key, "openai-key")
            self.assertEqual(loaded.app.database_path, (config_path.parent / "data" / "mvp.db").resolve())

    def test_runtime_config_pointer_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(json.dumps({"app": {"openai_api_key": "openai-key"}}), encoding="utf-8")
            runtime_pointer_path = Path(temp_dir) / "runtime-config-path.json"

            written_path = set_runtime_config_path(config_path, runtime_config_path=runtime_pointer_path)
            restored_path = get_runtime_config_path(runtime_config_path=runtime_pointer_path)

            self.assertEqual(written_path, runtime_pointer_path)
            self.assertEqual(restored_path, config_path.resolve())

    def test_load_config_file_rejects_unknown_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "server": {
                            "host": "127.0.0.1",
                            "unknown": True,
                        }
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(ValidationError):
                load_config_file(config_path)


if __name__ == "__main__":
    unittest.main()
