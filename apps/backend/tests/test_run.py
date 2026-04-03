from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.config import clear_config_cache
from app.run import main


class RunModuleTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        clear_config_cache()

    def test_main_launches_uvicorn_with_json_config(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            config_path.write_text(
                json.dumps(
                    {
                        "server": {
                            "host": "127.0.0.1",
                            "port": 8123,
                            "reload": False,
                        },
                        "app": {
                            "openai_api_key": "openai-key",
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch("app.run.set_runtime_config_path") as mock_set_runtime_config_path:
                with patch("app.run.uvicorn.run") as mock_uvicorn_run:
                    main(["-c", str(config_path), "--reload"])

            mock_set_runtime_config_path.assert_called_once_with(config_path.resolve())
            mock_uvicorn_run.assert_called_once()
            kwargs = mock_uvicorn_run.call_args.kwargs
            self.assertEqual(kwargs["app"], "app.main:create_app_from_runtime_config")
            self.assertTrue(kwargs["factory"])
            self.assertEqual(kwargs["host"], "127.0.0.1")
            self.assertEqual(kwargs["port"], 8123)
            self.assertTrue(kwargs["reload"])

    def test_main_exits_when_config_file_is_missing(self) -> None:
        with self.assertRaisesRegex(SystemExit, "Failed to load config file"):
            main(["-c", "missing-config.json"])


if __name__ == "__main__":
    unittest.main()
