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

    def test_hot_events_are_upserted_per_item_and_queryable(self) -> None:
        refreshed_at = "2026-04-07T10:00:00+00:00"
        updated_at = "2026-04-07T11:00:00+00:00"
        items = [
            {
                "id": "news:web3:event-1",
                "title": "ETF flows accelerate",
                "summary": "Large inflows tracked.",
                "url": "https://example.com/etf",
                "source": "Example",
                "source_domain": "example.com",
                "published_at": refreshed_at,
                "relative_age_hint": "1h ago",
                "heat_score": 98.0,
                "category": "news",
                "subcategory": "web3",
                "content_type": "news",
                "author_handle": "",
            },
            {
                "id": "tweet:x:event-2",
                "title": "Rotation is live",
                "summary": "Desk chatter points to rotation.",
                "url": "https://x.com/example/status/2",
                "source": "@example",
                "source_domain": "x.com",
                "published_at": "2026-04-07T09:30:00+00:00",
                "relative_age_hint": "30m ago",
                "heat_score": 101.0,
                "category": "social",
                "subcategory": "x",
                "content_type": "tweet",
                "author_handle": "example",
            },
        ]

        self.database.upsert_hot_events(items, refreshed_at)
        self.database.upsert_hot_events(
            [
                {
                    **items[0],
                    "summary": "Updated summary",
                    "heat_score": 88.0,
                }
            ],
            updated_at,
        )

        rows = self.database.list_hot_events(published_since="2026-04-06T12:00:00+00:00", limit=10)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["id"], "tweet:x:event-2")
        self.assertEqual(rows[1]["id"], "news:web3:event-1")
        self.assertEqual(rows[1]["summary"], "Updated summary")
        self.assertEqual(rows[1]["created_at"], refreshed_at)
        self.assertEqual(rows[1]["updated_at"], updated_at)
        self.assertEqual(rows[1]["last_refreshed_at"], updated_at)
        self.assertEqual(rows[1]["raw_json"]["id"], "news:web3:event-1")

        event = self.database.get_hot_event_by_id(
            "news:web3:event-1",
            published_since="2026-04-06T12:00:00+00:00",
        )
        self.assertIsNotNone(event)
        assert event is not None
        self.assertEqual(event["summary"], "Updated summary")
        self.assertEqual(self.database.get_latest_hot_events_refresh_time(), updated_at)


if __name__ == "__main__":
    unittest.main()
