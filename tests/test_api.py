from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.llm import GeminiClient


class FakeUpstreamClient:
    def fetch_user_by_username(self, username: str, *, request_id: str | None = None) -> dict:
        return {
            "id": "u-1",
            "username": username,
            "name": "Test User",
            "description": "Builder and investor",
            "location": "Singapore",
            "url": "https://example.com",
            "verified": True,
            "public_metrics": {
                "followers_count": 1234,
                "following_count": 120,
                "tweet_count": 240,
            },
        }

    def fetch_user_tweets(
        self,
        user_id: str,
        max_tweets: int = 500,
        *,
        request_id: str | None = None,
    ) -> list[dict]:
        items = []
        for index in range(min(max_tweets, 8)):
            items.append(
                {
                    "data": {
                        "id": f"t-{index}",
                        "text": f"Building in public with clear lessons {index}",
                        "created_at": f"2026-03-{index + 1:02d}T00:00:00Z",
                        "lang": "en",
                        "in_reply_to_user_id": "" if index % 3 else "another-user",
                        "referenced_tweets": [] if index % 4 else [{"id": "x", "type": "quoted"}],
                        "public_metrics": {
                            "like_count": 10 + index,
                            "retweet_count": 5,
                            "reply_count": 2,
                            "quote_count": 1,
                        },
                    }
                }
            )
        return items


class FakeLLMClient:
    def generate_persona(
        self,
        *,
        profile: dict,
        corpus_stats: dict,
        representative_tweets: list[dict],
        request_id: str | None = None,
    ) -> dict:
        return {
            "persona_version": "v1",
            "author_summary": f"{profile['name']} writes concise operator updates.",
            "voice_traits": ["operator-minded", "direct", "optimistic"],
            "topic_clusters": [{"topic": "product building", "evidence": ["building", "lessons"]}],
            "writing_patterns": {"average_length": corpus_stats["writing_stats"]["average_length"]},
            "lexical_markers": ["building", "lessons"],
            "do_not_sound_like": ["corporate PR", "clickbait"],
            "cta_style": "Occasional direct invitation to discuss.",
            "risk_notes": ["Derived from public posts only."],
        }

    def generate_drafts(
        self,
        *,
        persona: dict,
        prompt: str,
        representative_tweets: list[dict],
        source_texts: list[str],
        tweet_rows: list[dict],
        draft_count: int,
        request_id: str | None = None,
    ) -> dict:
        drafts = [
            {
                "text": f"Shipping faster means saying no to distractions. {prompt} #{index}",
                "tone_tags": ["direct", "builder"],
                "rationale": "Matches the concise operator tone.",
            }
            for index in range(draft_count)
        ]
        return {
            "drafts": drafts,
            "theme_keywords": ["focus"],
            "theme_top_keywords": ["shipping", "focus", "lessons"],
            "matched_theme_tweets": [
                {
                    "created_at": tweet_rows[0]["created_at"],
                    "text": tweet_rows[0]["text"],
                    "match_terms": ["focus"],
                }
            ],
            "best_score": 9.2,
            "target_score": 9.0,
            "target_score_met": True,
            "attempt_count": 1,
            "attempts": [
                {
                    "attempt": 1,
                    "best_score": 9.2,
                    "target_score_met": True,
                    "candidates": [
                        {
                            "text": drafts[0]["text"],
                            "tone_tags": drafts[0]["tone_tags"],
                            "rationale": drafts[0]["rationale"],
                            "rule_score": 9.4,
                            "llm_score": 9.2,
                            "final_score": 9.2,
                            "passed": True,
                            "rule_issues": [],
                            "rule_strengths": ["Theme keyword hits: focus"],
                            "llm_verdict": "strong_fit",
                            "llm_issues": [],
                            "llm_strengths": ["Matches the concise operator tone."],
                            "must_fix": [],
                            "failure_reasons": [],
                        }
                    ],
                }
            ],
            "evaluation": {"best_candidate": {"final_score": 9.2}},
        }


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{self.temp_dir.name}/mvp.db",
            openai_api_key="test-key",
            log_enable_file=False,
        )
        self.client = TestClient(
            create_app(
                settings,
                upstream_client=FakeUpstreamClient(),
                llm_client=FakeLLMClient(),
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingest_profile_then_generate_drafts(self) -> None:
        ingest_response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user", "max_tweets": 8},
        )
        self.assertEqual(ingest_response.status_code, 200)
        ingest_payload = ingest_response.json()
        self.assertEqual(ingest_payload["fetched_tweet_count"], 8)
        self.assertEqual(ingest_payload["profile"]["username"], "demo-user")

        profile_response = self.client.get("/api/v1/profiles/demo-user")
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["stored_tweet_count"], 8)

        drafts_response = self.client.post(
            "/api/v1/drafts/generate",
            json={"username": "demo-user", "prompt": "Talk about focus", "draft_count": 3},
        )
        self.assertEqual(drafts_response.status_code, 200)
        drafts_payload = drafts_response.json()
        self.assertEqual(len(drafts_payload["drafts"]), 3)
        self.assertIn("Talk about focus", drafts_payload["drafts"][0]["text"])
        self.assertEqual(drafts_payload["theme_keywords"], ["focus"])
        self.assertTrue(drafts_payload["target_score_met"])
        self.assertEqual(drafts_payload["attempts"][0]["candidates"][0]["final_score"], 9.2)
        self.assertEqual(drafts_payload["attempts"][0]["candidates"][0]["failure_reasons"], [])

    def test_ingest_requires_explicit_max_tweets(self) -> None:
        response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user"},
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("max_tweets", response.text)

    def test_generate_drafts_requires_ingest_first(self) -> None:
        response = self.client.post(
            "/api/v1/drafts/generate",
            json={"username": "missing-user", "prompt": "Talk about focus", "draft_count": 3},
        )
        self.assertEqual(response.status_code, 404)

    def test_create_app_uses_gemini_provider_factory(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{temp_dir.name}/mvp.db",
                llm_provider="gemini",
                gemini_api_key="gemini-key",
                log_enable_file=False,
            )
            with patch.object(GeminiClient, "_chat_completion_json", side_effect=AssertionError("should not call")):
                app = create_app(settings, upstream_client=FakeUpstreamClient())
            self.assertIsInstance(app.state.llm, GeminiClient)
        finally:
            temp_dir.cleanup()

    def test_generate_route_logs_request_metadata(self) -> None:
        self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user", "max_tweets": 8},
        )

        with self.assertLogs("app.main", level="INFO") as captured:
            response = self.client.post(
                "/api/v1/drafts/generate",
                json={"username": "demo-user", "prompt": "Talk about focus", "draft_count": 2},
            )

        self.assertEqual(response.status_code, 200)
        joined = "\n".join(captured.output)
        self.assertIn('"event":"api_draft_generate_started"', joined)
        self.assertIn('"event":"api_draft_generate_completed"', joined)
        self.assertIn('"request_id":"', joined)
        self.assertIn('"username":"demo-user"', joined)


if __name__ == "__main__":
    unittest.main()
