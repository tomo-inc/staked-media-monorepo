from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timezone

from app.config import Settings
from app.database import Database
from app.orchestrator import ContentOrchestrator
from app.schemas import ContentGenerateRequest


class FakeLLM:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0

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
        with self._lock:
            self.calls += 1
            call_number = self.calls
        best_score = 8.3 if call_number == 1 else 9.4
        return {
            "drafts": [
                {
                    "text": f"draft {index} about topic",
                    "tone_tags": ["direct"],
                    "rationale": "fit",
                }
                for index in range(draft_count)
            ],
            "best_score": best_score,
            "target_score_met": best_score >= 9.0,
        }


class FakeWebEnricher:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0

    def search_recent_topic_signals(self, topic: str, keywords: list[str]) -> dict:
        with self._lock:
            self.calls += 1
        return {
            "keywords": [topic, "related", "breaking"],
            "facts": [
                {
                    "title": f"{topic} update",
                    "summary": "new development",
                    "source": "test",
                    "url": "https://example.com",
                    "published_at": "2026-03-31T00:00:00+00:00",
                }
            ],
            "items": [],
        }


class OrchestratorTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.settings = Settings(
            app_env="test",
            database_url=f"sqlite:///{self.temp_dir.name}/mvp.db",
            openai_api_key="test-key",
            log_enable_file=False,
            content_rewrite_max_rounds=3,
        )
        self.database = Database(self.settings.database_path)
        self.database.init()
        self.llm = FakeLLM()
        self.web = FakeWebEnricher()
        self.orchestrator = ContentOrchestrator(
            settings=self.settings,
            database=self.database,
            llm=self.llm,  # type: ignore[arg-type]
            web_enricher=self.web,  # type: ignore[arg-type]
        )

        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        user = {
            "id": "u-1",
            "username": "demo",
            "name": "Demo",
            "description": "",
            "location": "",
            "url": "",
            "verified": False,
            "public_metrics": {"followers_count": 10, "following_count": 5, "tweet_count": 3},
        }
        self.database.upsert_user(user, now)
        tweets = [
            {
                "data": {
                    "id": "t-1",
                    "text": "Binance AI Pro updates and winners list discussion",
                    "created_at": "2026-03-30T10:00:00+00:00",
                    "lang": "en",
                    "public_metrics": {"like_count": 10, "retweet_count": 2, "reply_count": 1, "quote_count": 0},
                    "referenced_tweets": [],
                }
            },
            {
                "data": {
                    "id": "t-2",
                    "text": "Community-first launch cadence always matters",
                    "created_at": "2026-03-29T10:00:00+00:00",
                    "lang": "en",
                    "public_metrics": {"like_count": 8, "retweet_count": 1, "reply_count": 1, "quote_count": 0},
                    "referenced_tweets": [],
                }
            },
        ]
        self.database.upsert_tweets("u-1", tweets, now)
        self.database.save_persona_snapshot(
            user_id="u-1",
            username="demo",
            source_tweet_count=2,
            source_original_tweet_count=2,
            source_window_start="2026-03-29T10:00:00+00:00",
            source_window_end="2026-03-30T10:00:00+00:00",
            corpus_stats={"tweet_counts": {"total": 2, "original": 2}},
            representative_tweets=[
                {"id": "t-1", "text": "Binance AI Pro updates and winners list discussion", "created_at": "2026-03-30T10:00:00+00:00"}
            ],
            persona={
                "persona_version": "v1",
                "author_summary": "demo",
                "voice_traits": ["direct"],
                "topic_clusters": [],
                "writing_patterns": {},
                "lexical_markers": ["community"],
                "do_not_sound_like": [],
                "cta_style": "ask",
                "generation_guardrails": {},
                "risk_notes": [],
            },
            created_at=now,
        )

    def tearDown(self) -> None:
        try:
            self.temp_dir.cleanup()
        except PermissionError:
            pass

    def test_generate_content_uses_web_fallback_and_rewrite(self) -> None:
        payload = ContentGenerateRequest(
            username="demo",
            mode="A",
            topic="OpenClaw winners",
            idea="Share a short take",
            keywords=["OpenClaw"],
            draft_count=2,
        )
        result = self.orchestrator.generate_content(payload, request_id="req-1")

        self.assertEqual(result["request_id"], "req-1")
        self.assertEqual(len(result["drafts"]), 2)
        self.assertTrue(result["web_enrichment_used"])
        self.assertGreaterEqual(self.web.calls, 1)
        self.assertGreaterEqual(self.llm.calls, 2)
        self.assertIn("score", result)
        self.assertIn("final_score", result["score"])
        self.assertIn("quality_gate_met", result)
        self.assertIn("quality_gate_reason", result)
        self.assertIn("variants", result)
        self.assertEqual(len(result["variants"]), 3)
        self.assertEqual(
            {item["variant"] for item in result["variants"]},
            {"normal", "expansion", "open"},
        )
        self.assertIn("recommended_variant", result)
        self.assertIn(result["recommended_variant"], {"normal", "expansion", "open"})

        recommended = next(item for item in result["variants"] if item["variant"] == result["recommended_variant"])
        self.assertEqual(result["drafts"], recommended["drafts"])
        self.assertEqual(result["formatted_drafts"], recommended["formatted_drafts"])
        self.assertEqual(result["score"], recommended["score"])

        for variant in result["variants"]:
            self.assertIn("score", variant)
            self.assertIn("retry_count", variant)
            self.assertIn("quality_gate_reason", variant)
            self.assertIn("compensation_used", variant)
            self.assertIn("used_keywords", variant)
            self.assertIn("source_facts", variant)

    def test_generate_content_raises_lookup_error_when_no_rounds_can_run(self) -> None:
        orchestrator = ContentOrchestrator(
            settings=Settings(
                app_env="test",
                database_url=f"sqlite:///{self.temp_dir.name}/mvp.db",
                openai_api_key="test-key",
                log_enable_file=False,
                content_rewrite_max_rounds=0,
            ),
            database=self.database,
            llm=self.llm,  # type: ignore[arg-type]
            web_enricher=self.web,  # type: ignore[arg-type]
        )

        payload = ContentGenerateRequest(
            username="demo",
            mode="A",
            topic="OpenClaw winners",
            idea="Share a short take",
            keywords=["OpenClaw"],
            draft_count=2,
        )

        with self.assertRaisesRegex(LookupError, "could not produce any draft candidates"):
            orchestrator.generate_content(payload, request_id="req-empty")

    def test_suggest_ideas_and_exposure_outputs_structured_payload(self) -> None:
        ideas = self.orchestrator.suggest_ideas(direction="crypto", domain="ai", topic_hint="binance", limit=5)
        self.assertIn("ideas", ideas)
        self.assertIn("query", ideas)

        exposure = self.orchestrator.analyze_exposure(
            username="demo",
            text="Binance winners list is out, what do you think?",
            topic="Binance winners",
            domain="crypto",
        )
        self.assertIn("hashtags", exposure)
        self.assertIn("best_posting_windows", exposure)
        self.assertIn("heat_score", exposure)


if __name__ == "__main__":
    unittest.main()
