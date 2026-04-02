from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional


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

CREATE TABLE IF NOT EXISTS allowed_usernames (
    username TEXT PRIMARY KEY
);
"""


class Database:
    def __init__(self, database_path: Path):
        self.database_path = database_path

    def init(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as connection:
            connection.executescript(SCHEMA)
            connection.commit()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
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
        source_window_start: Optional[str],
        source_window_end: Optional[str],
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
            return int(cursor.lastrowid)

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
            return int(cursor.lastrowid)

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

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        normalized_username = normalize_username(username)
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM users WHERE lower(username) = ?",
                (normalized_username,),
            ).fetchone()
        if row is None:
            return None
        return _row_to_user(row)

    def get_user_tweets(self, user_id: str, limit: Optional[int] = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM tweets WHERE user_id = ? ORDER BY created_at DESC"
        params: list[Any] = [user_id]
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        with self.connect() as connection:
            rows = connection.execute(query, params).fetchall()
        return [_row_to_tweet(row) for row in rows]

    def get_latest_persona_snapshot(self, username: str) -> Optional[dict[str, Any]]:
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
