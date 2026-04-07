from __future__ import annotations

import unittest

import requests

from app.config import Settings
from app.upstream import UpstreamClient


class DummyResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.text = str(payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error", response=self)
        return None

    def json(self) -> dict:
        return self.payload


class DummySession:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url, params=None, proxies=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "proxies": proxies,
                "timeout": timeout,
            }
        )
        if params and params.get("cursor") == "cursor-1":
            return DummyResponse(
                {
                    "code": 200,
                    "data": {
                        "data": [{"data": {"id": "3", "text": "third", "created_at": "2026-03-03T00:00:00Z"}}],
                        "next_cursor": None,
                    },
                }
            )
        return DummyResponse(
            {
                "code": 200,
                "data": {
                    "data": [
                        {"data": {"id": "1", "text": "first", "created_at": "2026-03-01T00:00:00Z"}},
                        {"data": {"id": "2", "text": "second", "created_at": "2026-03-02T00:00:00Z"}},
                    ],
                    "next_cursor": "cursor-1",
                },
            }
        )


class MultiPageSession:
    def __init__(self) -> None:
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, params=None, proxies=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "proxies": proxies,
                "timeout": timeout,
            }
        )
        cursor = (params or {}).get("cursor")
        if cursor == "cursor-1":
            return DummyResponse(
                {
                    "code": 200,
                    "data": {
                        "data": [
                            {"data": {"id": "3", "text": "third", "created_at": "2026-03-03T00:00:00Z"}},
                            {"data": {"id": "4", "text": "fourth", "created_at": "2026-03-04T00:00:00Z"}},
                        ],
                        "next_cursor": "cursor-2",
                    },
                }
            )
        if cursor == "cursor-2":
            return DummyResponse(
                {
                    "code": 200,
                    "data": {
                        "data": [
                            {"data": {"id": "5", "text": "fifth", "created_at": "2026-03-05T00:00:00Z"}},
                            {"data": {"id": "6", "text": "sixth", "created_at": "2026-03-06T00:00:00Z"}},
                        ],
                        "next_cursor": None,
                    },
                }
            )
        return DummyResponse(
            {
                "code": 200,
                "data": {
                    "data": [
                        {"data": {"id": "1", "text": "first", "created_at": "2026-03-01T00:00:00Z"}},
                        {"data": {"id": "2", "text": "second", "created_at": "2026-03-02T00:00:00Z"}},
                    ],
                    "next_cursor": "cursor-1",
                },
            }
        )


class RetrySession:
    def __init__(self) -> None:
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, params=None, proxies=None, timeout=None):
        self.calls.append(url)
        if len(self.calls) == 1:
            return DummyResponse({"code": 500, "message": "temporary upstream issue"}, status_code=500)
        return DummyResponse({"code": 200, "data": {"data": [], "next_cursor": None}})


class RepeatingCursorSession:
    def __init__(self) -> None:
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, params=None, proxies=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "proxies": proxies,
                "timeout": timeout,
            }
        )
        if params and params.get("cursor") == "cursor-1":
            return DummyResponse(
                {
                    "code": 200,
                    "data": {
                        "data": [{"data": {"id": "2", "text": "second", "created_at": "2026-03-02T00:00:00Z"}}],
                        "next_cursor": "cursor-1",
                    },
                }
            )
        return DummyResponse(
            {
                "code": 200,
                "data": {
                    "data": [{"data": {"id": "1", "text": "first", "created_at": "2026-03-01T00:00:00Z"}}],
                    "next_cursor": "cursor-1",
                },
            }
        )


class EmptyPageSession:
    def __init__(self) -> None:
        self.calls = []
        self.cookies = requests.cookies.RequestsCookieJar()

    def get(self, url, params=None, proxies=None, timeout=None):
        self.calls.append(
            {
                "url": url,
                "params": params,
                "proxies": proxies,
                "timeout": timeout,
            }
        )
        if params and params.get("cursor") == "cursor-1":
            return DummyResponse(
                {
                    "code": 200,
                    "data": {
                        "data": [],
                        "next_cursor": "cursor-2",
                    },
                }
            )
        return DummyResponse(
            {
                "code": 200,
                "data": {
                    "data": [{"data": {"id": "1", "text": "first", "created_at": "2026-03-01T00:00:00Z"}}],
                    "next_cursor": "cursor-1",
                },
            }
        )


class UpstreamClientTestCase(unittest.TestCase):
    def test_client_disables_environment_proxy_for_default_session(self) -> None:
        settings = Settings(twitter_data_url="http://52.76.50.165:8081", twitter_data_proxy="")
        client = UpstreamClient(settings)
        self.assertFalse(client.session.trust_env)

    def test_fetch_user_tweets_paginates_with_cursor_and_uses_proxy(self) -> None:
        session = DummySession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        items = client.fetch_user_tweets("user-1", max_tweets=3)

        self.assertEqual(len(items), 3)
        self.assertEqual(session.calls[0]["params"], None)
        self.assertEqual(session.calls[1]["params"], {"cursor": "cursor-1"})
        self.assertEqual(
            session.calls[0]["proxies"],
            {"http": "http://192.168.1.199:9000", "https": "http://192.168.1.199:9000"},
        )

    def test_get_json_retries_on_transient_server_error(self) -> None:
        session = RetrySession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        payload = client._get_json("/api/v1/tweets/user-1")

        self.assertEqual(payload["code"], 200)
        self.assertEqual(len(session.calls), 2)

    def test_fetch_user_tweets_continues_until_requested_count(self) -> None:
        session = MultiPageSession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        items = client.fetch_user_tweets("user-1", max_tweets=5)

        self.assertEqual(len(items), 5)
        self.assertEqual(session.calls[0]["params"], None)
        self.assertEqual(session.calls[1]["params"], {"cursor": "cursor-1"})
        self.assertEqual(session.calls[2]["params"], {"cursor": "cursor-2"})

    def test_fetch_user_tweets_stops_when_upstream_exhausts_before_requested_count(self) -> None:
        session = MultiPageSession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        items = client.fetch_user_tweets("user-1", max_tweets=10)

        self.assertEqual(len(items), 6)
        self.assertEqual(len(session.calls), 3)

    def test_fetch_user_tweets_stops_when_cursor_repeats(self) -> None:
        session = RepeatingCursorSession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        items = client.fetch_user_tweets("user-1", max_tweets=5)

        self.assertEqual(len(items), 2)
        self.assertEqual(session.calls[0]["params"], None)
        self.assertEqual(session.calls[1]["params"], {"cursor": "cursor-1"})
        self.assertEqual(len(session.calls), 2)

    def test_fetch_user_tweets_stops_when_page_is_empty_even_with_next_cursor(self) -> None:
        session = EmptyPageSession()
        settings = Settings(
            twitter_data_url="http://52.76.50.165:8081",
            twitter_data_proxy="http://192.168.1.199:9000",
        )
        client = UpstreamClient(settings, session=session)

        items = client.fetch_user_tweets("user-1", max_tweets=5)

        self.assertEqual(len(items), 1)
        self.assertEqual(session.calls[0]["params"], None)
        self.assertEqual(session.calls[1]["params"], {"cursor": "cursor-1"})
        self.assertEqual(len(session.calls), 2)


if __name__ == "__main__":
    unittest.main()
