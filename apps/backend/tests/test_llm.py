from __future__ import annotations

import json
import unittest
from unittest.mock import patch

import app.llm as llm_module
from app.config import Settings
from app.llm import GeminiClient, LLMError, OpenAIClient, create_llm_client


class FakeResponse:
    def __init__(self, *, status_code: int = 200, json_body=None, text: str = "") -> None:
        self.status_code = status_code
        self._json_body = json_body or {}
        self.text = text

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            import requests

            error = requests.HTTPError(f"HTTP {self.status_code}")
            error.response = self
            raise error

    def json(self):
        return self._json_body


# Reusable JSON fixture strings for mock LLM responses
_SCORE_STRONG_FIT = '{"score": 9.1, "verdict": "strong_fit", "strengths": ["native"], "issues": [], "must_fix": []}'
_SCORE_FIT_88 = '{"score": 8.8, "verdict": "fit", "strengths": [], "issues": [], "must_fix": []}'
_SCORE_FIT_86 = '{"score": 8.6, "verdict": "fit", "strengths": [], "issues": [], "must_fix": []}'
_SCORE_FIT_91 = '{"score": 9.1, "verdict": "fit", "strengths": [], "issues": [], "must_fix": []}'
_SCORE_OK_90 = '{"score": 9.0, "verdict": "ok", "strengths": [], "issues": [], "must_fix": []}'
_SCORE_FIT_94_LIST = '[{"score": 9.4, "verdict": "fit", "strengths": ["native"], "issues": [], "must_fix": []}]'
_DRAFTS_WTDD = '{"drafts": [{"text": "WTDD 今天很强", "tone_tags": ["direct"], "rationale": "ok"}]}'


class LlmNormalizationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.client = OpenAIClient(Settings(openai_api_key="test-key"))

    def test_normalize_persona_payload_coerces_model_friendly_shapes(self) -> None:
        payload = {
            "persona_version": 1.0,
            "author_summary": "Builder voice",
            "voice_traits": ["direct", "operator-minded"],
            "topic_clusters": [{"topic": "adoption", "evidence_terms": ["growth"]}],
            "writing_patterns": ["short punchy lines", "mission-driven essays"],
            "lexical_markers": ["mass adoption"],
            "do_not_sound_like": "corporate PR",
            "cta_style": {
                "overall": "Light CTA usage",
                "common_forms": ["link drop", "future-facing statement"],
            },
            "generation_guardrails": {
                "preferred_openings": ["scene-first", "reaction-first"],
                "preferred_formats": "short observation",
                "compression_rules": ["one sharp point then stop"],
                "anti_patterns": ["polished symmetry"],
                "language_notes": "natural CN-EN code-switching only",
            },
            "risk_notes": "Public-post inference only",
            "language_profile": {
                "primary": "ZH",
                "secondary": "EN",
                "code_switch_style": "term-only",
                "notes": "technical terms in EN",
            },
            "domain_expertise": {
                "domain": "crypto",
                "level": "expert",
                "examples": "AMM",
            },
            "emotional_baseline": {"dominant": "mixed", "sarcasm": "frequent"},
            "audience_profile": {"type": "crypto-native peers", "knowledge": "MEV", "formality": "raw"},
            "interaction_style": {"original_tone": "blunt", "topics": ["breaking news"]},
            "posting_cadence": {
                "avg_daily_tweets": "6",
                "style": "burst-poster",
                "length_preference": "short",
                "active_hours": ["9", "10"],
            },
            "media_habits": {
                "text_only_ratio": "0.2",
                "link_ratio": "0.1",
                "media_attachment_ratio": "0.7",
                "format": "media-led",
                "notes": "usually screenshot captions",
            },
            "banned_phrases": "gm ser",
        }

        normalized = self.client._normalize_persona_payload(payload)

        self.assertEqual(normalized["persona_version"], "v1")
        self.assertEqual(normalized["writing_patterns"]["avg_sentence_length"], "medium")
        self.assertEqual(normalized["writing_patterns"]["punctuation_habits"][0], "short punchy lines")
        self.assertEqual(normalized["do_not_sound_like"], ["corporate PR"])
        self.assertIn("Light CTA usage", normalized["cta_style"])
        self.assertEqual(
            normalized["generation_guardrails"]["preferred_formats"],
            ["short observation"],
        )
        self.assertEqual(
            normalized["generation_guardrails"]["language_notes"],
            ["natural CN-EN code-switching only"],
        )
        self.assertEqual(normalized["language_profile"]["primary_language"], "zh")
        self.assertEqual(normalized["language_profile"]["secondary_languages"], ["en"])
        self.assertEqual(normalized["language_profile"]["mixing_pattern"], "term-only")
        self.assertEqual(normalized["domain_expertise"][0]["jargon_examples"], ["AMM"])
        self.assertEqual(normalized["emotional_baseline"]["sarcasm_level"], "frequent")
        self.assertEqual(normalized["audience_profile"]["formality"], "raw")
        self.assertEqual(normalized["interaction_style"]["engagement_triggers"], ["breaking news"])
        self.assertEqual(normalized["posting_cadence"]["avg_daily_tweets"], 6.0)
        self.assertEqual(normalized["posting_cadence"]["active_windows_utc"], [9, 10])
        self.assertEqual(normalized["media_habits"]["dominant_format"], "media-led")
        self.assertEqual(normalized["media_habits"]["notes"], "usually screenshot captions")
        self.assertEqual(normalized["banned_phrases"], ["gm ser"])

    def test_normalize_drafts_payload_accepts_string_items(self) -> None:
        payload = {"drafts": ["One clear post", {"draft": "Second clear post", "tags": "direct"}]}

        normalized = self.client._normalize_drafts_payload(payload)

        self.assertEqual(len(normalized["drafts"]), 2)
        self.assertEqual(normalized["drafts"][0]["text"], "One clear post")
        self.assertEqual(normalized["drafts"][1]["tone_tags"], ["direct"])

    def test_normalize_drafts_payload_accepts_top_level_list(self) -> None:
        payload = [
            "One clear post",
            {"draft": "Second clear post", "tags": "direct"},
        ]

        normalized = self.client._normalize_drafts_payload(payload)

        self.assertEqual(len(normalized["drafts"]), 2)
        self.assertEqual(normalized["drafts"][0]["text"], "One clear post")
        self.assertEqual(normalized["drafts"][1]["tone_tags"], ["direct"])

    def test_normalize_score_payload_rejects_top_level_list(self) -> None:
        with self.assertRaisesRegex(LLMError, "Score schema validation failed"):
            self.client._normalize_score_payload(
                [{"score": 9.0, "verdict": "fit"}],
                request_id="score-list",
            )

    def test_build_draft_request_payload_uses_guardrails_and_language_matching(self) -> None:
        payload = self.client._build_draft_request_payload(
            persona={
                "author_summary": "Timeline-native bilingual poster",
                "voice_traits": ["casual", "meme-aware"],
                "lexical_markers": ["gm frens", "timeline"],
                "do_not_sound_like": ["essay"],
                "writing_patterns": {
                    "avg_sentence_length": "short",
                    "paragraph_structure": "single-shot",
                },
                "language_profile": {
                    "primary_language": "zh",
                    "secondary_languages": ["en"],
                    "mixing_pattern": "term-only",
                    "mixing_notes": "technical terms in EN",
                },
                "emotional_baseline": {
                    "default_valence": "neutral",
                    "intensity": "moderate",
                    "sarcasm_level": "occasional",
                },
                "audience_profile": {
                    "primary_audience": "crypto-native peers",
                    "assumed_knowledge": ["DeFi"],
                    "formality": "casual",
                },
                "interaction_style": {
                    "original_post_tone": "blunt",
                    "reply_tone": "supportive",
                    "quote_tone": "one-line take",
                },
                "posting_cadence": {
                    "avg_daily_tweets": 6.0,
                    "posting_style": "burst-poster",
                    "preferred_post_length": "short",
                    "active_windows_utc": [9, 10],
                },
                "media_habits": {
                    "text_only_ratio": 0.8,
                    "link_ratio": 0.1,
                    "media_attachment_ratio": 0.1,
                    "dominant_format": "text-only",
                    "notes": "mostly standalone text",
                },
                "generation_guardrails": {
                    "preferred_openings": ["scene-first"],
                    "compression_rules": ["leave some implication unstated"],
                    "anti_patterns": ["generic summary language"],
                },
            },
            prompt="Talk about WTDD with the same punchy tone",
            representative_tweets=[{"text": "gm frens"}],
            matched_theme_tweets=[{"text": "WTDD meme energy", "match_terms": ["WTDD"]}],
            theme_keywords=["WTDD"],
            theme_top_keywords=["meme", "energy"],
            rejected_texts=["Too polished"],
            attempt_feedback=["Avoid generic summary language"],
            draft_count=4,
        )

        self.assertEqual(payload["constraints"]["draft_count"], 4)
        self.assertIn("Default to zh", payload["constraints"]["language_mode"])
        self.assertFalse(payload["constraints"]["full_chinese_only"])
        self.assertEqual(payload["style_brief"]["posting_cadence"]["posting_style"], "burst-poster")
        self.assertEqual(payload["style_brief"]["media_habits"]["dominant_format"], "text-only")
        self.assertEqual(
            payload["style_brief"]["generation_guardrails"]["preferred_openings"],
            ["scene-first"],
        )
        self.assertEqual(payload["style_brief"]["language_profile"]["mixing_pattern"], "term-only")
        self.assertEqual(payload["style_brief"]["audience_profile"]["primary_audience"], "crypto-native peers")
        self.assertEqual(payload["theme_keywords"], ["WTDD"])
        self.assertEqual(payload["theme_top_keywords"], ["meme", "energy"])
        self.assertTrue(
            any(
                "one sharp observation is better than a fully explained argument" in rule
                for rule in payload["drafting_rules"]
            )
        )

    def test_build_draft_request_payload_full_chinese_prompt_overrides_persona_language_profile(self) -> None:
        payload = self.client._build_draft_request_payload(
            persona={
                "language_profile": {
                    "primary_language": "en",
                    "secondary_languages": ["zh"],
                    "mixing_pattern": "fluid",
                    "mixing_notes": "switches freely",
                },
                "generation_guardrails": {},
            },
            prompt="写一条关于WTDD的推文，全中文，不要夹英文。",
            representative_tweets=[{"text": "WTDD today"}],
            matched_theme_tweets=[{"text": "WTDD today", "match_terms": ["WTDD"]}],
            theme_keywords=["WTDD"],
            theme_top_keywords=["today"],
            rejected_texts=[],
            attempt_feedback=[],
            draft_count=2,
        )

        self.assertTrue(payload["constraints"]["full_chinese_only"])
        self.assertIn("Full-Chinese only", payload["constraints"]["language_mode"])
        self.assertEqual(payload["constraints"]["allowed_english_tokens"], ["wtdd"])

    def test_build_draft_request_payload_explicit_english_prompt_disables_full_chinese_mode(self) -> None:
        payload = self.client._build_draft_request_payload(
            persona={
                "language_profile": {
                    "primary_language": "zh",
                    "secondary_languages": ["en"],
                    "mixing_pattern": "term-only",
                    "mixing_notes": "keeps English to terms unless asked",
                },
                "generation_guardrails": {},
            },
            prompt="请用英语写一条关于BTC的推文",
            representative_tweets=[{"text": "BTC 先看结构"}],
            matched_theme_tweets=[{"text": "BTC reclaim is the only thing that matters", "match_terms": ["BTC"]}],
            theme_keywords=["BTC"],
            theme_top_keywords=["reclaim"],
            rejected_texts=[],
            attempt_feedback=[],
            draft_count=1,
        )

        self.assertFalse(payload["constraints"]["full_chinese_only"])
        self.assertIn("explicit English or bilingual request", payload["constraints"]["language_mode"])
        self.assertEqual(payload["constraints"]["allowed_english_tokens"], [])
        self.assertEqual(payload["user_prompt"], "请用英语写一条关于BTC的推文")

    def test_sanitize_prompt_for_full_chinese_mode_preserves_theme_english_tokens(self) -> None:
        sanitized = self.client._sanitize_prompt_for_full_chinese_mode(
            prompt="写一条关于BTC突破10万和DeFi复苏的推文，全中文，bullish 语气像Claude Code。",
            theme_keywords=["BTC", "DeFi", "Claude Code"],
            allowed_english_tokens=set(),
        )

        self.assertIn("BTC", sanitized)
        self.assertIn("DeFi", sanitized)
        self.assertIn("Claude", sanitized)
        self.assertIn("Code", sanitized)
        self.assertNotIn("bullish", sanitized.lower())
        self.assertIn("某工具", sanitized)

    def test_allowed_english_tokens_defaults_to_theme_keywords(self) -> None:
        allowed_tokens = self.client._allowed_english_tokens_for_full_chinese_prompt(
            prompt="写一条关于BTC和DeFi的全中文帖子。",
            theme_keywords=["BTC", "ETH"],
        )

        self.assertEqual(allowed_tokens, {"btc", "eth"})

    def test_rule_score_penalizes_low_frequency_lexical_markers(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": ["时间线"],
                "banned_phrases": [],
            },
            prompt="用我的口吻写一条全中文帖子，主题是PEPE今天上涨20%",
            candidate_text="PEPE今天这波把时间线又点着了",
            source_texts=["PEPE今天很强"],
            matched_theme_tweets=[{"text": "PEPE今天反弹，青蛙情绪起来了"}],
            theme_keywords=["PEPE", "上涨", "20%"],
            theme_top_keywords=["青蛙", "情绪", "反弹"],
        )

        self.assertLess(evaluation["score"], 10.0)
        self.assertTrue(any("Low-frequency topic drift phrase" in issue for issue in evaluation["issues"]))

    def test_rule_score_blocks_unrequested_english_in_full_chinese_mode(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
            },
            prompt="写一条推文，中文全部，不要一下中文一下英文。",
            candidate_text="这波结论很直接，meta层面没有秘密。",
            source_texts=["市场噪音很多，保持耐心更重要。"],
            matched_theme_tweets=[{"text": "这波更像标题党，不是实质突破。"}],
            theme_keywords=["源码", "泄露"],
            theme_top_keywords=["标题党", "逆向"],
        )

        self.assertLess(evaluation["score"], 6.0)
        self.assertTrue(
            any(issue.startswith("Contains English despite full-Chinese prompt") for issue in evaluation["issues"])
        )

    def test_rule_score_blocks_english_for_plain_chinese_prompt(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
            },
            prompt="写一条关于PEPE反弹的帖子。",
            candidate_text="PEPE rebound looks cleaner now.",
            source_texts=["PEPE这波先看量能。"],
            matched_theme_tweets=[{"text": "PEPE反弹的时候情绪会先回来。"}],
            theme_keywords=["PEPE"],
            theme_top_keywords=["反弹", "情绪"],
        )

        self.assertTrue(
            any(issue.startswith("Contains English despite full-Chinese prompt") for issue in evaluation["issues"])
        )

    def test_rule_score_allows_english_for_chinese_prompt_that_explicitly_requests_english(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
            },
            prompt="请用英语写一条关于BTC的推文",
            candidate_text="BTC reclaim looks clean here.",
            source_texts=["BTC 先看量能，再看结构。"],
            matched_theme_tweets=[{"text": "BTC reclaim looked strong last time."}],
            theme_keywords=["BTC"],
            theme_top_keywords=["reclaim", "strong"],
        )

        self.assertFalse(
            any(issue.startswith("Contains English despite full-Chinese prompt") for issue in evaluation["issues"])
        )

    def test_rule_score_penalizes_emotional_and_audience_mismatch(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
                "emotional_baseline": {"sarcasm_level": "frequent"},
                "audience_profile": {"formality": "raw"},
                "posting_cadence": {
                    "posting_style": "burst-poster",
                    "preferred_post_length": "short",
                },
                "media_habits": {"dominant_format": "text-only"},
            },
            prompt="写一条关于PEPE反弹的帖子。",
            candidate_text=(
                "PEPE这波走势值得耐心观察。第一，量能已经回来了。第二，情绪也在修复。"
                "第三，这里更像是一次结构性回升。详见链接。"
            ),
            source_texts=["PEPE这波还是先看量能。"],
            matched_theme_tweets=[{"text": "PEPE反弹的时候情绪会先回来。"}],
            theme_keywords=["PEPE"],
            theme_top_keywords=["反弹", "情绪"],
        )

        self.assertTrue(
            any(
                "Polish level is especially misaligned for this persona's casual audience" in issue
                for issue in evaluation["issues"]
            )
        )
        self.assertTrue(any("Draft lacks expected sarcasm for this persona" in issue for issue in evaluation["issues"]))
        self.assertTrue(
            any("Too complete for this persona's posting cadence" in issue for issue in evaluation["issues"])
        )
        self.assertTrue(
            any("Too link-forward for this persona's text-only habit" in issue for issue in evaluation["issues"])
        )

    def test_rule_score_penalizes_media_led_drafts_that_read_too_complete(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
                "media_habits": {"dominant_format": "media-led"},
            },
            prompt="Write about PEPE momentum",
            candidate_text=(
                "PEPE momentum is back in a visible way. First, participation broadened across the board. "
                "Second, the reaction function looked much cleaner than last week. Third, positioning now matters more."
            ),
            source_texts=["PEPE momentum is back"],
            matched_theme_tweets=[{"text": "PEPE momentum is back"}],
            theme_keywords=["PEPE"],
            theme_top_keywords=["momentum"],
        )

        self.assertTrue(
            any("Too self-contained for this persona's media-led habit" in issue for issue in evaluation["issues"])
        )

    def test_rule_score_penalizes_earnest_question_for_high_sarcasm_persona(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
                "emotional_baseline": {"sarcasm_level": "defining"},
            },
            prompt="Write about PEPE momentum",
            candidate_text="PEPE这波你觉得还能继续走吗？",
            source_texts=["PEPE这波有点意思。"],
            matched_theme_tweets=[{"text": "PEPE momentum is back", "match_terms": ["PEPE"]}],
            theme_keywords=["PEPE"],
            theme_top_keywords=["momentum"],
        )

        self.assertTrue(any("Draft lacks expected sarcasm for this persona" in issue for issue in evaluation["issues"]))

    def test_rule_score_penalizes_earnest_question_with_agreement_cue_for_high_sarcasm_persona(self) -> None:
        evaluation = self.client._rule_score_draft(
            persona={
                "lexical_markers": [],
                "banned_phrases": [],
                "emotional_baseline": {"sarcasm_level": "defining"},
            },
            prompt="Write about BTC structure",
            candidate_text="现在先等确认更合理，对吧？",
            source_texts=["这波先等确认，不急着追。"],
            matched_theme_tweets=[{"text": "BTC structure still needs confirmation", "match_terms": ["BTC"]}],
            theme_keywords=["BTC"],
            theme_top_keywords=["structure", "confirmation"],
        )

        self.assertTrue(any("Draft lacks expected sarcasm for this persona" in issue for issue in evaluation["issues"]))

    def test_rule_score_penalizes_earnest_sentences_with_generic_sarcasm_words(self) -> None:
        candidates = [
            "Right now BTC looks strong.",
            "Of course BTC needs volume confirmation.",
            "Sure BTC can keep grinding if bids hold.",
        ]

        for candidate_text in candidates:
            with self.subTest(candidate_text=candidate_text):
                evaluation = self.client._rule_score_draft(
                    persona={
                        "lexical_markers": [],
                        "banned_phrases": [],
                        "emotional_baseline": {"sarcasm_level": "defining"},
                    },
                    prompt="Write about BTC structure",
                    candidate_text=candidate_text,
                    source_texts=["BTC still needs confirmation."],
                    matched_theme_tweets=[{"text": "BTC structure still needs confirmation", "match_terms": ["BTC"]}],
                    theme_keywords=["BTC"],
                    theme_top_keywords=["BTC"],
                )

                self.assertTrue(
                    any("Draft lacks expected sarcasm for this persona" in issue for issue in evaluation["issues"])
                )

    def test_rule_score_allows_contextual_sarcasm_markers_for_high_sarcasm_persona(self) -> None:
        candidates = [
            "Yeah right, BTC just teleports through resistance.",
            "Sure, because BTC always rewards late longs.",
        ]

        for candidate_text in candidates:
            with self.subTest(candidate_text=candidate_text):
                evaluation = self.client._rule_score_draft(
                    persona={
                        "lexical_markers": [],
                        "banned_phrases": [],
                        "emotional_baseline": {"sarcasm_level": "defining"},
                    },
                    prompt="Write about BTC structure",
                    candidate_text=candidate_text,
                    source_texts=["BTC still needs confirmation."],
                    matched_theme_tweets=[{"text": "BTC structure still needs confirmation", "match_terms": ["BTC"]}],
                    theme_keywords=["BTC"],
                    theme_top_keywords=["BTC"],
                )

                self.assertFalse(
                    any("Draft lacks expected sarcasm for this persona" in issue for issue in evaluation["issues"])
                )

    def test_generate_drafts_full_chinese_falls_back_to_best_available_candidate(self) -> None:
        rule_result = {
            "score": 4.0,
            "passed": False,
            "hard_fail": False,
            "issues": ["Contains English despite full-Chinese prompt: btc"],
            "strengths": ["Theme keyword hits: BTC"],
        }
        with patch.object(
            self.client,
            "_chat_completion_json",
            return_value={"drafts": [{"text": "BTC这波继续观察", "tone_tags": ["direct"], "rationale": "ok"}]},
        ):
            with patch.object(
                self.client,
                "_rule_score_draft",
                return_value=rule_result,
            ):
                result = self.client.generate_drafts(
                    persona={"generation_guardrails": {}, "lexical_markers": [], "do_not_sound_like": []},
                    prompt="写一条关于BTC的推文，中文全部，不要一下中文一下英文。",
                    representative_tweets=[
                        {
                            "id": "rep-1",
                            "text": "BTC今天又新高了",
                            "created_at": "2026-03-30T00:00:00Z",
                            "engagement_score": 5,
                        }
                    ],
                    source_texts=["市场有波动，保持耐心。"],
                    tweet_rows=[
                        {
                            "id": "tweet-1",
                            "text": "BTC今天这波确实猛",
                            "created_at": "2026-03-30T00:00:00Z",
                            "is_retweet": False,
                            "is_reply": False,
                            "is_quote": False,
                            "retweet_count": 1,
                            "reply_count": 1,
                            "like_count": 1,
                            "quote_count": 0,
                        }
                    ],
                    draft_count=1,
                )

        self.assertEqual(len(result["drafts"]), 1)
        self.assertEqual(result["drafts"][0]["text"], "BTC这波继续观察")
        self.assertTrue(
            any(
                issue.startswith("Contains English despite full-Chinese prompt")
                for issue in result["evaluation"]["best_candidate"]["rule_issues"]
            )
        )

    def test_candidate_result_preserves_failure_reasons(self) -> None:
        candidate = self.client._candidate_result(
            text="Candidate text",
            tone_tags=["direct"],
            rationale="Why this failed",
            evaluation={
                "rule_score": 6.5,
                "llm_score": 7.0,
                "final_score": 6.5,
                "passed": False,
                "rule_issues": ["Misses the top keywords from matched historical tweets"],
                "llm_issues": ["Sounds slightly too polished"],
                "must_fix": ["Use more native wording"],
                "failure_reasons": [
                    "Misses the top keywords from matched historical tweets",
                    "Sounds slightly too polished",
                    "Use more native wording",
                ],
            },
        )

        self.assertEqual(candidate["final_score"], 6.5)
        self.assertFalse(candidate["passed"])
        self.assertEqual(len(candidate["failure_reasons"]), 3)

    def test_build_attempt_feedback_uses_flat_candidate_scores(self) -> None:
        attempt_candidates = [
            {
                "text": "Candidate one",
                "final_score": 8.6,
                "passed": False,
                "must_fix": ["Use more native wording"],
                "rule_issues": ["Too polished"],
            },
            {
                "text": "Candidate two",
                "final_score": 7.4,
                "passed": False,
                "must_fix": ["Hit theme keywords"],
                "rule_issues": ["Theme drift"],
            },
        ]

        feedback = self.client._build_attempt_feedback(attempt_candidates)
        best_score = max(float(item.get("final_score", 0.0)) for item in attempt_candidates)

        self.assertEqual(best_score, 8.6)
        self.assertEqual(feedback, ["Use more native wording"])


class ScoreDraftsBatchTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.settings = Settings(openai_api_key="test-key", llm_http_proxy="")
        self.client = OpenAIClient(self.settings)

    def test_batch_scores_multiple_candidates(self) -> None:
        batch_response = {
            "scores": [
                {"index": 0, "score": 9.0, "verdict": "good", "strengths": ["natural"], "issues": [], "must_fix": []},
                {
                    "index": 1,
                    "score": 7.5,
                    "verdict": "weak",
                    "strengths": [],
                    "issues": ["drift"],
                    "must_fix": ["fix"],
                },
            ]
        }
        with patch.object(self.client, "_chat_completion_json", return_value=batch_response) as mock_chat:
            results = self.client.score_drafts_batch(
                persona={
                    "author_summary": "",
                    "voice_traits": [],
                    "do_not_sound_like": [],
                    "generation_guardrails": {},
                    "language_profile": {"primary_language": "zh"},
                    "emotional_baseline": {"sarcasm_level": "occasional"},
                    "audience_profile": {"formality": "casual"},
                    "interaction_style": {"original_post_tone": "direct"},
                    "posting_cadence": {"posting_style": "steady"},
                    "media_habits": {"dominant_format": "text-only"},
                },
                prompt="test",
                candidate_texts=["候选A", "候选B"],
                matched_theme_tweets=[],
                theme_keywords=[],
                theme_top_keywords=[],
            )
        request_payload = json.loads(mock_chat.call_args.kwargs["user_prompt"])
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["score"], 9.0)
        self.assertEqual(results[1]["score"], 7.5)
        self.assertEqual(results[1]["issues"], ["drift"])
        self.assertIn("language_profile", request_payload["persona"])
        self.assertIn("emotional_baseline", request_payload["persona"])
        self.assertIn("audience_profile", request_payload["persona"])
        self.assertIn("interaction_style", request_payload["persona"])
        self.assertIn("posting_cadence", request_payload["persona"])
        self.assertIn("media_habits", request_payload["persona"])
        self.assertTrue(any("emotional register" in instruction for instruction in request_payload["instructions"]))
        self.assertTrue(any("interaction_style" in instruction for instruction in request_payload["instructions"]))

    def test_batch_returns_defaults_for_missing_indices(self) -> None:
        batch_response = {
            "scores": [
                {"index": 0, "score": 8.0, "verdict": "ok", "strengths": [], "issues": [], "must_fix": []},
            ]
        }
        with patch.object(self.client, "_chat_completion_json", return_value=batch_response):
            results = self.client.score_drafts_batch(
                persona={
                    "author_summary": "",
                    "voice_traits": [],
                    "do_not_sound_like": [],
                    "generation_guardrails": {},
                },
                prompt="test",
                candidate_texts=["候选A", "候选B", "候选C"],
                matched_theme_tweets=[],
                theme_keywords=[],
                theme_top_keywords=[],
            )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0]["score"], 8.0)
        self.assertEqual(results[1]["score"], 0.0)
        self.assertEqual(results[1]["verdict"], "missing")
        self.assertEqual(results[2]["score"], 0.0)

    def test_batch_handles_empty_candidates(self) -> None:
        results = self.client.score_drafts_batch(
            persona={},
            prompt="test",
            candidate_texts=[],
            matched_theme_tweets=[],
            theme_keywords=[],
            theme_top_keywords=[],
        )
        self.assertEqual(results, [])

    def test_batch_handles_malformed_llm_response(self) -> None:
        with patch.object(self.client, "_chat_completion_json", return_value={"unexpected": "shape"}):
            results = self.client.score_drafts_batch(
                persona={
                    "author_summary": "",
                    "voice_traits": [],
                    "do_not_sound_like": [],
                    "generation_guardrails": {},
                },
                prompt="test",
                candidate_texts=["候选A"],
                matched_theme_tweets=[],
                theme_keywords=[],
                theme_top_keywords=[],
            )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["score"], 0.0)
        self.assertEqual(results[0]["verdict"], "missing")

    def test_batch_handles_list_response(self) -> None:
        list_response = [
            {"index": 0, "score": 8.5, "verdict": "ok", "strengths": [], "issues": [], "must_fix": []},
        ]
        with patch.object(self.client, "_chat_completion_json", return_value=list_response):
            results = self.client.score_drafts_batch(
                persona={
                    "author_summary": "",
                    "voice_traits": [],
                    "do_not_sound_like": [],
                    "generation_guardrails": {},
                },
                prompt="test",
                candidate_texts=["候选A"],
                matched_theme_tweets=[],
                theme_keywords=[],
                theme_top_keywords=[],
            )
        self.assertEqual(results[0]["score"], 8.5)

    def test_batch_clamps_invalid_scores(self) -> None:
        batch_response = {
            "scores": [
                {"index": 0, "score": 15.0, "verdict": "ok", "strengths": [], "issues": [], "must_fix": []},
                {"index": 1, "score": -3.0, "verdict": "ok", "strengths": [], "issues": [], "must_fix": []},
                {"index": 2, "score": "not_a_number", "verdict": "ok", "strengths": [], "issues": [], "must_fix": []},
            ]
        }
        with patch.object(self.client, "_chat_completion_json", return_value=batch_response):
            results = self.client.score_drafts_batch(
                persona={
                    "author_summary": "",
                    "voice_traits": [],
                    "do_not_sound_like": [],
                    "generation_guardrails": {},
                },
                prompt="test",
                candidate_texts=["A", "B", "C"],
                matched_theme_tweets=[],
                theme_keywords=[],
                theme_top_keywords=[],
            )
        self.assertEqual(results[0]["score"], 10.0)
        self.assertEqual(results[1]["score"], 0.0)
        self.assertEqual(results[2]["score"], 0.0)


class ComputeFinalScoreTestCase(unittest.TestCase):
    def test_weighted_blend(self) -> None:
        from app.llm.base_client import LLMClient

        self.assertEqual(LLMClient._compute_final_score(7.5, 9.0), 8.4)
        self.assertEqual(LLMClient._compute_final_score(10.0, 10.0), 10.0)
        self.assertEqual(LLMClient._compute_final_score(0.0, 0.0), 0.0)
        self.assertEqual(LLMClient._compute_final_score(8.5, 9.0), 8.8)


class LlmProviderTestCase(unittest.TestCase):
    def test_settings_rejects_unknown_provider(self) -> None:
        with self.assertRaisesRegex(ValueError, "`llm_provider` must be one of"):
            Settings(llm_provider="not-a-provider")

    def test_settings_normalizes_provider(self) -> None:
        settings = Settings(llm_provider=" GEMINI ", gemini_api_key="k")

        self.assertEqual(settings.llm_provider, "gemini")

    def test_create_llm_client_returns_openai_by_default(self) -> None:
        client = create_llm_client(Settings(openai_api_key="test-key"))

        self.assertIsInstance(client, OpenAIClient)
        self.assertEqual(client.provider_name, "openai")

    def test_create_llm_client_returns_gemini_when_selected(self) -> None:
        client = create_llm_client(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
            )
        )

        self.assertIsInstance(client, GeminiClient)
        self.assertEqual(client.provider_name, "gemini")

    def test_public_exports_match_supported_api(self) -> None:
        self.assertEqual(
            set(llm_module.__all__),
            {
                "GeminiClient",
                "LLMClient",
                "LLMError",
                "LLMTransportError",
                "OpenAIClient",
                "OpenAIError",
                "create_llm_client",
            },
        )
        self.assertFalse(hasattr(llm_module, "requests"))

    def test_gemini_requires_api_key(self) -> None:
        client = GeminiClient(Settings(llm_provider="gemini"))

        with self.assertRaisesRegex(LLMError, "Gemini API key is not configured"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"test": true}',
                temperature=0.2,
            )

    @patch("app.llm.base_client.requests.post")
    def test_gemini_parses_json_response(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={"candidates": [{"content": {"parts": [{"text": _SCORE_STRONG_FIT}]}}]}
        )
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
                gemini_model="gemini-2.0-flash",
                llm_http_proxy="http://127.0.0.1:9000",
            )
        )

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.3,
        )

        self.assertEqual(payload["score"], 9.1)
        self.assertEqual(payload["verdict"], "strong_fit")
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertEqual(call_kwargs["params"], {"key": "gemini-key"})
        self.assertEqual(call_kwargs["json"]["generationConfig"]["responseMimeType"], "application/json")
        self.assertEqual(
            call_kwargs["proxies"],
            {"http": "http://127.0.0.1:9000", "https": "http://127.0.0.1:9000"},
        )

    @patch("app.llm.base_client.requests.post")
    def test_gemini_rejects_empty_candidates(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(json_body={})
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
            )
        )

        with self.assertRaisesRegex(LLMError, "Gemini response did not include any candidates"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"candidate_text":"hello"}',
                temperature=0.3,
            )

    @patch("app.llm.base_client.requests.post")
    def test_gemini_http_error_raises_llmerror(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(status_code=429, text="quota exhausted")
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
            )
        )

        with self.assertRaisesRegex(LLMError, "Gemini request failed"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"candidate_text":"hello"}',
                temperature=0.3,
            )

    @patch("app.llm.base_client.requests.post")
    def test_gemini_rejects_invalid_json_response(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={"candidates": [{"content": {"parts": [{"text": "not-json"}]}}]}
        )
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
            )
        )

        with self.assertRaisesRegex(LLMError, "Gemini returned invalid JSON"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"candidate_text":"hello"}',
                temperature=0.3,
            )

    @patch("app.llm.base_client.requests.post")
    def test_gemini_parses_fenced_json_response(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={"candidates": [{"content": {"parts": [{"text": "```json\n" + _SCORE_FIT_88 + "\n```"}]}}]}
        )
        client = GeminiClient(Settings(llm_provider="gemini", gemini_api_key="gemini-key"))

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.3,
        )

        self.assertEqual(payload["score"], 8.8)

    @patch("app.llm.base_client.requests.post")
    def test_gemini_extracts_json_from_wrapped_text(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={
                "candidates": [
                    {"content": {"parts": [{"text": "Here is the result:\n" + _SCORE_FIT_86 + "\nThanks."}]}}
                ]
            }
        )
        client = GeminiClient(Settings(llm_provider="gemini", gemini_api_key="gemini-key"))

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.3,
        )

        self.assertEqual(payload["score"], 8.6)

    @patch("app.llm.base_client.requests.post")
    def test_gemini_retries_timeout_then_succeeds(self, mock_post) -> None:
        import requests

        mock_post.side_effect = [
            requests.ReadTimeout("timed out"),
            FakeResponse(json_body={"candidates": [{"content": {"parts": [{"text": _SCORE_FIT_91}]}}]}),
        ]
        client = GeminiClient(
            Settings(
                llm_provider="gemini",
                gemini_api_key="gemini-key",
                llm_max_retries=1,
                llm_retry_backoff_seconds=0.0,
            )
        )

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.3,
        )

        self.assertEqual(payload["score"], 9.1)
        self.assertEqual(mock_post.call_count, 2)

    @patch("app.llm.base_client.requests.post")
    def test_openai_retries_http_5xx_then_succeeds(self, mock_post) -> None:
        mock_post.side_effect = [
            FakeResponse(status_code=503, text="temporary outage"),
            FakeResponse(json_body={"choices": [{"message": {"content": _SCORE_OK_90}}]}),
        ]
        client = OpenAIClient(
            Settings(
                openai_api_key="openai-key",
                llm_max_retries=1,
                llm_retry_backoff_seconds=0.0,
            )
        )

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.1,
        )

        self.assertEqual(payload["score"], 9.0)
        self.assertEqual(mock_post.call_count, 2)

    @patch("app.llm.base_client.requests.post")
    def test_openai_request_shape_and_parsing(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(json_body={"choices": [{"message": {"content": _SCORE_OK_90}}]})
        client = OpenAIClient(
            Settings(
                openai_api_key="openai-key",
                openai_model="gpt-test",
                llm_http_proxy="http://127.0.0.1:9000",
            )
        )

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.1,
        )

        self.assertEqual(payload["score"], 9.0)
        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args.kwargs
        self.assertIn("Authorization", call_kwargs["headers"])
        self.assertEqual(call_kwargs["headers"]["Authorization"], "Bearer openai-key")
        self.assertEqual(call_kwargs["json"]["model"], "gpt-test")
        self.assertEqual(call_kwargs["json"]["response_format"]["type"], "json_object")
        self.assertEqual(
            call_kwargs["proxies"],
            {"http": "http://127.0.0.1:9000", "https": "http://127.0.0.1:9000"},
        )

    @patch("app.llm.base_client.requests.post")
    def test_openai_recovers_plaintext_numbered_drafts(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={
                "choices": [
                    {
                        "message": {
                            "content": (
                                "1. 天气不是背景板，它已经在接管情绪。\n\n2. 当季节秩序开始漂移，日常就会变成风险管理。"
                            )
                        }
                    }
                ]
            }
        )
        client = OpenAIClient(Settings(openai_api_key="openai-key"))

        payload = client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"prompt":"写天气主题推文"}',
            temperature=0.8,
            purpose="draft_generation",
        )

        self.assertIn("drafts", payload)
        self.assertEqual(len(payload["drafts"]), 2)
        self.assertEqual(payload["drafts"][0]["tone_tags"], [])
        self.assertIn("天气不是背景板", payload["drafts"][0]["text"])

    @patch("app.llm.base_client.requests.post")
    def test_openai_plaintext_response_still_fails_for_non_draft_purpose(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={"choices": [{"message": {"content": "这不是 JSON，只是普通文本。"}}]}
        )
        client = OpenAIClient(Settings(openai_api_key="openai-key"))

        with self.assertRaisesRegex(LLMError, "OpenAI returned invalid JSON"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"candidate_text":"hello"}',
                temperature=0.1,
                purpose="score",
            )

    @patch("app.llm.base_client.requests.post")
    def test_openai_http_error_raises_llmerror(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(status_code=400, text="bad request")
        client = OpenAIClient(Settings(openai_api_key="openai-key"))

        with self.assertRaisesRegex(LLMError, "OpenAI request failed"):
            client._chat_completion_json(
                system_prompt="Return JSON",
                user_prompt='{"candidate_text":"hello"}',
                temperature=0.1,
            )
        self.assertEqual(mock_post.call_count, 1)

    @patch("app.llm.base_client.requests.post")
    def test_openai_uses_no_proxy_when_unconfigured(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(json_body={"choices": [{"message": {"content": _SCORE_OK_90}}]})
        client = OpenAIClient(Settings(openai_api_key="openai-key", llm_http_proxy=""))

        client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.1,
        )

        call_kwargs = mock_post.call_args.kwargs
        self.assertIsNone(call_kwargs["proxies"])

    @patch("app.llm.base_client.requests.post")
    def test_gemini_uses_no_proxy_when_unconfigured(self, mock_post) -> None:
        mock_post.return_value = FakeResponse(
            json_body={"candidates": [{"content": {"parts": [{"text": _SCORE_STRONG_FIT}]}}]}
        )
        client = GeminiClient(Settings(llm_provider="gemini", gemini_api_key="gemini-key", llm_http_proxy=""))

        client._chat_completion_json(
            system_prompt="Return JSON",
            user_prompt='{"candidate_text":"hello"}',
            temperature=0.3,
        )

        call_kwargs = mock_post.call_args.kwargs
        self.assertIsNone(call_kwargs["proxies"])

    @patch("app.llm.base_client.requests.post")
    def test_generate_drafts_falls_back_when_score_transport_exhausts_retries(self, mock_post) -> None:
        import requests

        mock_post.side_effect = [
            FakeResponse(json_body={"choices": [{"message": {"content": _DRAFTS_WTDD}}]}),
            requests.ReadTimeout("timed out"),
            requests.ReadTimeout("timed out"),
        ]
        client = OpenAIClient(
            Settings(
                openai_api_key="openai-key",
                llm_max_retries=1,
                llm_retry_backoff_seconds=0.0,
                llm_score_timeout_seconds=1,
            )
        )

        with patch.object(
            client,
            "_rule_score_draft",
            return_value={
                "score": 9.2,
                "passed": True,
                "hard_fail": False,
                "issues": [],
                "strengths": ["Theme keyword hits: WTDD"],
            },
        ):
            result = client.generate_drafts(
                persona={"generation_guardrails": {}, "lexical_markers": [], "do_not_sound_like": []},
                prompt="WTDD 今天很强",
                representative_tweets=[{"text": "WTDD meme"}],
                source_texts=["WTDD meme"],
                tweet_rows=[
                    {
                        "id": "tweet-1",
                        "text": "WTDD meme",
                        "created_at": "2026-03-30T00:00:00Z",
                        "is_retweet": False,
                        "retweet_count": 0,
                        "reply_count": 0,
                        "like_count": 0,
                        "quote_count": 0,
                    }
                ],
                draft_count=1,
            )

        candidate = result["attempts"][0]["candidates"][0]
        self.assertEqual(candidate["llm_verdict"], "provider_timeout_fallback")
        self.assertEqual(candidate["final_score"], 9.2)
        self.assertTrue(candidate["passed"])
        self.assertEqual(mock_post.call_count, 3)

    @patch("app.llm.base_client.requests.post")
    def test_generate_drafts_falls_back_when_score_payload_is_list(self, mock_post) -> None:
        mock_post.side_effect = [
            FakeResponse(json_body={"choices": [{"message": {"content": _DRAFTS_WTDD}}]}),
            FakeResponse(json_body={"choices": [{"message": {"content": _SCORE_FIT_94_LIST}}]}),
        ]
        client = OpenAIClient(
            Settings(
                openai_api_key="openai-key",
                llm_max_retries=1,
                llm_retry_backoff_seconds=0.0,
                llm_score_timeout_seconds=1,
            )
        )

        with patch.object(
            client,
            "_rule_score_draft",
            return_value={
                "score": 9.2,
                "passed": True,
                "hard_fail": False,
                "issues": [],
                "strengths": ["Theme keyword hits: WTDD"],
            },
        ):
            result = client.generate_drafts(
                persona={"generation_guardrails": {}, "lexical_markers": [], "do_not_sound_like": []},
                prompt="WTDD 今天很强",
                representative_tweets=[{"text": "WTDD meme"}],
                source_texts=["WTDD meme"],
                tweet_rows=[
                    {
                        "id": "tweet-1",
                        "text": "WTDD meme",
                        "created_at": "2026-03-30T00:00:00Z",
                        "is_retweet": False,
                        "retweet_count": 0,
                        "reply_count": 0,
                        "like_count": 0,
                        "quote_count": 0,
                    }
                ],
                draft_count=1,
            )

        candidate = result["attempts"][0]["candidates"][0]
        self.assertEqual(candidate["llm_score"], 9.4)
        self.assertEqual(candidate["final_score"], 9.3)
        self.assertTrue(candidate["passed"])
        self.assertEqual(mock_post.call_count, 2)


if __name__ == "__main__":
    unittest.main()
