from __future__ import annotations

import tempfile
import unittest

from app.config import Settings
from app.database import Database


class DatabaseWhitelistTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{self.temp_dir.name}/mvp.db",
            openai_api_key="test-key",
            log_enable_file=False,
        )
        self.database = Database(settings.database_path)
        self.database.init()

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_allowed_usernames_are_normalized_and_idempotent(self) -> None:
        self.database.add_allowed_username(" ElonMusk ")
        self.database.add_allowed_username("elonmusk")

        self.assertTrue(self.database.is_username_allowed("ELONMUSK"))
        self.assertEqual(self.database.list_allowed_usernames(), ["elonmusk"])

        self.database.remove_allowed_username("ELONMUSK")
        self.assertFalse(self.database.is_username_allowed("elonmusk"))
        self.assertEqual(self.database.list_allowed_usernames(), [])


if __name__ == "__main__":
    unittest.main()
