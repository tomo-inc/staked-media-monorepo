from __future__ import annotations

from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import psycopg
from psycopg.rows import dict_row

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,
        username TEXT NOT NULL UNIQUE,
        name TEXT NOT NULL,
        description TEXT,
        location TEXT,
        profile_url TEXT,
        followers_count INTEGER NOT NULL DEFAULT 0,
        following_count INTEGER NOT NULL DEFAULT 0,
        tweet_count INTEGER NOT NULL DEFAULT 0,
        verified BOOLEAN NOT NULL DEFAULT FALSE,
        raw_json JSONB NOT NULL,
        last_ingested_at TIMESTAMPTZ NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tweets (
        id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        lang TEXT,
        is_retweet BOOLEAN NOT NULL DEFAULT FALSE,
        is_reply BOOLEAN NOT NULL DEFAULT FALSE,
        is_quote BOOLEAN NOT NULL DEFAULT FALSE,
        like_count INTEGER NOT NULL DEFAULT 0,
        retweet_count INTEGER NOT NULL DEFAULT 0,
        reply_count INTEGER NOT NULL DEFAULT 0,
        quote_count INTEGER NOT NULL DEFAULT 0,
        raw_json JSONB NOT NULL,
        ingested_at TIMESTAMPTZ NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_tweets_user_created_at ON tweets(user_id, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS persona_snapshots (
        id BIGSERIAL PRIMARY KEY,
        user_id TEXT NOT NULL,
        username TEXT NOT NULL,
        source_tweet_count INTEGER NOT NULL,
        source_original_tweet_count INTEGER NOT NULL,
        source_window_start TIMESTAMPTZ,
        source_window_end TIMESTAMPTZ,
        corpus_stats_json JSONB NOT NULL,
        representative_tweets_json JSONB NOT NULL,
        persona_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        FOREIGN KEY(user_id) REFERENCES users(id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_persona_username_created_at ON persona_snapshots(username, created_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS draft_requests (
        id BIGSERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        persona_snapshot_id BIGINT NOT NULL,
        prompt TEXT NOT NULL,
        draft_count INTEGER NOT NULL,
        output_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        FOREIGN KEY(persona_snapshot_id) REFERENCES persona_snapshots(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS hot_events (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        summary TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        source TEXT NOT NULL DEFAULT '',
        source_domain TEXT NOT NULL DEFAULT '',
        published_at TIMESTAMPTZ NOT NULL,
        relative_age_hint TEXT NOT NULL DEFAULT '',
        heat_score DOUBLE PRECISION NOT NULL DEFAULT 0.0,
        category TEXT NOT NULL DEFAULT '',
        subcategory TEXT NOT NULL DEFAULT '',
        content_type TEXT NOT NULL DEFAULT 'news',
        author_handle TEXT NOT NULL DEFAULT '',
        last_refreshed_at TIMESTAMPTZ NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL,
        raw_json JSONB NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_hot_events_published_at ON hot_events(published_at DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hot_events_heat_score ON hot_events(heat_score DESC)",
    "CREATE INDEX IF NOT EXISTS idx_hot_events_content_type ON hot_events(content_type)",
    "CREATE INDEX IF NOT EXISTS idx_hot_events_last_refreshed_at ON hot_events(last_refreshed_at DESC)",
    """
    CREATE TABLE IF NOT EXISTS hot_event_translations (
        event_id TEXT NOT NULL,
        target_language TEXT NOT NULL,
        title_translated TEXT NOT NULL,
        summary_translated TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (event_id, target_language),
        FOREIGN KEY(event_id) REFERENCES hot_events(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS allowed_usernames (
        username TEXT PRIMARY KEY
    )
    """,
]


class Database:
    def __init__(self, database_url: str):
        self.database_url = str(database_url or "").strip()

    def init(self) -> None:
        with self.connect() as connection:
            connection.execute("DROP TABLE IF EXISTS hot_events_snapshots")
            for statement in SCHEMA_STATEMENTS:
                connection.execute(statement)
            connection.commit()

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection[dict[str, Any]]]:
        connection = psycopg.connect(self.database_url, row_factory=dict_row)
        try:
            yield connection
        finally:
            connection.close()

    def upsert_user(self, user: dict[str, Any], ingested_at: str) -> None:
        metrics = user.get("public_metrics") or {}
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, username, name, description, location, profile_url,
                    followers_count, following_count, tweet_count, verified,
                    raw_json, last_ingested_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(id) DO UPDATE SET
                    username=excluded.username,
                    name=excluded.name,
                    description=excluded.description,
                    location=excluded.location,
                    profile_url=excluded.profile_url,
                    followers_count=excluded.followers_count,
                    following_count=excluded.following_count,
                    tweet_count=excluded.tweet_count,
                    verified=excluded.verified,
                    raw_json=excluded.raw_json,
                    last_ingested_at=excluded.last_ingested_at
                """,
                (
                    user["id"],
                    user["username"],
                    user.get("name") or user["username"],
                    user.get("description") or "",
                    user.get("location") or "",
                    user.get("url") or "",
                    metrics.get("followers_count", 0),
                    metrics.get("following_count", 0),
                    metrics.get("tweet_count", 0),
                    bool(user.get("verified") or user.get("is_blue_verified")),
                    user,
                    _coerce_timestamp(ingested_at),
                ),
            )
            connection.commit()

    def upsert_tweets(self, user_id: str, tweet_items: Iterable[dict[str, Any]], ingested_at: str) -> int:
        count = 0
        with self.connect() as connection:
            for item in tweet_items:
                tweet = item["data"]
                metrics = tweet.get("public_metrics") or {}
                flags = _tweet_flags(tweet)
                connection.execute(
                    """
                    INSERT INTO tweets (
                        id, user_id, text, created_at, lang,
                        is_retweet, is_reply, is_quote,
                        like_count, retweet_count, reply_count, quote_count,
                        raw_json, ingested_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        user_id=excluded.user_id,
                        text=excluded.text,
                        created_at=excluded.created_at,
                        lang=excluded.lang,
                        is_retweet=excluded.is_retweet,
                        is_reply=excluded.is_reply,
                        is_quote=excluded.is_quote,
                        like_count=excluded.like_count,
                        retweet_count=excluded.retweet_count,
                        reply_count=excluded.reply_count,
                        quote_count=excluded.quote_count,
                        raw_json=excluded.raw_json,
                        ingested_at=excluded.ingested_at
                    """,
                    (
                        tweet["id"],
                        user_id,
                        tweet.get("text") or "",
                        _coerce_timestamp(tweet.get("created_at"), fallback=ingested_at),
                        tweet.get("lang") or "",
                        flags["is_retweet"],
                        flags["is_reply"],
                        flags["is_quote"],
                        metrics.get("like_count", 0),
                        metrics.get("retweet_count", 0),
                        metrics.get("reply_count", 0),
                        metrics.get("quote_count", 0),
                        item,
                        _coerce_timestamp(ingested_at),
                    ),
                )
                count += 1
            connection.commit()
        return count

    def save_persona_snapshot(
        self,
        *,
        user_id: str,
        username: str,
        source_tweet_count: int,
        source_original_tweet_count: int,
        source_window_start: str | None,
        source_window_end: str | None,
        corpus_stats: dict[str, Any],
        representative_tweets: list[dict[str, Any]],
        persona: dict[str, Any],
        created_at: str,
    ) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO persona_snapshots (
                    user_id, username, source_tweet_count, source_original_tweet_count,
                    source_window_start, source_window_end, corpus_stats_json,
                    representative_tweets_json, persona_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    username,
                    source_tweet_count,
                    source_original_tweet_count,
                    _coerce_timestamp(source_window_start, allow_none=True),
                    _coerce_timestamp(source_window_end, allow_none=True),
                    corpus_stats,
                    representative_tweets,
                    persona,
                    _coerce_timestamp(created_at),
                ),
            ).fetchone()
            connection.commit()
            return int((row or {}).get("id") or 0)

    def save_draft_request(
        self,
        *,
        username: str,
        persona_snapshot_id: int,
        prompt: str,
        draft_count: int,
        output: dict[str, Any],
        created_at: str,
    ) -> int:
        with self.connect() as connection:
            row = connection.execute(
                """
                INSERT INTO draft_requests (
                    username, persona_snapshot_id, prompt, draft_count, output_json, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    username,
                    persona_snapshot_id,
                    prompt,
                    draft_count,
                    output,
                    _coerce_timestamp(created_at),
                ),
            ).fetchone()
            connection.commit()
            return int((row or {}).get("id") or 0)

    def upsert_hot_events(self, hot_events: Iterable[dict[str, Any]], refreshed_at: str) -> int:
        count = 0
        with self.connect() as connection:
            for item in hot_events:
                normalized = _normalize_hot_event(item)
                connection.execute(
                    """
                    INSERT INTO hot_events (
                        id,
                        title,
                        summary,
                        url,
                        source,
                        source_domain,
                        published_at,
                        relative_age_hint,
                        heat_score,
                        category,
                        subcategory,
                        content_type,
                        author_handle,
                        last_refreshed_at,
                        created_at,
                        updated_at,
                        raw_json
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        summary=excluded.summary,
                        url=excluded.url,
                        source=excluded.source,
                        source_domain=excluded.source_domain,
                        published_at=excluded.published_at,
                        relative_age_hint=excluded.relative_age_hint,
                        heat_score=excluded.heat_score,
                        category=excluded.category,
                        subcategory=excluded.subcategory,
                        content_type=excluded.content_type,
                        author_handle=excluded.author_handle,
                        last_refreshed_at=excluded.last_refreshed_at,
                        updated_at=excluded.updated_at,
                        raw_json=excluded.raw_json
                    """,
                    (
                        normalized["id"],
                        normalized["title"],
                        normalized["summary"],
                        normalized["url"],
                        normalized["source"],
                        normalized["source_domain"],
                        _coerce_timestamp(normalized["published_at"], fallback=refreshed_at),
                        normalized["relative_age_hint"],
                        normalized["heat_score"],
                        normalized["category"],
                        normalized["subcategory"],
                        normalized["content_type"],
                        normalized["author_handle"],
                        _coerce_timestamp(refreshed_at),
                        _coerce_timestamp(refreshed_at),
                        _coerce_timestamp(refreshed_at),
                        item,
                    ),
                )
                count += 1
            connection.commit()
        return count

    def list_hot_events(self, *, published_since: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT *
            FROM hot_events
            WHERE published_at >= %s
            ORDER BY heat_score DESC, published_at DESC, id ASC
        """
        params: list[Any] = [_coerce_timestamp(published_since)]
        if limit is not None:
            query += " LIMIT %s"
            params.append(int(limit))

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_hot_event(row) for row in rows]

    def get_hot_event_by_id(self, event_id: str, *, published_since: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM hot_events WHERE id = %s"
        params: list[Any] = [str(event_id or "").strip()]
        if published_since is not None:
            query += " AND published_at >= %s"
            params.append(_coerce_timestamp(published_since))
        query += " LIMIT 1"
        with self.connect() as connection:
            row = connection.execute(query, params).fetchone()
        if row is None:
            return None
        return _row_to_hot_event(row)

    def get_latest_hot_events_refresh_time(self) -> str:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT MAX(last_refreshed_at) AS last_refreshed_at
                FROM hot_events
                """
            ).fetchone()
        if row is None:
            return ""
        return _to_iso_string(row.get("last_refreshed_at"))

    def get_hot_event_translations(self, event_ids: Iterable[str], target_language: str) -> dict[str, dict[str, Any]]:
        normalized_event_ids = [str(event_id or "").strip() for event_id in event_ids if str(event_id or "").strip()]
        if not normalized_event_ids:
            return {}

        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT event_id, target_language, title_translated, summary_translated, created_at
                FROM hot_event_translations
                WHERE target_language = %s
                  AND event_id = ANY(%s)
                """,
                (str(target_language or "").strip(), normalized_event_ids),
            ).fetchall()
        return {
            str(row["event_id"]): {
                "event_id": str(row["event_id"]),
                "target_language": str(row["target_language"]),
                "title_translated": str(row["title_translated"] or ""),
                "summary_translated": str(row["summary_translated"] or ""),
                "created_at": _to_iso_string(row.get("created_at")),
            }
            for row in rows
        }

    def save_hot_event_translations(self, rows: Iterable[dict[str, Any]]) -> int:
        count = 0
        with self.connect() as connection:
            for row in rows:
                connection.execute(
                    """
                    INSERT INTO hot_event_translations (
                        event_id,
                        target_language,
                        title_translated,
                        summary_translated,
                        created_at
                    ) VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT(event_id, target_language) DO UPDATE SET
                        title_translated=excluded.title_translated,
                        summary_translated=excluded.summary_translated,
                        created_at=excluded.created_at
                    """,
                    (
                        str(row.get("event_id") or "").strip(),
                        str(row.get("target_language") or "").strip(),
                        str(row.get("title_translated") or ""),
                        str(row.get("summary_translated") or ""),
                        _coerce_timestamp(row.get("created_at"), fallback=datetime.now().astimezone().isoformat()),
                    ),
                )
                count += 1
            connection.commit()
        return count

    def list_allowed_usernames(self) -> list[str]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT username
                FROM allowed_usernames
                ORDER BY username ASC
                """
            ).fetchall()
        return [str(row["username"]) for row in rows]

    def add_allowed_username(self, username: str) -> str:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO allowed_usernames (username)
                VALUES (%s)
                ON CONFLICT (username) DO NOTHING
                """,
                (normalized_username,),
            )
            connection.commit()
        return normalized_username

    def remove_allowed_username(self, username: str) -> str:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM allowed_usernames WHERE username = %s",
                (normalized_username,),
            )
            connection.commit()
        return normalized_username

    def is_username_allowed(self, username: str) -> bool:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM allowed_usernames WHERE username = %s LIMIT 1",
                (normalized_username,),
            ).fetchone()
        return row is not None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(username) = %s",
                (normalized_username,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    def get_user_tweets(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM tweets WHERE user_id = %s ORDER BY created_at DESC"
        params: list[Any] = [user_id]
        if limit is not None:
            query += " LIMIT %s"
            params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_tweet(row) for row in rows]

    def get_latest_persona_snapshot(self, username: str) -> dict[str, Any] | None:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM persona_snapshots
                WHERE lower(username) = %s
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """,
                (normalized_username,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_persona_snapshot(row)


def normalize_username(username: str) -> str:
    return str(username or "").strip().lower()


def _tweet_flags(tweet: dict[str, Any]) -> dict[str, bool]:
    referenced = tweet.get("referenced_tweets") or []
    types = {item.get("type") for item in referenced}
    return {
        "is_retweet": "retweeted" in types or (tweet.get("text") or "").startswith("RT @"),
        "is_reply": bool(tweet.get("in_reply_to_user_id")),
        "is_quote": "quoted" in types,
    }


def _row_to_user(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["verified"] = bool(payload["verified"])
    payload["raw_json"] = payload.get("raw_json") or {}
    payload["last_ingested_at"] = _to_iso_string(payload.get("last_ingested_at"))
    return payload


def _row_to_tweet(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    for key in ("is_retweet", "is_reply", "is_quote"):
        payload[key] = bool(payload[key])
    payload["raw_json"] = payload.get("raw_json") or {}
    payload["created_at"] = _to_iso_string(payload.get("created_at"))
    payload["ingested_at"] = _to_iso_string(payload.get("ingested_at"))
    return payload


def _row_to_persona_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["source_window_start"] = _to_iso_string(payload.get("source_window_start"))
    payload["source_window_end"] = _to_iso_string(payload.get("source_window_end"))
    payload["corpus_stats"] = payload.pop("corpus_stats_json") or {}
    payload["representative_tweets"] = payload.pop("representative_tweets_json") or []
    payload["persona"] = payload.pop("persona_json") or {}
    payload["created_at"] = _to_iso_string(payload.get("created_at"))
    return payload


def _row_to_hot_event(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload["heat_score"] = float(payload.get("heat_score") or 0.0)
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "url": str(payload.get("url") or ""),
        "source": str(payload.get("source") or ""),
        "source_domain": str(payload.get("source_domain") or ""),
        "published_at": _to_iso_string(payload.get("published_at")),
        "relative_age_hint": str(payload.get("relative_age_hint") or ""),
        "heat_score": payload["heat_score"],
        "category": str(payload.get("category") or ""),
        "subcategory": str(payload.get("subcategory") or ""),
        "content_type": str(payload.get("content_type") or "news"),
        "author_handle": str(payload.get("author_handle") or ""),
        "last_refreshed_at": _to_iso_string(payload.get("last_refreshed_at")),
        "created_at": _to_iso_string(payload.get("created_at")),
        "updated_at": _to_iso_string(payload.get("updated_at")),
        "raw_json": payload.get("raw_json") or {},
    }


def _normalize_hot_event(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": str(item.get("id") or "").strip(),
        "title": str(item.get("title") or "").strip(),
        "summary": str(item.get("summary") or "").strip(),
        "url": str(item.get("url") or "").strip(),
        "source": str(item.get("source") or "").strip(),
        "source_domain": str(item.get("source_domain") or "").strip(),
        "published_at": str(item.get("published_at") or "").strip(),
        "relative_age_hint": str(item.get("relative_age_hint") or "").strip(),
        "heat_score": float(item.get("heat_score") or 0.0),
        "category": str(item.get("category") or "").strip(),
        "subcategory": str(item.get("subcategory") or "").strip(),
        "content_type": str(item.get("content_type") or "news").strip() or "news",
        "author_handle": str(item.get("author_handle") or "").strip(),
    }


def _coerce_timestamp(
    value: Any,
    *,
    fallback: Any | None = None,
    allow_none: bool = False,
) -> str | None:
    normalized = _to_iso_string(value)
    if normalized:
        return normalized
    fallback_value = _to_iso_string(fallback)
    if fallback_value:
        return fallback_value
    if allow_none:
        return None
    raise ValueError("Timestamp value is required")


def _to_iso_string(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value or "").strip()
