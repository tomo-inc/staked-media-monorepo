from __future__ import annotations

import logging
import time
from typing import Any

import requests

from app.config import Settings
from app.logging_utils import get_logger, log_event, redact_for_log

logger = get_logger(__name__)


class UpstreamError(RuntimeError):
    """Raised when the upstream X data service fails."""


class UpstreamClient:
    def __init__(self, settings: Settings, session: requests.Session | None = None):
        self.settings = settings
        self.session = session or requests.Session()
        # Avoid implicit Windows/system proxy leakage (for example Internet Settings proxy).
        # Upstream proxy must be controlled only by `twitter.data_proxy`.
        if isinstance(self.session, requests.Session):
            self.session.trust_env = False

    def fetch_user_by_username(self, username: str, *, request_id: str | None = None) -> dict[str, Any]:
        log_event(
            logger,
            logging.INFO,
            "upstream_fetch_user_started",
            request_id=request_id,
            username=username,
            provider="twitter_upstream",
            outcome="started",
        )
        payload = self._get_json(f"/api/v1/users/username/{username}", request_id=request_id)
        user = (payload.get("data") or {}).get("data")
        if not user:
            log_event(
                logger,
                logging.WARNING,
                "upstream_fetch_user_missing",
                request_id=request_id,
                username=username,
                provider="twitter_upstream",
                outcome="failed",
            )
            raise UpstreamError(f"User {username} was not found in upstream response")
        log_event(
            logger,
            logging.INFO,
            "upstream_fetch_user_completed",
            request_id=request_id,
            username=username,
            user_id=user.get("id"),
            provider="twitter_upstream",
            outcome="completed",
        )
        return user

    def fetch_user_tweets(
        self,
        user_id: str,
        max_tweets: int | None = None,
        *,
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        max_tweets = max_tweets or self.settings.twitter.max_ingest_tweets
        log_event(
            logger,
            logging.INFO,
            "upstream_fetch_tweets_started",
            request_id=request_id,
            user_id=user_id,
            max_tweets=max_tweets,
            provider="twitter_upstream",
            outcome="started",
        )
        items: list[dict[str, Any]] = []
        cursor: str | None = None
        seen_tweet_ids: set[str] = set()
        seen_cursors: set[str] = set()
        page_count = 0
        stop_reason = "max_tweets_reached"

        while len(items) < max_tweets:
            params = {"cursor": cursor} if cursor else None
            payload = self._get_json(f"/api/v1/tweets/{user_id}", params=params, request_id=request_id)
            data = payload.get("data") or {}
            page_items = data.get("data") or []
            page_count += 1
            log_event(
                logger,
                logging.INFO,
                "upstream_fetch_tweets_page",
                request_id=request_id,
                user_id=user_id,
                cursor_present=bool(cursor),
                page_size=len(page_items),
                accumulated_count=len(items),
                provider="twitter_upstream",
                outcome="completed",
            )
            for item in page_items:
                tweet = item.get("data") or {}
                tweet_id = tweet.get("id")
                if not tweet_id or tweet_id in seen_tweet_ids:
                    continue
                seen_tweet_ids.add(tweet_id)
                items.append(item)
                if len(items) >= max_tweets:
                    break

            next_cursor = data.get("next_cursor")
            if len(items) >= max_tweets:
                stop_reason = "max_tweets_reached"
                break
            if len(page_items) == 0:
                stop_reason = "empty_page"
                break
            if not next_cursor:
                stop_reason = "missing_next_cursor"
                break
            if next_cursor in seen_cursors:
                stop_reason = "repeated_cursor"
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        log_event(
            logger,
            logging.INFO,
            "upstream_fetch_tweets_completed",
            request_id=request_id,
            user_id=user_id,
            max_tweets=max_tweets,
            page_count=page_count,
            total_count=len(items[:max_tweets]),
            stop_reason=stop_reason,
            provider="twitter_upstream",
            outcome="completed",
        )
        return items[:max_tweets]

    def _get_json(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        response = None
        for attempt in range(3):
            started_at = time.perf_counter()
            if hasattr(self.session, "cookies"):
                self.session.cookies.clear()

            log_event(
                logger,
                logging.INFO,
                "upstream_request_started",
                request_id=request_id,
                path=path,
                attempt=attempt + 1,
                params=params or {},
                proxy_enabled=bool(self.settings.twitter.data_proxies),
                provider="twitter_upstream",
                outcome="started",
            )
            try:
                response = self.session.get(
                    f"{self.settings.twitter.data_url.rstrip('/')}{path}",
                    params=params,
                    proxies=self.settings.twitter.data_proxies,
                    timeout=self.settings.llm.request_timeout_seconds,
                )
            except requests.RequestException as exc:
                last_error = exc
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if attempt < 2:
                    log_event(
                        logger,
                        logging.WARNING,
                        "upstream_request_retrying_after_exception",
                        request_id=request_id,
                        path=path,
                        attempt=attempt + 1,
                        error=str(exc),
                        duration_ms=duration_ms,
                        provider="twitter_upstream",
                        outcome="retried",
                    )
                    continue
                log_event(
                    logger,
                    logging.ERROR,
                    "upstream_request_failed_before_response",
                    request_id=request_id,
                    path=path,
                    attempt=attempt + 1,
                    error=str(exc),
                    duration_ms=duration_ms,
                    provider="twitter_upstream",
                    outcome="failed",
                )
                raise UpstreamError(f"Upstream request failed before response: {exc}") from exc
            try:
                response.raise_for_status()
            except requests.HTTPError as exc:
                last_error = exc
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if attempt < 2 and response.status_code >= 500:
                    log_event(
                        logger,
                        logging.WARNING,
                        "upstream_request_retrying",
                        request_id=request_id,
                        path=path,
                        attempt=attempt + 1,
                        status_code=response.status_code,
                        duration_ms=duration_ms,
                        provider="twitter_upstream",
                        outcome="retried",
                    )
                    continue
                detail = response.text[:1000]
                log_event(
                    logger,
                    logging.ERROR,
                    "upstream_request_failed",
                    request_id=request_id,
                    path=path,
                    attempt=attempt + 1,
                    status_code=response.status_code,
                    body_snippet=redact_for_log(detail, self.settings.log.max_body_chars),
                    duration_ms=duration_ms,
                    provider="twitter_upstream",
                    outcome="failed",
                )
                raise UpstreamError(f"Upstream request failed: {detail}") from exc

            try:
                payload = response.json()
            except ValueError as exc:
                last_error = exc
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if attempt < 2:
                    log_event(
                        logger,
                        logging.WARNING,
                        "upstream_response_json_retrying",
                        request_id=request_id,
                        path=path,
                        attempt=attempt + 1,
                        duration_ms=duration_ms,
                        provider="twitter_upstream",
                        outcome="retried",
                    )
                    continue
                snippet = response.text[:1000]
                log_event(
                    logger,
                    logging.ERROR,
                    "upstream_response_json_invalid",
                    request_id=request_id,
                    path=path,
                    attempt=attempt + 1,
                    body_snippet=redact_for_log(snippet, self.settings.log.max_body_chars),
                    duration_ms=duration_ms,
                    provider="twitter_upstream",
                    outcome="failed",
                )
                raise UpstreamError("Upstream response is not valid JSON") from exc
            if payload.get("code") not in (None, 200):
                last_error = UpstreamError(f"Upstream returned application error: {payload}")
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if attempt < 2:
                    log_event(
                        logger,
                        logging.WARNING,
                        "upstream_application_retrying",
                        request_id=request_id,
                        path=path,
                        attempt=attempt + 1,
                        payload_code=payload.get("code"),
                        duration_ms=duration_ms,
                        provider="twitter_upstream",
                        outcome="retried",
                    )
                    continue
                log_event(
                    logger,
                    logging.ERROR,
                    "upstream_application_failed",
                    request_id=request_id,
                    path=path,
                    payload_code=payload.get("code"),
                    body_snippet=redact_for_log(payload, self.settings.log.max_body_chars),
                    duration_ms=duration_ms,
                    provider="twitter_upstream",
                    outcome="failed",
                )
                raise last_error
            log_event(
                logger,
                logging.INFO,
                "upstream_request_completed",
                request_id=request_id,
                path=path,
                attempt=attempt + 1,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                provider="twitter_upstream",
                outcome="completed",
            )
            return payload

        if response is not None:
            log_event(
                logger,
                logging.ERROR,
                "upstream_request_exhausted",
                request_id=request_id,
                path=path,
                body_snippet=redact_for_log(response.text[:1000], self.settings.log.max_body_chars),
                provider="twitter_upstream",
                outcome="failed",
            )
            raise UpstreamError(f"Upstream request failed: {response.text[:1000]}") from last_error
        log_event(
            logger,
            logging.ERROR,
            "upstream_request_no_response",
            request_id=request_id,
            path=path,
            provider="twitter_upstream",
            outcome="failed",
        )
        raise UpstreamError("Upstream request failed before a response was received") from last_error
