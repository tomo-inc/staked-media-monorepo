from __future__ import annotations

import tempfile
import threading
import time
import unittest
from datetime import UTC, datetime

from app.config import Settings
from app.database import Database
from app.orchestrator import ContentOrchestrator
from app.schemas import ContentGenerateRequest, TrendingGenerateRequest


class FakeLLM:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.calls = 0
        self.translation_overrides: dict[str, dict[str, str]] = {}

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

    def translate_hot_events_batch(
        self,
        *,
        items: dict[str, dict[str, str]],
        target_language: str,
        request_id: str | None = None,
    ) -> dict[str, dict[str, str]]:
        if self.translation_overrides:
            return dict(self.translation_overrides)
        return {
            str(event_id): {
                "title_translated": str(item.get("title") or ""),
                "summary_translated": str(item.get("summary") or ""),
            }
            for event_id, item in items.items()
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


class FakeHotEventsService:
    def __init__(self) -> None:
        self.calls = 0
        self.latest_refresh = False
        self.should_fail = False
        self.error_message = "provider unavailable"
        self.published_at = (datetime.now(UTC).replace(microsecond=0)).isoformat()
        self.block_refresh = False
        self.refresh_started = threading.Event()
        self.release_refresh = threading.Event()

    def list_hot_events(self, *, hours: int, limit: int, refresh: bool) -> dict:
        self.calls += 1
        self.latest_refresh = refresh
        if self.should_fail:
            raise RuntimeError(self.error_message)
        if refresh and self.block_refresh:
            self.refresh_started.set()
            if not self.release_refresh.wait(timeout=2.0):
                raise RuntimeError("timed out waiting for refresh release")
        items = [
            {
                "id": "web3::event-1",
                "title": "Bitcoin ETF flow spikes",
                "summary": "ETF inflow jumps in the past 24 hours.",
                "url": "https://example.com/etf",
                "source": "Example News",
                "source_domain": "example.com",
                "published_at": self.published_at,
                "relative_age_hint": "2h ago",
                "heat_score": 96.0,
                "category": "web3",
                "subcategory": "",
                "content_type": "news",
                "author_handle": "",
            }
        ][:limit]
        return {
            "items": items,
            "warnings": [],
            "source_status": {
                "opennews": {"status": "ok", "count": len(items), "error": ""},
                "opentwitter": {"status": "ok", "count": 0, "error": ""},
            },
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
        self.database = Database(self.settings.database.url)
        self.database.init()
        self.llm = FakeLLM()
        self.web = FakeWebEnricher()
        self.hot = FakeHotEventsService()
        self.orchestrator = ContentOrchestrator(
            settings=self.settings,
            database=self.database,
            llm=self.llm,  # type: ignore[arg-type]
            web_enricher=self.web,  # type: ignore[arg-type]
            hot_events_service=self.hot,  # type: ignore[arg-type]
        )

        now = datetime.now(UTC).replace(microsecond=0).isoformat()
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
                {
                    "id": "t-1",
                    "text": "Binance AI Pro updates and winners list discussion",
                    "created_at": "2026-03-30T10:00:00+00:00",
                }
            ],
            persona={
                "persona_version": "v1",
                "author_summary": "demo",
                "voice_traits": ["direct"],
                "topic_clusters": [],
                "writing_patterns": {
                    "avg_sentence_length": "short",
                    "punctuation_habits": [],
                    "paragraph_structure": "single-shot",
                    "code_switching_style": "",
                    "emoji_usage": "none",
                },
                "lexical_markers": ["community"],
                "do_not_sound_like": [],
                "cta_style": "ask",
                "generation_guardrails": {},
                "risk_notes": [],
                "language_profile": {
                    "primary_language": "en",
                    "secondary_languages": [],
                    "mixing_pattern": "none",
                    "mixing_notes": "",
                },
                "domain_expertise": [],
                "emotional_baseline": {
                    "default_valence": "neutral",
                    "intensity": "moderate",
                    "sarcasm_level": "none",
                    "humor_style": "",
                },
                "audience_profile": {
                    "primary_audience": "community",
                    "assumed_knowledge": [],
                    "formality": "casual",
                },
                "interaction_style": {
                    "original_post_tone": "direct",
                    "reply_tone": "",
                    "quote_tone": "",
                    "engagement_triggers": [],
                },
                "posting_cadence": {
                    "avg_daily_tweets": 2.0,
                    "posting_style": "steady",
                    "preferred_post_length": "short",
                    "active_windows_utc": [10],
                },
                "media_habits": {
                    "text_only_ratio": 1.0,
                    "link_ratio": 0.0,
                    "media_attachment_ratio": 0.0,
                    "dominant_format": "text-only",
                    "notes": "",
                },
                "geo_context": {
                    "declared_location": "",
                    "region_hint": "unknown",
                    "timezone_hint": "unknown",
                    "confidence": "low",
                    "notes": "",
                },
                "stance_patterns": {
                    "hot_take_style": "mixed",
                    "controversy_posture": "mixed",
                    "endorsement_style": "selective",
                    "notes": "",
                },
                "banned_phrases": [],
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

    def test_list_hot_events_uses_service_and_returns_payload(self) -> None:
        payload = self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)
        self.assertEqual(payload["hours"], 24)
        self.assertEqual(payload["count"], 1)
        self.assertEqual(payload["items"][0]["id"], "web3::event-1")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(payload["source_status"]["opennews"]["status"], "ok")
        self.assertFalse(payload["is_stale"])
        self.assertEqual(payload["last_refresh_error"], "")
        self.assertFalse(payload["refreshing"])
        self.assertEqual(self.hot.calls, 1)
        self.assertTrue(self.hot.latest_refresh)

    def test_list_hot_events_reads_stored_items_without_re_fetching(self) -> None:
        first = self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)
        second = self.orchestrator.list_hot_events(hours=24, limit=20, refresh=False)

        self.assertEqual(first["items"][0]["id"], "web3::event-1")
        self.assertEqual(second["items"][0]["id"], "web3::event-1")
        self.assertEqual(self.hot.calls, 1)
        self.assertEqual(second["warnings"], [])
        self.assertEqual(second["source_status"]["opennews"]["status"], "ok")
        self.assertFalse(second["refreshing"])

    def test_list_hot_events_returns_stored_items_after_refresh_failure(self) -> None:
        self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)
        self.hot.should_fail = True

        payload = self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)

        self.assertEqual(payload["count"], 1)
        self.assertFalse(payload["is_stale"])
        self.assertTrue(payload["throttled"])
        self.assertGreater(payload["next_refresh_available_in_seconds"], 0)
        self.assertEqual(payload["last_refresh_error"], "")
        self.assertEqual(payload["items"][0]["id"], "web3::event-1")
        self.assertEqual(payload["warnings"], [])
        self.assertEqual(self.hot.calls, 1)

    def test_list_hot_events_returns_immediately_while_refresh_is_in_progress(self) -> None:
        self.hot.block_refresh = True
        worker = threading.Thread(
            target=self.orchestrator.refresh_hot_events_snapshot,
            kwargs={"hours": 24, "limit": 20},
            daemon=True,
        )
        worker.start()
        self.assertTrue(self.hot.refresh_started.wait(timeout=1.0))

        started_at = time.monotonic()
        payload = self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)
        elapsed_seconds = time.monotonic() - started_at

        self.assertLess(elapsed_seconds, 0.2)
        self.assertTrue(payload["refreshing"])
        self.assertFalse(payload["throttled"])
        self.assertEqual(payload["count"], 0)
        self.assertEqual(payload["items"], [])
        self.assertEqual(self.hot.calls, 1)

        self.hot.release_refresh.set()
        worker.join(timeout=1.0)
        self.assertFalse(worker.is_alive())

    def test_refresh_hot_events_skips_persisting_no_op_translations(self) -> None:
        self.orchestrator.refresh_hot_events_snapshot(hours=24, limit=20, language="zh-CN")

        translations = self.database.get_hot_event_translations(["web3::event-1"], "zh-CN")

        self.assertEqual(translations, {})

    def test_refresh_hot_events_persists_real_translations_only(self) -> None:
        self.llm.translation_overrides = {
            "web3::event-1": {
                "title_translated": "比特币 ETF 资金流激增",
                "summary_translated": "过去 24 小时 ETF 流入明显上升。",
            },
            "unexpected-event": {
                "title_translated": "unexpected",
                "summary_translated": "unexpected",
            },
        }

        payload = self.orchestrator.refresh_hot_events_snapshot(hours=24, limit=20, language="zh-CN")
        translations = self.database.get_hot_event_translations(["web3::event-1"], "zh-CN")

        self.assertIn("web3::event-1", translations)
        self.assertEqual(
            translations["web3::event-1"]["title_translated"],
            "比特币 ETF 资金流激增",
        )
        self.assertEqual(payload["items"][0]["title_translated"], "比特币 ETF 资金流激增")
        self.assertTrue(payload["items"][0]["is_translated"])

    def test_generate_trending_content_uses_mode_b_and_selected_event(self) -> None:
        self.orchestrator.list_hot_events(hours=24, limit=20, refresh=True)
        payload = TrendingGenerateRequest(
            username="demo",
            event_id="web3::event-1",
            comment="I think this may trigger rotation into large caps.",
            draft_count=2,
        )
        result = self.orchestrator.generate_trending_content(payload, request_id="req-conv-1")
        self.assertEqual(result["request_id"], "req-conv-1")
        self.assertEqual(result["mode"], "B")
        self.assertEqual(result["topic"], "Bitcoin ETF flow spikes")
        self.assertEqual(len(result["drafts"]), 2)


if __name__ == "__main__":
    unittest.main()
