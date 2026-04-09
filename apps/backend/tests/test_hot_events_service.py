from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import requests

from app.config import HotEventsFusionSettings
from app.hot_events import HotEventsService

FAKE_API_TOKEN = "test-token"  # noqa: S105


class _FakeResponse:
    def __init__(self, payload: dict, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


class HotEventsServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = HotEventsService(
            timeout_seconds=2.0,
            cache_ttl_seconds=120,
            api_token=FAKE_API_TOKEN,
        )

    def test_partial_success_returns_warnings_and_source_status(self) -> None:
        recent_ts = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)).isoformat()

        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "categories": [
                                    {"code": "Reuters", "aiEnabled": True, "sort": 100},
                                ]
                            }
                        ],
                    }
                )
            if url.endswith("/open/tweets_type"):
                raise requests.RequestException("tweets type timeout")
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": 1,
                                "text": "ETF inflow spikes",
                                "ts": recent_ts,
                                "newsType": "Reuters",
                                "link": "https://example.com/etf",
                                "source": "Reuters",
                                "description": "Inflow jumped sharply.",
                                "engineType": "news",
                                "aiRating": {"score": 82, "enSummary": "Strong ETF inflow"},
                            }
                        ],
                    }
                )
            raise requests.RequestException("twitter search unavailable")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch(
                "app.hot_events.requests.post",
                side_effect=fake_post,
            ),
        ):
            payload = self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["content_type"], "news")
        self.assertEqual(payload["source_status"]["opennews"]["status"], "ok")
        self.assertEqual(payload["source_status"]["opentwitter"]["status"], "error")
        self.assertTrue(payload["warnings"])

    def test_all_sources_failed_raises_runtime_error(self) -> None:
        with (
            patch(
                "app.hot_events.requests.get",
                side_effect=requests.RequestException("network down"),
            ),
            patch(
                "app.hot_events.requests.post",
                side_effect=requests.RequestException("network down"),
            ),
        ):
            with self.assertRaises(RuntimeError):
                self.service.list_hot_events(hours=24, limit=10, refresh=True)

    def test_cache_and_refresh_behaviour(self) -> None:
        call_counts = {"get": 0, "post": 0}
        recent_ts = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)).isoformat()

        def fake_get(url: str, *args, **kwargs):
            call_counts["get"] += 1
            if url.endswith("/open/news_type"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [{"categories": [{"code": "Reuters", "aiEnabled": True, "sort": 10}]}],
                    }
                )
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            call_counts["post"] += 1
            if url.endswith("/open/news_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": 1,
                                "text": "Macro headline",
                                "ts": recent_ts,
                                "newsType": "Reuters",
                                "link": "https://example.com/macro",
                                "source": "Reuters",
                                "description": "Macro move",
                                "engineType": "news",
                                "aiRating": {"score": 60, "enSummary": "Macro move"},
                            }
                        ],
                    }
                )
            if url.endswith("/open/tweets_search") or url.endswith("/open/twitter_search"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch(
                "app.hot_events.requests.post",
                side_effect=fake_post,
            ),
        ):
            first = self.service.list_hot_events(hours=24, limit=10, refresh=True)
            second = self.service.list_hot_events(hours=24, limit=10, refresh=False)
            third = self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(len(first["items"]), 1)
        self.assertEqual(len(second["items"]), 1)
        self.assertEqual(len(third["items"]), 1)
        self.assertGreaterEqual(call_counts["get"], 6)
        self.assertGreaterEqual(call_counts["post"], 6)

    def test_twitter_item_normalization_with_inferred_score(self) -> None:
        recent_tweet_ts = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)).strftime(
            "%a %b %d %H:%M:%S +0000 %Y"
        )

        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                raise requests.RequestException("news unavailable")
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/tweets_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": "2040946284396265834",
                                "text": "BTC breakout setup",
                                "createdAt": recent_tweet_ts,
                                "retweetCount": 100,
                                "favoriteCount": 200,
                                "replyCount": 30,
                                "quoteCount": 20,
                                "userScreenName": "alpha",
                                "userName": "Alpha",
                                "userFollowers": 50000,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch(
                "app.hot_events.requests.post",
                side_effect=fake_post,
            ),
        ):
            payload = self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(len(payload["items"]), 1)
        item = payload["items"][0]
        self.assertEqual(item["content_type"], "tweet")
        self.assertEqual(item["author_handle"], "alpha")
        self.assertEqual(item["source_domain"], "x.com")
        self.assertGreater(item["heat_score"], 0)

    def test_opentwitter_404_falls_back_to_legacy_search_without_warning(self) -> None:
        recent_tweet_ts = (datetime.now(UTC).replace(microsecond=0) - timedelta(hours=2)).strftime(
            "%a %b %d %H:%M:%S +0000 %Y"
        )

        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_search"):
                return _FakeResponse({}, status_code=404)
            if url.endswith("/open/twitter_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": "tweet-legacy-1",
                                "text": "Legacy fallback tweet",
                                "createdAt": recent_tweet_ts,
                                "retweetCount": 12,
                                "favoriteCount": 34,
                                "replyCount": 5,
                                "quoteCount": 1,
                                "userScreenName": "legacy",
                                "userName": "Legacy",
                                "userFollowers": 1200,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch("app.hot_events.requests.post", side_effect=fake_post),
        ):
            payload = self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["content_type"], "tweet")
        self.assertEqual(payload["source_status"]["opennews"]["status"], "ok")
        self.assertEqual(payload["source_status"]["opentwitter"]["status"], "ok")
        self.assertEqual(payload["warnings"], [])

    def test_opentwitter_failure_uses_generic_error_when_both_search_paths_fail(self) -> None:
        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_search") or url.endswith("/open/twitter_search"):
                return _FakeResponse({}, status_code=404)
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch("app.hot_events.requests.post", side_effect=fake_post),
        ):
            with self.assertRaises(RuntimeError) as context:
                self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(
            str(context.exception),
            f"opentwitter unavailable: {self.service.OPENTWITTER_UNAVAILABLE_ERROR}",
        )

    def test_opentwitter_invalid_legacy_payload_uses_generic_error(self) -> None:
        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse({"success": True, "data": []})
            if url.endswith("/open/tweets_search"):
                return _FakeResponse({}, status_code=404)
            if url.endswith("/open/twitter_search"):
                return _FakeResponse({"success": True, "data": {"items": []}})
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch("app.hot_events.requests.post", side_effect=fake_post),
        ):
            with self.assertRaises(RuntimeError) as context:
                self.service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(
            str(context.exception),
            f"opentwitter unavailable: {self.service.OPENTWITTER_UNAVAILABLE_ERROR}",
        )

    def test_source_weights_can_promote_tweets_over_news(self) -> None:
        now_utc = datetime.now(UTC).replace(microsecond=0)
        recent_news_ts = (now_utc - timedelta(hours=2)).isoformat()
        recent_tweet_ts = (now_utc - timedelta(hours=1)).isoformat()
        service = HotEventsService(
            timeout_seconds=2.0,
            cache_ttl_seconds=120,
            api_token=FAKE_API_TOKEN,
            fusion_settings=HotEventsFusionSettings(
                source_weight_news=0.3,
                source_weight_tweet=2.0,
                time_decay_half_life_hours=9999.0,
            ),
        )

        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [{"categories": [{"code": "Reuters", "aiEnabled": True, "sort": 10}]}],
                    }
                )
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": 1,
                                "text": "ETF inflow spikes",
                                "ts": recent_news_ts,
                                "newsType": "Reuters",
                                "link": "https://example.com/etf",
                                "source": "Reuters",
                                "description": "Inflow jumped sharply.",
                                "aiRating": {"score": 90, "enSummary": "Strong ETF inflow"},
                            }
                        ],
                    }
                )
            if url.endswith("/open/tweets_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": "tweet-1",
                                "text": "BTC breakout setup",
                                "createdAt": recent_tweet_ts,
                                "retweetCount": 10,
                                "favoriteCount": 20,
                                "replyCount": 5,
                                "quoteCount": 0,
                                "userScreenName": "alpha",
                                "userName": "Alpha",
                                "userFollowers": 1000,
                            }
                        ],
                    }
                )
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch(
                "app.hot_events.requests.post",
                side_effect=fake_post,
            ),
        ):
            payload = service.list_hot_events(hours=24, limit=10, refresh=True)

        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["content_type"], "tweet")
        self.assertGreater(payload["items"][0]["heat_score"], payload["items"][1]["heat_score"])

    def test_time_decay_penalizes_older_items(self) -> None:
        now_utc = datetime.now(UTC).replace(microsecond=0)
        newer_ts = now_utc.isoformat()
        older_ts = (now_utc - timedelta(hours=24)).isoformat()
        service = HotEventsService(
            timeout_seconds=2.0,
            cache_ttl_seconds=120,
            api_token=FAKE_API_TOKEN,
            fusion_settings=HotEventsFusionSettings(time_decay_half_life_hours=4.0),
        )

        def fake_get(url: str, *args, **kwargs):
            if url.endswith("/open/news_type"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [{"categories": [{"code": "Reuters", "aiEnabled": True, "sort": 10}]}],
                    }
                )
            if url.endswith("/open/tweets_type"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected GET URL: {url}")

        def fake_post(url: str, *args, **kwargs):
            if url.endswith("/open/news_search"):
                return _FakeResponse(
                    {
                        "success": True,
                        "data": [
                            {
                                "id": 1,
                                "text": "New macro headline",
                                "ts": newer_ts,
                                "newsType": "Reuters",
                                "link": "https://example.com/new",
                                "source": "Reuters",
                                "description": "new item",
                                "aiRating": {"score": 80, "enSummary": "new"},
                            },
                            {
                                "id": 2,
                                "text": "Old macro headline",
                                "ts": older_ts,
                                "newsType": "Reuters",
                                "link": "https://example.com/old",
                                "source": "Reuters",
                                "description": "old item",
                                "aiRating": {"score": 80, "enSummary": "old"},
                            },
                        ],
                    }
                )
            if url.endswith("/open/tweets_search") or url.endswith("/open/twitter_search"):
                return _FakeResponse({"success": True, "data": []})
            raise AssertionError(f"Unexpected POST URL: {url}")

        with (
            patch("app.hot_events.requests.get", side_effect=fake_get),
            patch(
                "app.hot_events.requests.post",
                side_effect=fake_post,
            ),
        ):
            payload = service.list_hot_events(hours=48, limit=10, refresh=True)

        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["url"], "https://example.com/new")
        self.assertEqual(payload["items"][1]["url"], "https://example.com/old")
        self.assertGreater(payload["items"][0]["heat_score"], payload["items"][1]["heat_score"])


if __name__ == "__main__":
    unittest.main()
