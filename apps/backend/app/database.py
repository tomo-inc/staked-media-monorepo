from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

SCHEMA = """
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
    verified INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    last_ingested_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tweets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    text TEXT NOT NULL,
    created_at TEXT NOT NULL,
    lang TEXT,
    is_retweet INTEGER NOT NULL DEFAULT 0,
    is_reply INTEGER NOT NULL DEFAULT 0,
    is_quote INTEGER NOT NULL DEFAULT 0,
    like_count INTEGER NOT NULL DEFAULT 0,
    retweet_count INTEGER NOT NULL DEFAULT 0,
    reply_count INTEGER NOT NULL DEFAULT 0,
    quote_count INTEGER NOT NULL DEFAULT 0,
    raw_json TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_tweets_user_created_at
ON tweets(user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS persona_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    username TEXT NOT NULL,
    source_tweet_count INTEGER NOT NULL,
    source_original_tweet_count INTEGER NOT NULL,
    source_window_start TEXT,
    source_window_end TEXT,
    corpus_stats_json TEXT NOT NULL,
    representative_tweets_json TEXT NOT NULL,
    persona_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(user_id) REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_persona_username_created_at
ON persona_snapshots(username, created_at DESC);

CREATE TABLE IF NOT EXISTS draft_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    persona_snapshot_id INTEGER NOT NULL,
    prompt TEXT NOT NULL,
    draft_count INTEGER NOT NULL,
    output_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY(persona_snapshot_id) REFERENCES persona_snapshots(id)
);

CREATE TABLE IF NOT EXISTS hot_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL DEFAULT '',
    source_domain TEXT NOT NULL DEFAULT '',
    published_at TEXT NOT NULL DEFAULT '',
    relative_age_hint TEXT NOT NULL DEFAULT '',
    heat_score REAL NOT NULL DEFAULT 0.0,
    category TEXT NOT NULL DEFAULT '',
    subcategory TEXT NOT NULL DEFAULT '',
    content_type TEXT NOT NULL DEFAULT 'news',
    author_handle TEXT NOT NULL DEFAULT '',
    last_refreshed_at TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    raw_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hot_events_published_at
ON hot_events(published_at DESC);

CREATE INDEX IF NOT EXISTS idx_hot_events_heat_score
ON hot_events(heat_score DESC);

CREATE INDEX IF NOT EXISTS idx_hot_events_content_type
ON hot_events(content_type);

CREATE INDEX IF NOT EXISTS idx_hot_events_last_refreshed_at
ON hot_events(last_refreshed_at DESC);

CREATE TABLE IF NOT EXISTS allowed_usernames (
    username TEXT PRIMARY KEY
);
"""


class _ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.execute("DROP TABLE IF EXISTS hot_events_snapshots")
            connection.executescript(SCHEMA)
            connection.commit()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, factory=_ClosingConnection)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert_user(self, user: dict[str, Any], ingested_at: str) -> None:
        metrics = user.get("public_metrics") or {}
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO users (
                    id, username, name, description, location, profile_url,
                    followers_count, following_count, tweet_count, verified,
                    raw_json, last_ingested_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    int(bool(user.get("verified") or user.get("is_blue_verified"))),
                    json.dumps(user, ensure_ascii=True),
                    ingested_at,
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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        tweet.get("created_at") or "",
                        tweet.get("lang") or "",
                        int(flags["is_retweet"]),
                        int(flags["is_reply"]),
                        int(flags["is_quote"]),
                        metrics.get("like_count", 0),
                        metrics.get("retweet_count", 0),
                        metrics.get("reply_count", 0),
                        metrics.get("quote_count", 0),
                        json.dumps(item, ensure_ascii=True),
                        ingested_at,
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
            cursor = connection.execute(
                """
                INSERT INTO persona_snapshots (
                    user_id, username, source_tweet_count, source_original_tweet_count,
                    source_window_start, source_window_end, corpus_stats_json,
                    representative_tweets_json, persona_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    user_id,
                    username,
                    source_tweet_count,
                    source_original_tweet_count,
                    source_window_start,
                    source_window_end,
                    json.dumps(corpus_stats, ensure_ascii=True),
                    json.dumps(representative_tweets, ensure_ascii=True),
                    json.dumps(persona, ensure_ascii=True),
                    created_at,
                ),
            )
            connection.commit()
            return cursor.lastrowid or 0

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
            cursor = connection.execute(
                """
                INSERT INTO draft_requests (
                    username, persona_snapshot_id, prompt, draft_count, output_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    persona_snapshot_id,
                    prompt,
                    draft_count,
                    json.dumps(output, ensure_ascii=True),
                    created_at,
                ),
            )
            connection.commit()
            return cursor.lastrowid or 0

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
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        normalized["published_at"],
                        normalized["relative_age_hint"],
                        normalized["heat_score"],
                        normalized["category"],
                        normalized["subcategory"],
                        normalized["content_type"],
                        normalized["author_handle"],
                        refreshed_at,
                        refreshed_at,
                        refreshed_at,
                        json.dumps(item, ensure_ascii=True),
                    ),
                )
                count += 1
            connection.commit()
        return count

    def list_hot_events(self, *, published_since: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = """
            SELECT *
            FROM hot_events
            WHERE published_at >= ?
            ORDER BY heat_score DESC, published_at DESC, id ASC
        """
        params: list[Any] = [published_since]
        if limit is not None:
            query += " LIMIT ?"
            params.append(int(limit))

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_hot_event(row) for row in rows]

    def get_hot_event_by_id(self, event_id: str, *, published_since: str | None = None) -> dict[str, Any] | None:
        query = "SELECT * FROM hot_events WHERE id = ?"
        params: list[Any] = [str(event_id or "").strip()]
        if published_since is not None:
            query += " AND published_at >= ?"
            params.append(published_since)
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
        return str(row["last_refreshed_at"] or "")

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
                INSERT OR IGNORE INTO allowed_usernames (username)
                VALUES (?)
                """,
                (normalized_username,),
            )
            connection.commit()
        return normalized_username

    def remove_allowed_username(self, username: str) -> str:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM allowed_usernames WHERE username = ?",
                (normalized_username,),
            )
            connection.commit()
        return normalized_username

    def is_username_allowed(self, username: str) -> bool:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM allowed_usernames WHERE username = ? LIMIT 1",
                (normalized_username,),
            ).fetchone()
        return row is not None

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (normalized_username,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    def get_user_tweets(self, user_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM tweets WHERE user_id = ? ORDER BY created_at DESC"
        params: list[Any] = [user_id]
        if limit is not None:
            query += " LIMIT ?"
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
                WHERE lower(username) = ?
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


def _row_to_user(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["verified"] = bool(payload["verified"])
    payload["raw_json"] = json.loads(payload["raw_json"])
    return payload


def _row_to_tweet(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    for key in ("is_retweet", "is_reply", "is_quote"):
        payload[key] = bool(payload[key])
    payload["raw_json"] = json.loads(payload["raw_json"])
    return payload


def _row_to_persona_snapshot(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["corpus_stats"] = json.loads(payload.pop("corpus_stats_json"))
    payload["representative_tweets"] = json.loads(payload.pop("representative_tweets_json"))
    payload["persona"] = json.loads(payload.pop("persona_json"))
    return payload


def _row_to_hot_event(row: sqlite3.Row) -> dict[str, Any]:
    payload = dict(row)
    payload["heat_score"] = float(payload.get("heat_score") or 0.0)
    return {
        "id": str(payload.get("id") or ""),
        "title": str(payload.get("title") or ""),
        "summary": str(payload.get("summary") or ""),
        "url": str(payload.get("url") or ""),
        "source": str(payload.get("source") or ""),
        "source_domain": str(payload.get("source_domain") or ""),
        "published_at": str(payload.get("published_at") or ""),
        "relative_age_hint": str(payload.get("relative_age_hint") or ""),
        "heat_score": payload["heat_score"],
        "category": str(payload.get("category") or ""),
        "subcategory": str(payload.get("subcategory") or ""),
        "content_type": str(payload.get("content_type") or "news"),
        "author_handle": str(payload.get("author_handle") or ""),
        "last_refreshed_at": str(payload.get("last_refreshed_at") or ""),
        "created_at": str(payload.get("created_at") or ""),
        "updated_at": str(payload.get("updated_at") or ""),
        "raw_json": _safe_json_loads(payload.get("raw_json")),
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


def _safe_json_loads(value: Any) -> Any:
    try:
        return json.loads(str(value or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
