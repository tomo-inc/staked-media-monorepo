from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from statistics import mean
from typing import Any


URL_RE = re.compile(r"https?://\S+")
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#\w+")
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9']+")
EMOJI_RE = re.compile(r"[\U0001F300-\U0001FAFF]")
THEME_TOKEN_RE = re.compile(r"\d+%|[$]?[A-Za-z][A-Za-z0-9']+|[\u4e00-\u9fff]{1,12}")
CHINESE_BLOCK_RE = re.compile(r"[\u4e00-\u9fff]{2,}")

STOPWORDS = {
    "about",
    "after",
    "again",
    "against",
    "all",
    "also",
    "and",
    "any",
    "are",
    "because",
    "been",
    "before",
    "being",
    "between",
    "both",
    "but",
    "can",
    "could",
    "each",
    "from",
    "have",
    "just",
    "more",
    "most",
    "much",
    "over",
    "some",
    "such",
    "than",
    "that",
    "their",
    "them",
    "then",
    "there",
    "these",
    "they",
    "this",
    "those",
    "through",
    "very",
    "what",
    "when",
    "where",
    "which",
    "while",
    "with",
    "would",
    "your",
    "into",
    "here",
    "http",
    "https",
    "rt",
}

CHINESE_STOPWORDS = {
    "今天",
    "现在",
    "这个",
    "这次",
    "一个",
    "一种",
    "一些",
    "一条",
    "帖子",
    "推文",
    "主题",
    "口吻",
    "写一条",
    "写个",
    "写篇",
    "生成",
    "内容",
    "要求",
    "保持",
    "想发",
    "一篇",
    "不要",
    "更像",
    "原生",
    "简短",
    "表达",
    "中文",
    "全中文",
    "中英",
    "夹带",
    "的话",
    "相关",
}

SUMMARY_DRIFT_PHRASES = {
    "有趣之处在于",
    "更像是",
    "交汇点",
    "辨识度",
    "生命力",
}


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def prompt_requests_full_chinese(prompt: str) -> bool:
    prompt = clean_text(prompt)
    return any(
        marker in prompt
        for marker in ("全中文", "不要中英夹带", "纯中文", "只用中文", "不要英文", "中文X帖子", "中文帖子")
    )


def normalize_for_similarity(text: str) -> str:
    without_urls = URL_RE.sub("", text or "")
    without_mentions = MENTION_RE.sub("", without_urls)
    letters_only = re.sub(r"[^a-z0-9\u4e00-\u9fff\s]", " ", without_mentions.lower())
    return re.sub(r"\s+", " ", letters_only).strip()


def is_too_similar(candidate: str, source_texts: list[str], threshold: float) -> bool:
    normalized_candidate = normalize_for_similarity(candidate)
    if not normalized_candidate:
        return True

    for source_text in source_texts:
        normalized_source = normalize_for_similarity(source_text)
        if not normalized_source:
            continue
        if normalized_candidate == normalized_source:
            return True
        if SequenceMatcher(None, normalized_candidate, normalized_source).ratio() >= threshold:
            return True
    return False


def extract_theme_keywords(prompt: str, limit: int = 8) -> list[str]:
    prompt = clean_text(prompt)
    extracted: list[str] = []
    seen: set[str] = set()

    for raw_token in THEME_TOKEN_RE.findall(prompt):
        token = _normalize_theme_token(clean_text(raw_token).strip("$"))
        if not token:
            continue
        normalized = _normalize_keyword(token)
        if not normalized or normalized in seen:
            continue
        if not _is_theme_keyword(token):
            continue
        seen.add(normalized)
        extracted.append(token if _contains_chinese(token) or "%" in token else normalized.upper())
        if len(extracted) >= limit:
            break

    return extracted


def select_theme_tweets(tweet_rows: list[dict[str, Any]], theme_keywords: list[str], limit: int = 12) -> list[dict[str, Any]]:
    if not theme_keywords:
        return []

    candidates = [row for row in tweet_rows if not row["is_retweet"] and clean_text(row["text"])]
    scored_rows: list[tuple[float, dict[str, Any], list[str]]] = []

    for row in candidates:
        text = clean_text(row["text"])
        match_terms = [keyword for keyword in theme_keywords if keyword_in_text(keyword, text)]
        if not match_terms:
            continue
        score = float(len(match_terms) * 10 + _engagement_score(row))
        scored_rows.append((score, row, match_terms))

    scored_rows.sort(
        key=lambda item: (
            len(item[2]),
            item[0],
            item[1]["created_at"],
        ),
        reverse=True,
    )

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for _, row, match_terms in scored_rows:
        if row["id"] in seen_ids:
            continue
        seen_ids.add(row["id"])
        selected.append(
            {
                "id": row["id"],
                "text": clean_text(row["text"]),
                "created_at": row["created_at"],
                "match_terms": match_terms,
                "engagement_score": _engagement_score(row),
            }
        )
        if len(selected) >= limit:
            break

    return selected


def extract_top_theme_keywords(
    matched_tweets: list[dict[str, Any]],
    theme_keywords: list[str],
    *,
    prompt: str = "",
    limit: int = 5,
) -> list[str]:
    if not matched_tweets:
        return theme_keywords[:limit]

    normalized_theme_keywords = {_normalize_keyword(keyword) for keyword in theme_keywords}
    counter = Counter()

    for item in matched_tweets:
        for token in _extract_keyword_candidates(item["text"]):
            normalized = _normalize_keyword(token)
            if not normalized or normalized in normalized_theme_keywords:
                continue
            counter[token] += 1

    prefers_chinese = prompt_requests_full_chinese(prompt)
    ranked = sorted(
        counter.items(),
        key=lambda item: (
            item[1],
            _keyword_priority(item[0], prefers_chinese),
            len(item[0]),
        ),
        reverse=True,
    )

    results: list[str] = []
    seen: set[str] = set()
    for token, _ in ranked:
        normalized = _normalize_keyword(token)
        if normalized in seen:
            continue
        seen.add(normalized)
        results.append(token)
        if len(results) >= limit:
            break

    if len(results) < 3:
        for token in theme_keywords:
            normalized = _normalize_keyword(token)
            if normalized in seen:
                continue
            seen.add(normalized)
            results.append(token)
            if len(results) >= limit:
                break

    return results[:limit]


def build_corpus_stats(profile: dict[str, Any], tweet_rows: list[dict[str, Any]], sample_size: int = 40) -> dict[str, Any]:
    total_tweets = len(tweet_rows)
    original_rows = [row for row in tweet_rows if not row["is_retweet"]]
    original_or_quote_rows = [row for row in tweet_rows if not row["is_retweet"] or row["is_quote"]]

    analysis_rows = original_rows or original_or_quote_rows or tweet_rows
    texts = [clean_text(row["text"]) for row in analysis_rows if clean_text(row["text"])]
    all_texts = [clean_text(row["text"]) for row in tweet_rows if clean_text(row["text"])]

    start_patterns = Counter()
    end_patterns = Counter()
    keyword_counter = Counter()

    for text in texts:
        tokens = WORD_RE.findall(text.lower())
        if tokens:
            start_patterns[" ".join(tokens[:2])] += 1
            end_patterns[" ".join(tokens[-2:])] += 1
        for token in tokens:
            if len(token) < 3 or token in STOPWORDS:
                continue
            keyword_counter[token] += 1

    sample_tweets = select_representative_tweets(tweet_rows, limit=sample_size)
    high_engagement = sorted(
        tweet_rows,
        key=_engagement_score,
        reverse=True,
    )[:5]

    average_length = round(mean(len(text) for text in texts), 2) if texts else 0.0
    window_start = min((row["created_at"] for row in tweet_rows), default=None)
    window_end = max((row["created_at"] for row in tweet_rows), default=None)

    return {
        "profile_snapshot": {
            "name": profile.get("name") or profile.get("username") or "",
            "username": profile.get("username") or "",
            "description": profile.get("description") or "",
            "location": profile.get("location") or "",
            "followers_count": (profile.get("public_metrics") or {}).get("followers_count", 0),
        },
        "tweet_counts": {
            "total": total_tweets,
            "original": len(original_rows),
            "retweets": sum(1 for row in tweet_rows if row["is_retweet"]),
            "replies": sum(1 for row in tweet_rows if row["is_reply"]),
            "quotes": sum(1 for row in tweet_rows if row["is_quote"]),
        },
        "source_window": {
            "start": window_start,
            "end": window_end,
        },
        "writing_stats": {
            "average_length": average_length,
            "question_ratio": _feature_ratio(texts, lambda text: "?" in text),
            "exclamation_ratio": _feature_ratio(texts, lambda text: "!" in text),
            "link_ratio": _feature_ratio(all_texts, lambda text: bool(URL_RE.search(text))),
            "mention_ratio": _feature_ratio(all_texts, lambda text: bool(MENTION_RE.search(text))),
            "hashtag_ratio": _feature_ratio(all_texts, lambda text: bool(HASHTAG_RE.search(text))),
            "emoji_ratio": _feature_ratio(all_texts, lambda text: bool(EMOJI_RE.search(text))),
            "top_openings": [pattern for pattern, _ in start_patterns.most_common(10)],
            "top_closings": [pattern for pattern, _ in end_patterns.most_common(10)],
            "top_keywords": [word for word, _ in keyword_counter.most_common(20)],
        },
        "high_engagement_examples": [
            {
                "id": row["id"],
                "text": clean_text(row["text"]),
                "created_at": row["created_at"],
                "engagement_score": _engagement_score(row),
            }
            for row in high_engagement
        ],
        "representative_tweets": sample_tweets,
    }


def select_representative_tweets(tweet_rows: list[dict[str, Any]], limit: int = 40) -> list[dict[str, Any]]:
    candidates = [row for row in tweet_rows if not row["is_retweet"]]
    if not candidates:
        candidates = list(tweet_rows)

    recent = sorted(candidates, key=lambda row: row["created_at"], reverse=True)[: max(10, limit // 2)]
    high_engagement = sorted(candidates, key=_engagement_score, reverse=True)[: max(10, limit // 3)]
    long_form = sorted(candidates, key=lambda row: len(clean_text(row["text"])), reverse=True)[: max(5, limit // 5)]

    selected: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for row in recent + high_engagement + long_form:
        if row["id"] in seen_ids:
            continue
        seen_ids.add(row["id"])
        selected.append(
            {
                "id": row["id"],
                "text": clean_text(row["text"]),
                "created_at": row["created_at"],
                "is_reply": row["is_reply"],
                "is_quote": row["is_quote"],
                "engagement_score": _engagement_score(row),
            }
        )
        if len(selected) >= limit:
            break
    return selected


def _feature_ratio(texts: list[str], matcher) -> float:
    if not texts:
        return 0.0
    matches = sum(1 for text in texts if matcher(text))
    return round(matches / len(texts), 3)


def _engagement_score(row: dict[str, Any]) -> int:
    return (
        int(row.get("like_count", 0))
        + int(row.get("retweet_count", 0)) * 2
        + int(row.get("reply_count", 0)) * 2
        + int(row.get("quote_count", 0)) * 3
    )


def keyword_in_text(keyword: str, text: str) -> bool:
    keyword = clean_text(keyword)
    text = clean_text(text)
    if not keyword or not text:
        return False
    if _contains_chinese(keyword) or "%" in keyword:
        return keyword in text
    return keyword.lower() in text.lower()


def phrase_frequency(items: list[dict[str, Any]], phrase: str) -> int:
    return sum(_count_occurrences(item.get("text", ""), phrase) for item in items)


def extract_english_words(text: str) -> list[str]:
    return WORD_RE.findall(text or "")


def _extract_keyword_candidates(text: str) -> list[str]:
    cleaned = clean_text(URL_RE.sub("", text or ""))
    candidates: list[str] = []

    for token in WORD_RE.findall(cleaned):
        normalized = token.lower()
        if len(normalized) < 3 or normalized in STOPWORDS:
            continue
        candidates.append(normalized)

    for block in CHINESE_BLOCK_RE.findall(cleaned):
        for size in range(2, min(5, len(block) + 1)):
            for index in range(len(block) - size + 1):
                token = block[index : index + size]
                if token in CHINESE_STOPWORDS or token in SUMMARY_DRIFT_PHRASES:
                    continue
                candidates.append(token)

    return candidates


def _is_theme_keyword(token: str) -> bool:
    normalized = _normalize_keyword(token)
    if not normalized:
        return False
    if _contains_chinese(token) and any(
        marker in token for marker in ("口吻", "中文", "帖子", "主题", "要求", "想发", "中英", "夹带")
    ):
        return False
    if normalized in STOPWORDS or normalized in CHINESE_STOPWORDS:
        return False
    if normalized in {"x", "post", "tweet"}:
        return False
    if "%" in token:
        return True
    if _contains_chinese(token):
        return len(token) >= 2
    return len(normalized) >= 3


def _normalize_keyword(token: str) -> str:
    token = clean_text(token).strip("$").lower()
    return token


def _normalize_theme_token(token: str) -> str:
    token = clean_text(token)
    if _contains_chinese(token) and len(token) > 2 and token.endswith(("了", "的", "啊", "呢", "吗")):
        return token[:-1]
    return token


def _contains_chinese(token: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in token)


def _keyword_priority(token: str, prefers_chinese: bool) -> int:
    if prefers_chinese and _contains_chinese(token):
        return 2
    if not prefers_chinese and not _contains_chinese(token):
        return 2
    return 1


def _count_occurrences(text: str, phrase: str) -> int:
    if not text or not phrase:
        return 0
    if _contains_chinese(phrase) or "%" in phrase:
        return clean_text(text).count(phrase)
    return clean_text(text).lower().count(phrase.lower())
