from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.config import Settings
from app.database import Database
from app.llm import GeminiClient
from app.main import create_app
from app.orchestrator import ContentOrchestrator


class FakeUpstreamClient:
    def __init__(self) -> None:
        self.last_max_tweets: int | None = None

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
        max_tweets: int = 100,
        *,
        request_id: str | None = None,
    ) -> list[dict]:
        self.last_max_tweets = max_tweets
        items = []
        for index in range(min(max_tweets, 1200)):
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
    def __init__(self) -> None:
        self.last_source_text_count: int | None = None
        self.last_tweet_row_count: int | None = None

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
            "topic_clusters": [
                {
                    "topic": "product building",
                    "evidence_terms": ["building", "lessons"],
                    "frequency": "high",
                }
            ],
            "writing_patterns": {
                "avg_sentence_length": "medium",
                "punctuation_habits": ["light periods"],
                "paragraph_structure": "single-shot",
                "code_switching_style": "mostly English, occasional proper nouns",
                "emoji_usage": "none",
            },
            "lexical_markers": ["building", "lessons"],
            "do_not_sound_like": ["corporate PR", "clickbait"],
            "cta_style": "Occasional direct invitation to discuss.",
            "generation_guardrails": {
                "preferred_openings": ["observation-first"],
                "preferred_formats": ["short update"],
                "compression_rules": ["one idea then stop"],
                "anti_patterns": ["essay-like explanation"],
                "language_notes": ["stay concise and operator-like"],
            },
            "risk_notes": ["Derived from public posts only."],
            "language_profile": {
                "primary_language": "en",
                "secondary_languages": [],
                "mixing_pattern": "none",
                "mixing_notes": "",
            },
            "domain_expertise": [
                {
                    "domain": "product",
                    "depth": "expert",
                    "jargon_examples": ["shipping", "distribution"],
                }
            ],
            "emotional_baseline": {
                "default_valence": "positive",
                "intensity": "moderate",
                "sarcasm_level": "none",
                "humor_style": "",
            },
            "audience_profile": {
                "primary_audience": "builders",
                "assumed_knowledge": ["shipping", "product loops"],
                "formality": "casual",
            },
            "interaction_style": {
                "original_post_tone": "concise and operator-minded",
                "reply_tone": "supportive",
                "quote_tone": "adds a short take",
                "engagement_triggers": ["product lessons", "distribution"],
            },
            "posting_cadence": {
                "avg_daily_tweets": corpus_stats["cadence_stats"]["avg_daily_tweets"],
                "posting_style": corpus_stats["cadence_stats"]["posting_style_hint"],
                "preferred_post_length": corpus_stats["cadence_stats"]["preferred_post_length_hint"],
                "active_windows_utc": corpus_stats["cadence_stats"]["active_windows_utc"],
            },
            "media_habits": {
                "text_only_ratio": corpus_stats["media_stats"]["text_only_ratio"],
                "link_ratio": corpus_stats["media_stats"]["link_ratio"],
                "media_attachment_ratio": corpus_stats["media_stats"]["media_attachment_ratio"],
                "dominant_format": corpus_stats["media_stats"]["dominant_format_hint"],
                "notes": "mostly standalone product updates",
            },
            "geo_context": {
                "declared_location": profile.get("location") or "",
                "region_hint": "southeast asia",
                "timezone_hint": "UTC+8",
                "confidence": "medium",
                "notes": "location and posting windows point to Singapore/UTC+8",
            },
            "stance_patterns": {
                "hot_take_style": "measured",
                "controversy_posture": "avoids pile-ons",
                "endorsement_style": "selective",
                "notes": "prefers practical takes over maximalist endorsement",
            },
            "banned_phrases": ["dear ser"],
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
        self.last_source_text_count = len(source_texts)
        self.last_tweet_row_count = len(tweet_rows)
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


class FakeWebEnricher:
    def search_recent_topic_signals(self, topic: str, keywords: list[str]) -> dict:
        return {
            "keywords": [topic, "winners", "results", "binance"],
            "facts": [
                {
                    "title": f"{topic} winners announced",
                    "summary": "Public update with ranked results.",
                    "source": "test-source",
                    "url": "https://example.com/news",
                    "published_at": "2026-03-31T00:00:00+00:00",
                }
            ],
            "items": [],
        }


class FakeContentOrchestrator:
    def generate_content(self, payload, request_id: str) -> dict:
        return {
            "request_id": request_id,
            "mode": payload.mode,
            "topic": payload.topic or payload.idea or "content_generate",
            "variants": [
                {
                    "variant": "normal",
                    "label": "Normal",
                    "drafts": [
                        {
                            "text": "Draft one",
                            "tone_tags": ["direct"],
                            "rationale": "fit",
                        }
                    ],
                    "formatted_drafts": ["1. Draft one"],
                    "score": {
                        "theme_relevance": 9.0,
                        "style_similarity": 9.0,
                        "publishability": 9.0,
                        "final_score": 9.0,
                    },
                    "target_score_met": True,
                    "retry_count": 0,
                    "quality_gate_reason": "",
                    "compensation_used": False,
                    "used_keywords": ["btc"],
                    "source_facts": [],
                }
            ],
            "recommended_variant": "normal",
            "drafts": [
                {
                    "text": "Draft one",
                    "tone_tags": ["direct"],
                    "rationale": "fit",
                }
            ],
            "formatted_drafts": ["1. Draft one"],
            "score": {
                "theme_relevance": 9.0,
                "style_similarity": 9.0,
                "publishability": 9.0,
                "final_score": 9.0,
            },
            "target_score_met": True,
            "quality_gate_met": True,
            "quality_gate_reason": "",
            "retry_count": 0,
            "history_match_count": 0,
            "web_enrichment_used": False,
            "used_keywords": ["btc"],
            "web_keywords": [],
            "personal_phrases": [],
            "source_facts": [],
            "debug_summary": "ok",
        }

    def get_debug(self, request_id: str) -> dict | None:
        return None

    def suggest_ideas(self, *, direction: str, domain: str, topic_hint: str, limit: int) -> dict:
        return {"ideas": [], "query": "", "suggested_keywords": []}

    def analyze_exposure(self, *, username: str, text: str, topic: str, domain: str) -> dict:
        return {
            "hashtags": [],
            "best_posting_windows": [],
            "heat_score": 0.0,
            "heat_label": "low",
            "reasons": [],
        }


class ApiTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.upstream_client = FakeUpstreamClient()
        self.llm_client = FakeLLMClient()
        settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{self.temp_dir.name}/mvp.db",
            openai_api_key="test-key",
            log_enable_file=False,
        )
        self.settings = settings
        db = Database(settings.database_path)
        db.init()
        db.add_allowed_username("demo-user")
        db.add_allowed_username("missing-user")
        content_orchestrator = ContentOrchestrator(
            settings=settings,
            database=db,
            llm=self.llm_client,
            web_enricher=FakeWebEnricher(),
        )
        self.client = TestClient(
            create_app(
                settings,
                upstream_client=self.upstream_client,
                llm_client=self.llm_client,
                content_orchestrator=content_orchestrator,
            )
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ingest_profile_then_generate_drafts(self) -> None:
        ingest_response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user"},
        )
        self.assertEqual(ingest_response.status_code, 200)
        ingest_payload = ingest_response.json()
        self.assertEqual(ingest_payload["fetched_tweet_count"], self.settings.max_ingest_tweets)
        self.assertEqual(ingest_payload["profile"]["username"], "demo-user")
        self.assertEqual(self.upstream_client.last_max_tweets, self.settings.max_ingest_tweets)
        self.assertEqual(ingest_payload["persona"]["language_profile"]["primary_language"], "en")
        self.assertEqual(ingest_payload["persona"]["topic_clusters"][0]["evidence_terms"], ["building", "lessons"])
        self.assertIn("posting_cadence", ingest_payload["persona"])
        self.assertIn("media_habits", ingest_payload["persona"])

        profile_response = self.client.get("/api/v1/profiles/demo-user")
        self.assertEqual(profile_response.status_code, 200)
        self.assertEqual(profile_response.json()["stored_tweet_count"], self.settings.max_ingest_tweets)

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

    def test_ingest_uses_server_side_max_tweets(self) -> None:
        response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.upstream_client.last_max_tweets, self.settings.max_ingest_tweets)
        self.assertEqual(response.json()["fetched_tweet_count"], self.settings.max_ingest_tweets)

    def test_generate_drafts_uses_bounded_history_window(self) -> None:
        ingest_response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user"},
        )
        self.assertEqual(ingest_response.status_code, 200)

        response = self.client.post(
            "/api/v1/drafts/generate",
            json={"username": "demo-user", "prompt": "Talk about focus", "draft_count": 2},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.llm_client.last_source_text_count, self.settings.max_ingest_tweets)
        self.assertEqual(self.llm_client.last_tweet_row_count, self.settings.max_ingest_tweets)

    def test_generate_drafts_requires_ingest_first(self) -> None:
        response = self.client.post(
            "/api/v1/drafts/generate",
            json={"username": "missing-user", "prompt": "Talk about focus", "draft_count": 3},
        )
        self.assertEqual(response.status_code, 404)

    def test_persona_routes_reject_non_whitelisted_username(self) -> None:
        ingest_response = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "elonmusk"},
        )
        self.assertEqual(ingest_response.status_code, 403)
        self.assertEqual(ingest_response.json()["detail"], "Target username is not in the trial whitelist")

        profile_response = self.client.get("/api/v1/profiles/elonmusk")
        self.assertEqual(profile_response.status_code, 403)

        drafts_response = self.client.post(
            "/api/v1/drafts/generate",
            json={"username": "elonmusk", "prompt": "Talk about focus", "draft_count": 2},
        )
        self.assertEqual(drafts_response.status_code, 403)

        content_response = self.client.post(
            "/api/v1/content/generate",
            json={
                "username": "elonmusk",
                "mode": "A",
                "idea": "Talk about rockets",
                "topic": "rockets",
                "draft_count": 1,
            },
        )
        self.assertEqual(content_response.status_code, 403)

        exposure_response = self.client.post(
            "/api/v1/exposure/analyze",
            json={
                "username": "elonmusk",
                "text": "Rockets are hard",
                "topic": "rockets",
                "domain": "space",
            },
        )
        self.assertEqual(exposure_response.status_code, 403)

    def test_admin_whitelist_endpoints_manage_allowed_usernames(self) -> None:
        initial = self.client.get("/admin/api/v1/whitelist/usernames")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["usernames"], ["demo-user", "missing-user"])

        added = self.client.post(
            "/admin/api/v1/whitelist/usernames",
            json={"username": "  ElonMusk  "},
        )
        self.assertEqual(added.status_code, 200)
        self.assertEqual(added.json()["usernames"], ["demo-user", "elonmusk", "missing-user"])

        removed = self.client.delete("/admin/api/v1/whitelist/usernames/ELONMUSK")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["usernames"], ["demo-user", "missing-user"])

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
            json={"username": "demo-user"},
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

    def test_openapi_omits_ingest_max_tweets(self) -> None:
        response = self.client.get("/openapi.json")

        self.assertEqual(response.status_code, 200)
        schema = response.json()["components"]["schemas"]["ProfileIngestRequest"]
        self.assertEqual(set(schema["properties"].keys()), {"username"})
        self.assertNotIn("max_tweets", schema["properties"])

    def test_content_ideas_generate_exposure_and_debug_endpoints(self) -> None:
        ingest = self.client.post(
            "/api/v1/profiles/ingest",
            json={"username": "demo-user"},
        )
        self.assertEqual(ingest.status_code, 200)

        ideas = self.client.post(
            "/api/v1/content/ideas",
            json={"direction": "crypto", "domain": "ai", "topic_hint": "binance", "limit": 3},
        )
        self.assertEqual(ideas.status_code, 200)
        self.assertIn("ideas", ideas.json())

        generated = self.client.post(
            "/api/v1/content/generate",
            json={
                "username": "demo-user",
                "mode": "A",
                "idea": "Share thoughts about Binance winners list",
                "topic": "Binance winners",
                "keywords": ["Binance", "winners"],
                "draft_count": 2,
            },
        )
        self.assertEqual(generated.status_code, 200)
        payload = generated.json()
        self.assertIn("request_id", payload)
        self.assertIn("score", payload)
        self.assertIn("quality_gate_met", payload)
        self.assertIn("quality_gate_reason", payload)
        self.assertEqual(len(payload["drafts"]), 2)
        self.assertIn("variants", payload)
        self.assertEqual(len(payload["variants"]), 3)
        self.assertEqual(
            {item["variant"] for item in payload["variants"]},
            {"normal", "expansion", "open"},
        )
        self.assertIn("recommended_variant", payload)
        self.assertIn(payload["recommended_variant"], {"normal", "expansion", "open"})

        recommended = next(item for item in payload["variants"] if item["variant"] == payload["recommended_variant"])
        self.assertEqual(payload["drafts"], recommended["drafts"])
        self.assertEqual(payload["formatted_drafts"], recommended["formatted_drafts"])
        self.assertEqual(payload["score"], recommended["score"])
        self.assertIn("quality_gate_reason", recommended)
        self.assertIn("compensation_used", recommended)

        exposure = self.client.post(
            "/api/v1/exposure/analyze",
            json={
                "username": "demo-user",
                "text": payload["drafts"][0]["text"],
                "topic": "Binance winners",
                "domain": "crypto",
            },
        )
        self.assertEqual(exposure.status_code, 200)
        self.assertIn("heat_score", exposure.json())

        debug = self.client.get(f"/api/v1/content/debug/{payload['request_id']}")
        self.assertEqual(debug.status_code, 200)
        self.assertEqual(debug.json()["request_id"], payload["request_id"])
        self.assertIn("variants", debug.json())

    def test_content_generate_returns_409_when_persona_snapshot_is_missing_before_save(self) -> None:
        temp_dir = tempfile.TemporaryDirectory()
        try:
            settings = Settings(
                app_env="test",
                database_url=f"sqlite:///{temp_dir.name}/mvp.db",
                openai_api_key="test-key",
                log_enable_file=False,
            )
            database = Database(settings.database_path)
            database.init()
            database.add_allowed_username("demo-user")
            database.upsert_user(
                {
                    "id": "u-1",
                    "username": "demo-user",
                    "name": "Test User",
                    "description": "",
                    "location": "",
                    "url": "",
                    "verified": False,
                    "public_metrics": {"followers_count": 1, "following_count": 1, "tweet_count": 1},
                },
                "2026-03-31T00:00:00+00:00",
            )
            client = TestClient(
                create_app(
                    settings,
                    upstream_client=FakeUpstreamClient(),
                    llm_client=self.llm_client,
                    content_orchestrator=FakeContentOrchestrator(),  # type: ignore[arg-type]
                )
            )

            response = client.post(
                "/api/v1/content/generate",
                json={
                    "username": "demo-user",
                    "mode": "A",
                    "idea": "Share thoughts about BTC momentum",
                    "topic": "BTC momentum",
                    "keywords": ["BTC"],
                    "draft_count": 1,
                },
            )

            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["detail"], "Persona not found. Run /api/v1/profiles/ingest first")
        finally:
            temp_dir.cleanup()


if __name__ == "__main__":
    unittest.main()
