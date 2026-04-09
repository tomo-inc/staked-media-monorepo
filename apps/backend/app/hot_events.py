from __future__ import annotations

import hashlib
import html
import re
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

import requests

from app.config import HotEventsFusionSettings

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"\s+")


class HotEventsService:
    BASE_URL = "https://ai.6551.io"
    OPENNEWS_TYPE_PATH = "/open/news_type"
    OPENNEWS_SEARCH_PATH = "/open/news_search"
    OPENTWITTER_TYPE_PATH = "/open/tweets_type"
    OPENTWITTER_SEARCH_PATH = "/open/tweets_search"
    OPENTWITTER_LEGACY_SEARCH_PATH = "/open/twitter_search"
    OPENTWITTER_UNAVAILABLE_ERROR = "opentwitter search unavailable"
    DEFAULT_TWITTER_QUERY = "crypto OR bitcoin OR ethereum OR web3 OR ai"

    def __init__(
        self,
        *,
        timeout_seconds: float = 8.0,
        cache_ttl_seconds: int = 120,
        api_token: str = "",
        fusion_settings: HotEventsFusionSettings | None = None,
    ):
        self.timeout_seconds = timeout_seconds
        self.cache_ttl_seconds = max(0, int(cache_ttl_seconds))
        self.api_token = str(api_token or "").strip()
        self.fusion_settings = fusion_settings or HotEventsFusionSettings()

    def list_hot_events(self, *, hours: int = 24, limit: int = 50, refresh: bool = False) -> dict[str, Any]:
        bounded_hours = max(1, min(72, int(hours)))
        bounded_limit = max(1, min(200, int(limit)))
        payload = self._fetch_hot_events(hours=bounded_hours)
        return {
            "items": payload["items"][:bounded_limit],
            "warnings": list(payload.get("warnings", [])),
            "source_status": dict(payload.get("source_status", {})),
        }

    def _fetch_hot_events(self, *, hours: int) -> dict[str, Any]:
        if not self.api_token:
            raise RuntimeError("provider_6551_token is empty")

        source_status: dict[str, dict[str, Any]] = {}
        warnings: list[str] = []
        now_utc = datetime.now(UTC)
        cutoff = now_utc - timedelta(hours=hours)
        normalized_items: list[dict[str, Any]] = []

        for source_name, fetcher in (
            ("opennews", self._fetch_opennews_items),
            ("opentwitter", self._fetch_opentwitter_items),
        ):
            try:
                items = fetcher(cutoff=cutoff, now_utc=now_utc)
                source_status[source_name] = {"status": "ok", "count": len(items), "error": ""}
                normalized_items.extend(items)
            except RuntimeError as exc:
                message = str(exc)
                warnings.append(f"{source_name} unavailable: {message}")
                source_status[source_name] = {"status": "error", "count": 0, "error": message}

        if not normalized_items:
            error_text = "; ".join(warnings) if warnings else "No hot events were fetched"
            raise RuntimeError(error_text)

        deduped: dict[str, dict[str, Any]] = {}
        for item in normalized_items:
            dedupe_key = str(item.get("url") or item.get("id") or item.get("title"))
            existing = deduped.get(dedupe_key)
            if existing is None or float(item.get("heat_score", 0.0)) > float(existing.get("heat_score", 0.0)):
                deduped[dedupe_key] = item

        sorted_items = sorted(
            deduped.values(),
            key=lambda item: (
                float(item.get("heat_score", 0.0)),
                self._published_sort_key(item.get("published_at")),
            ),
            reverse=True,
        )
        return {"items": sorted_items, "warnings": warnings, "source_status": source_status}

    def _fetch_opennews_items(self, *, cutoff: datetime, now_utc: datetime) -> list[dict[str, Any]]:
        type_payload = self._get_json(self.OPENNEWS_TYPE_PATH)
        news_types = self._extract_news_type_codes(type_payload)

        search_payload: dict[str, Any] = {"limit": 120, "page": 1}
        if news_types:
            search_payload["newsType"] = news_types

        search_result = self._post_json(self.OPENNEWS_SEARCH_PATH, payload=search_payload)
        raw_items = search_result.get("data")
        if not isinstance(raw_items, list):
            return []

        normalized: list[dict[str, Any]] = []
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            normalized_item = self._normalize_news_item(raw_item, cutoff=cutoff, now_utc=now_utc)
            if normalized_item is not None:
                normalized.append(normalized_item)
        return normalized

    def _fetch_opentwitter_items(self, *, cutoff: datetime, now_utc: datetime) -> list[dict[str, Any]]:
        query = self.DEFAULT_TWITTER_QUERY
        query_candidates = self._extract_twitter_query_candidates()
        if query_candidates:
            query = " OR ".join(query_candidates[:5])

        request_payload = {
            "maxResults": 120,
            "product": "Top",
            "keywords": query,
        }
        raw_items: list[dict[str, Any]] | None = None
        for search_path in (self.OPENTWITTER_SEARCH_PATH, self.OPENTWITTER_LEGACY_SEARCH_PATH):
            try:
                payload = self._post_json(search_path, payload=request_payload)
            except RuntimeError:
                continue

            items = payload.get("data")
            if not isinstance(items, list):
                continue

            raw_items = [item for item in items if isinstance(item, dict)]
            break

        if raw_items is None:
            raise RuntimeError(self.OPENTWITTER_UNAVAILABLE_ERROR)

        normalized: list[dict[str, Any]] = []
        for raw_item in raw_items:
            normalized_item = self._normalize_tweet_item(raw_item, cutoff=cutoff, now_utc=now_utc)
            if normalized_item is not None:
                normalized.append(normalized_item)
        return normalized

    def _extract_news_type_codes(self, payload: dict[str, Any]) -> list[str]:
        data = payload.get("data")
        if not isinstance(data, list):
            return []

        candidates: list[tuple[int, str]] = []
        for group in data:
            if not isinstance(group, dict):
                continue
            categories = group.get("categories")
            if not isinstance(categories, list):
                continue
            for category in categories:
                if not isinstance(category, dict):
                    continue
                code = str(category.get("code") or "").strip()
                if not code:
                    continue
                sort_value = int(category.get("sort") or 0)
                ai_enabled = bool(category.get("aiEnabled", False))
                if not ai_enabled and sort_value <= 0:
                    continue
                candidates.append((sort_value, code))

        candidates.sort(key=lambda item: item[0], reverse=True)
        deduped: list[str] = []
        seen: set[str] = set()
        for _, code in candidates:
            normalized = code.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(code)
            if len(deduped) >= 20:
                break
        return deduped

    def _extract_twitter_query_candidates(self) -> list[str]:
        try:
            payload = self._get_json(self.OPENTWITTER_TYPE_PATH)
        except RuntimeError:
            return []

        data = payload.get("data")
        if not isinstance(data, list):
            return []

        tokens: list[str] = []
        for group in data:
            if not isinstance(group, dict):
                continue
            categories = group.get("categories")
            if not isinstance(categories, list):
                continue
            for category in categories:
                if not isinstance(category, dict):
                    continue
                name = str(category.get("enName") or category.get("name") or "").strip()
                if len(name) < 2:
                    continue
                cleaned = _WHITESPACE_RE.sub(" ", name).strip()
                if not cleaned:
                    continue
                tokens.append(cleaned)

        deduped: list[str] = []
        seen: set[str] = set()
        for token in tokens:
            normalized = token.lower()
            if normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(token)
            if len(deduped) >= 10:
                break
        return deduped

    def _normalize_news_item(
        self,
        raw_item: dict[str, Any],
        *,
        cutoff: datetime,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        text = self._clean_text(raw_item.get("text"))
        if not text:
            return None

        published_at = self._normalize_published_at(raw_item.get("ts"))
        published_dt = self._parse_iso_datetime(published_at)
        if published_dt is not None and published_dt < cutoff:
            return None

        ai_rating = raw_item.get("aiRating")
        ai_rating_score = 0.0
        ai_summary = ""
        if isinstance(ai_rating, dict):
            ai_rating_score = self._safe_float(ai_rating.get("score"))
            ai_summary = self._clean_text(ai_rating.get("enSummary") or ai_rating.get("summary"))

        title = text[:140]
        summary = self._clean_text(ai_summary or raw_item.get("description") or text)[:500]
        news_type = self._clean_text(raw_item.get("newsType"))
        source = self._clean_text(raw_item.get("source") or news_type or "opennews")
        url = str(raw_item.get("link") or "").strip()
        source_domain = self._source_domain(url, source)
        raw_id = str(raw_item.get("id") or "").strip()
        event_id = raw_id or self._build_event_id(
            category="news",
            subcategory=news_type,
            title=title,
            published_at=published_at,
        )
        heat_score = self._compute_heat_score(
            base_score=ai_rating_score,
            source_weight=self.fusion_settings.source_weight_news,
            published_dt=published_dt,
            now_utc=now_utc,
        )

        return {
            "id": f"news:{news_type}:{event_id}",
            "title": title,
            "summary": summary,
            "url": url,
            "source": source,
            "source_domain": source_domain,
            "published_at": published_at,
            "relative_age_hint": self._relative_age_hint(published_dt, now_utc),
            "heat_score": heat_score,
            "category": "news",
            "subcategory": news_type,
            "content_type": "news",
            "author_handle": "",
        }

    def _normalize_tweet_item(
        self,
        raw_item: dict[str, Any],
        *,
        cutoff: datetime,
        now_utc: datetime,
    ) -> dict[str, Any] | None:
        text = self._clean_text(raw_item.get("text"))
        if not text:
            return None

        published_at = self._normalize_published_at(raw_item.get("createdAt"))
        published_dt = self._parse_iso_datetime(published_at)
        if published_dt is not None and published_dt < cutoff:
            return None

        tweet_id = str(raw_item.get("id") or "").strip()
        author_handle = self._clean_text(raw_item.get("userScreenName"))
        author_name = self._clean_text(raw_item.get("userName"))
        source = f"@{author_handle}" if author_handle else (author_name or "x")
        url = ""
        if tweet_id and author_handle:
            url = f"https://x.com/{author_handle}/status/{tweet_id}"

        retweets = self._safe_float(raw_item.get("retweetCount"))
        likes = self._safe_float(raw_item.get("favoriteCount"))
        replies = self._safe_float(raw_item.get("replyCount"))
        quotes = self._safe_float(raw_item.get("quoteCount"))
        followers = self._safe_float(raw_item.get("userFollowers"))
        explicit_score = self._safe_float(raw_item.get("score"))
        inferred_score = (
            retweets * self.fusion_settings.tweet_weight_retweet
            + likes * self.fusion_settings.tweet_weight_like
            + replies * self.fusion_settings.tweet_weight_reply
            + quotes * self.fusion_settings.tweet_weight_quote
            + min(followers / 1000.0, self.fusion_settings.tweet_follower_cap_k)
        )
        base_score = explicit_score if explicit_score > 0 else inferred_score
        heat_score = self._compute_heat_score(
            base_score=base_score,
            source_weight=self.fusion_settings.source_weight_tweet,
            published_dt=published_dt,
            now_utc=now_utc,
        )

        title = text[:140]
        summary = text[:500]
        source_domain = self._source_domain(url, "x.com")
        stable_id = tweet_id or self._build_event_id(
            category="tweet",
            subcategory="x",
            title=title,
            published_at=published_at,
        )

        return {
            "id": f"tweet:x:{stable_id}",
            "title": title,
            "summary": summary,
            "url": url,
            "source": source,
            "source_domain": source_domain,
            "published_at": published_at,
            "relative_age_hint": self._relative_age_hint(published_dt, now_utc),
            "heat_score": heat_score,
            "category": "social",
            "subcategory": "x",
            "content_type": "tweet",
            "author_handle": author_handle,
        }

    def _get_json(self, path: str) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.get(url, headers=self._auth_headers(), timeout=self.timeout_seconds)
            response.raise_for_status()
            payload = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"GET {path} failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"GET {path} returned invalid JSON") from exc

        if not isinstance(payload, dict):
            raise RuntimeError(f"GET {path} returned a non-object payload")
        if payload.get("success") is False:
            raise RuntimeError(f"GET {path} returned unsuccessful response: {payload.get('error') or payload}")
        return payload

    def _post_json(self, path: str, *, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.BASE_URL}{path}"
        try:
            response = requests.post(url, headers=self._auth_headers(), json=payload, timeout=self.timeout_seconds)
            response.raise_for_status()
            body = response.json()
        except requests.RequestException as exc:
            raise RuntimeError(f"POST {path} failed: {exc}") from exc
        except ValueError as exc:
            raise RuntimeError(f"POST {path} returned invalid JSON") from exc

        if not isinstance(body, dict):
            raise RuntimeError(f"POST {path} returned a non-object payload")
        if body.get("success") is False:
            raise RuntimeError(f"POST {path} returned unsuccessful response: {body.get('error') or body}")
        return body

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_token}"}

    @staticmethod
    def _safe_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _clean_text(value: Any) -> str:
        text = html.unescape(str(value or ""))
        text = _TAG_RE.sub(" ", text)
        text = _WHITESPACE_RE.sub(" ", text).strip()
        return text

    @staticmethod
    def _source_domain(url: str, source: str) -> str:
        if url:
            parsed = urlparse(url)
            hostname = (parsed.hostname or "").strip().lower()
            if hostname.startswith("www."):
                hostname = hostname[4:]
            if hostname:
                return hostname
        return source.strip().lower()

    @staticmethod
    def _build_event_id(*, category: str, subcategory: str, title: str, published_at: str) -> str:
        seed = f"{category}|{subcategory}|{title}|{published_at}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]

    @staticmethod
    def _normalize_published_at(value: Any) -> str:
        text = str(value or "").strip()
        if not text:
            return ""
        parsed = HotEventsService._parse_iso_datetime(text)
        if parsed is None:
            return text
        return parsed.replace(microsecond=0).isoformat()

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            try:
                parsed = datetime.strptime(text, "%a %b %d %H:%M:%S %z %Y")
            except ValueError:
                return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    @staticmethod
    def _relative_age_hint(published_dt: datetime | None, now_utc: datetime) -> str:
        if published_dt is None:
            return "unknown"
        delta_seconds = int((now_utc - published_dt).total_seconds())
        if delta_seconds < 60:
            return "just now"
        minutes = delta_seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        return f"{days}d ago"

    @staticmethod
    def _published_sort_key(value: Any) -> float:
        parsed = HotEventsService._parse_iso_datetime(value)
        if parsed is None:
            return 0.0
        return parsed.timestamp()

    def _compute_heat_score(
        self,
        *,
        base_score: float,
        source_weight: float,
        published_dt: datetime | None,
        now_utc: datetime,
    ) -> float:
        weighted = max(0.0, float(base_score)) * max(0.0, float(source_weight))
        decayed = weighted * self._time_decay_multiplier(published_dt=published_dt, now_utc=now_utc)
        return round(self._clamp_heat_score(decayed), 3)

    def _time_decay_multiplier(self, *, published_dt: datetime | None, now_utc: datetime) -> float:
        if published_dt is None:
            return 1.0
        age_hours = max(0.0, (now_utc - published_dt).total_seconds() / 3600.0)
        half_life_hours = max(0.1, float(self.fusion_settings.time_decay_half_life_hours))
        return 0.5 ** (age_hours / half_life_hours)

    def _clamp_heat_score(self, value: float) -> float:
        max_heat_score = max(1.0, float(self.fusion_settings.max_heat_score))
        return min(max_heat_score, max(0.0, float(value)))
