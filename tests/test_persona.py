from __future__ import annotations

import unittest

from app.persona import (
    build_corpus_stats,
    extract_theme_keywords,
    extract_top_theme_keywords,
    is_too_similar,
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
            "用我的口吻写一条中文X帖子，主题是：今天PEPE上涨了20%，我想发一篇帖子。要求不要中英夹带。"
        )

        self.assertIn("PEPE", keywords)
        self.assertIn("上涨", keywords)
        self.assertIn("20%", keywords)
        self.assertNotIn("今天", keywords)

    def test_select_theme_tweets_and_extract_top_theme_keywords_use_theme_corpus(self) -> None:
        tweet_rows = [
            {
                "id": "1",
                "text": "PEPE拉起来的时候，meme板块的情绪会一起回来。",
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
                "text": "真正的PEPE龙头效应，是青蛙一动，情绪就起来了。",
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

        matched = select_theme_tweets(tweet_rows, ["PEPE", "上涨"])
        top_keywords = extract_top_theme_keywords(matched, ["PEPE", "上涨"], prompt="全中文")

        self.assertEqual(len(matched), 2)
        self.assertIn("PEPE", matched[0]["match_terms"])
        self.assertTrue(any(keyword in top_keywords for keyword in ["情绪", "龙头", "青蛙", "板块"]))


if __name__ == "__main__":
    unittest.main()
