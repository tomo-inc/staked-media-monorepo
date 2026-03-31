from __future__ import annotations

import unittest

from app.persona import (
    build_corpus_stats,
    expand_related_keywords,
    extract_personal_phrases_unbounded,
    extract_theme_keywords,
    extract_top_theme_keywords,
    is_too_similar,
    prompt_requests_full_chinese,
    select_theme_tweets,
)


class PersonaHelpersTestCase(unittest.TestCase):
    def test_build_corpus_stats_counts_retweets_and_replies(self) -> None:
        profile = {
            "name": "Tester",
            "username": "tester",
            "description": "Builder",
            "location": "",
            "public_metrics": {"followers_count": 50},
        }
        tweet_rows = [
            {
                "id": "1",
                "text": "Shipping product updates with clear takeaways",
                "created_at": "2026-03-01T00:00:00Z",
                "is_retweet": False,
                "is_reply": False,
                "is_quote": False,
                "like_count": 10,
                "retweet_count": 2,
                "reply_count": 1,
                "quote_count": 0,
            },
            {
                "id": "2",
                "text": "RT @someone Strong point on distribution",
                "created_at": "2026-03-02T00:00:00Z",
                "is_retweet": True,
                "is_reply": False,
                "is_quote": False,
                "like_count": 1,
                "retweet_count": 0,
                "reply_count": 0,
                "quote_count": 0,
            },
            {
                "id": "3",
                "text": "@friend The shortest path is still the best one",
                "created_at": "2026-03-03T00:00:00Z",
                "is_retweet": False,
                "is_reply": True,
                "is_quote": False,
                "like_count": 3,
                "retweet_count": 1,
                "reply_count": 1,
                "quote_count": 0,
            },
        ]

        stats = build_corpus_stats(profile, tweet_rows, sample_size=3)
        self.assertEqual(stats["tweet_counts"]["total"], 3)
        self.assertEqual(stats["tweet_counts"]["original"], 2)
        self.assertEqual(stats["tweet_counts"]["retweets"], 1)
        self.assertEqual(stats["tweet_counts"]["replies"], 1)
        self.assertEqual(len(stats["representative_tweets"]), 2)

    def test_similarity_guard_blocks_near_duplicates(self) -> None:
        source_texts = ["Shipping product updates with clear takeaways"]
        self.assertTrue(
            is_too_similar(
                "Shipping product updates with very clear takeaways",
                source_texts,
                threshold=0.90,
            )
        )
        self.assertFalse(
            is_too_similar(
                "Focus compounds when the roadmap gets simpler",
                source_texts,
                threshold=0.90,
            )
        )

    def test_extract_theme_keywords_prefers_signal_terms(self) -> None:
        keywords = extract_theme_keywords(
            "Write a Chinese post about PEPE pumping 20% and focus on market narrative."
        )
        self.assertIn("PEPE", keywords)
        self.assertIn("20%", keywords)

    def test_select_theme_tweets_and_extract_top_theme_keywords_use_theme_corpus(self) -> None:
        tweet_rows = [
            {
                "id": "1",
                "text": "PEPE momentum usually drags meme sentiment together.",
                "created_at": "2026-03-01T00:00:00Z",
                "is_retweet": False,
                "is_reply": False,
                "is_quote": False,
                "like_count": 10,
                "retweet_count": 2,
                "reply_count": 1,
                "quote_count": 0,
            },
            {
                "id": "2",
                "text": "Real PEPE leadership often shows up before broader rotation.",
                "created_at": "2026-03-02T00:00:00Z",
                "is_retweet": False,
                "is_reply": False,
                "is_quote": False,
                "like_count": 12,
                "retweet_count": 2,
                "reply_count": 1,
                "quote_count": 0,
            },
            {
                "id": "3",
                "text": "BTC remains the macro anchor.",
                "created_at": "2026-03-03T00:00:00Z",
                "is_retweet": False,
                "is_reply": False,
                "is_quote": False,
                "like_count": 20,
                "retweet_count": 2,
                "reply_count": 1,
                "quote_count": 0,
            },
        ]

        matched = select_theme_tweets(tweet_rows, ["PEPE"])
        top_keywords = extract_top_theme_keywords(matched, ["PEPE"], prompt="Use Chinese style.")

        self.assertEqual(len(matched), 2)
        self.assertIn("PEPE", matched[0]["match_terms"])
        self.assertTrue(any(keyword.lower() in ("momentum", "leadership", "rotation", "sentiment") for keyword in top_keywords))

    def test_expand_related_keywords_dedupes_and_prioritizes_seed(self) -> None:
        expanded = expand_related_keywords(
            ["Binance", "AI Pro"],
            ["AI Pro", "OpenClaw", "winners"],
            ["community", "OpenClaw", "alpha"],
            limit=6,
        )
        self.assertEqual(expanded[0], "Binance")
        self.assertIn("OpenClaw", expanded)
        self.assertIn("community", expanded)
        self.assertEqual(len(expanded), len(set(token.lower() for token in expanded)))

    def test_extract_personal_phrases_unbounded_returns_sentence_chunks_and_tokens(self) -> None:
        phrases = extract_personal_phrases_unbounded(
            [
                {"text": "We keep shipping weekly updates. Community first, always."},
                {"text": "Product rhythm matters; focus and execution win."},
            ]
        )
        lowered = [phrase.lower() for phrase in phrases]
        self.assertTrue(any("shipping weekly updates" in phrase for phrase in lowered))
        self.assertIn("community", lowered)

    def test_prompt_requests_full_chinese_detects_common_user_wording(self) -> None:
        self.assertTrue(
            prompt_requests_full_chinese("写一条推文，中文全部，不要一下中文一下英文。")
        )
        self.assertTrue(
            prompt_requests_full_chinese(
                "写一条X推文，主题是：Claude Code 泄露了全部源码。观点：这是标题党，风格直接。"
            )
        )
        self.assertFalse(
            prompt_requests_full_chinese("写一条中英双语推文，保持轻松语气。")
        )


if __name__ == "__main__":
    unittest.main()
