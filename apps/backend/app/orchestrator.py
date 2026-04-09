from __future__ import annotations

import concurrent.futures
import logging
import re
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from app.config import SUPPORTED_TRANSLATION_LANGUAGES, Settings
from app.database import Database
from app.hot_events import HotEventsService
from app.llm import LLMClient, LLMError
from app.logging_utils import get_logger, log_event
from app.persona import (
    expand_related_keywords,
    extract_personal_phrases_unbounded,
    extract_theme_keywords,
    extract_top_theme_keywords,
    select_theme_tweets,
)
from app.schemas import ContentGenerateRequest, ContentVariantType, TrendingGenerateRequest
from app.web_enrichment import WebEnricher

logger = get_logger(__name__)
_HIRAGANA_KATAKANA_RE = re.compile(r"[\u3040-\u30ff]")
_HANGUL_RE = re.compile(r"[\uac00-\ud7af]")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_SPANISH_HINT_RE = re.compile(r"[ñáéíóúü¿¡]", flags=re.IGNORECASE)
_SPANISH_STOPWORDS = {
    "de",
    "la",
    "el",
    "que",
    "y",
    "en",
    "los",
    "las",
    "por",
    "para",
    "con",
    "del",
}


class ContentOrchestrator:
    VARIANTS: tuple[ContentVariantType, ...] = ("normal", "expansion", "open")

    def __init__(
        self,
        *,
        settings: Settings,
        database: Database,
        llm: LLMClient,
        web_enricher: WebEnricher | None = None,
        hot_events_service: HotEventsService | None = None,
    ):
        self.settings = settings
        self.database = database
        self.llm = llm
        self.web_enricher = web_enricher or WebEnricher(
            timeout_seconds=settings.web_enrichment.timeout_seconds,
            max_items=settings.web_enrichment.max_items,
            recency_hours=settings.web_enrichment.recency_hours,
        )
        self.hot_events_service = hot_events_service or HotEventsService(
            timeout_seconds=settings.web_enrichment.timeout_seconds,
            cache_ttl_seconds=120,
            api_token=settings.hot_events.provider_6551_token,
            fusion_settings=settings.hot_events.fusion,
        )
        self._hot_events_refresh_lock = threading.Lock()
        self._hot_events_refreshing = threading.Event()
        self._hot_events_last_refresh_monotonic: float = 0.0
        self._hot_events_last_attempted_at: str = ""
        self._hot_events_last_refresh_error: str = ""
        self._hot_events_last_warnings: list[str] = []
        self._hot_events_last_source_status: dict[str, Any] = {}
        self._debug_runs: dict[str, dict[str, Any]] = {}

    def suggest_ideas(self, *, direction: str, domain: str, topic_hint: str, limit: int) -> dict[str, Any]:
        query = " ".join(part for part in [direction, domain, topic_hint] if part).strip() or "crypto ai"
        enrichment = self.web_enricher.search_recent_topic_signals(query, [])
        ideas = []
        for item in enrichment.get("items", [])[:limit]:
            ideas.append(
                {
                    "topic": item.get("title", "")[:120],
                    "summary": item.get("summary", "")[:280],
                    "keywords": extract_theme_keywords(f"{item.get('title', '')} {item.get('summary', '')}"),
                    "source": item.get("source", ""),
                    "published_at": item.get("published_at", ""),
                    "url": item.get("url", ""),
                }
            )
        return {
            "ideas": ideas,
            "query": query,
            "suggested_keywords": enrichment.get("keywords", [])[:20],
        }

    def list_hot_events(self, *, hours: int, limit: int, refresh: bool, language: str | None = None) -> dict[str, Any]:
        bounded_hours = self._bound_hot_events_hours(hours)
        bounded_limit = self._bound_hot_events_limit(limit)
        if refresh:
            try:
                return self.refresh_hot_events_snapshot(
                    hours=bounded_hours,
                    limit=bounded_limit,
                    language=language,
                )
            except RuntimeError as exc:
                self._hot_events_last_refresh_error = str(exc)
                self._hot_events_last_attempted_at = self._utc_now_iso()
                fallback = self._get_hot_events_response(
                    hours=bounded_hours,
                    limit=bounded_limit,
                    warnings=[f"hot events refresh failed: {exc}"],
                    last_refresh_error=str(exc),
                    force_stale=True,
                    language=language,
                )
                if not fallback["items"]:
                    raise
                return fallback
        return self._get_hot_events_response(hours=bounded_hours, limit=bounded_limit, language=language)

    def refresh_hot_events_snapshot(
        self,
        *,
        hours: int = 24,
        limit: int = 200,
        language: str | None = None,
    ) -> dict[str, Any]:
        bounded_hours = self._bound_hot_events_hours(hours)
        bounded_limit = self._bound_hot_events_limit(limit)
        if not self._hot_events_refresh_lock.acquire(blocking=False):
            currently_refreshing = self._hot_events_refreshing.is_set()
            attempted_at = self._utc_now_iso()
            self._hot_events_last_attempted_at = attempted_at
            return self._get_hot_events_response(
                hours=bounded_hours,
                limit=bounded_limit,
                last_attempted_at=attempted_at,
                last_refresh_error=self._hot_events_last_refresh_error,
                refreshing=currently_refreshing,
                allow_live_translation=not currently_refreshing,
                language=language,
            )

        try:
            attempted_at = self._utc_now_iso()
            self._hot_events_last_attempted_at = attempted_at
            throttled, next_refresh_available_in_seconds = self._get_hot_events_refresh_throttle()
            if throttled:
                return self._get_hot_events_response(
                    hours=bounded_hours,
                    limit=bounded_limit,
                    last_attempted_at=attempted_at,
                    last_refresh_error=self._hot_events_last_refresh_error,
                    throttled=True,
                    next_refresh_available_in_seconds=next_refresh_available_in_seconds,
                    refreshing=False,
                    language=language,
                )

            self._hot_events_refreshing.set()
            refreshed_at = attempted_at
            payload = self.hot_events_service.list_hot_events(hours=bounded_hours, limit=200, refresh=True)
            items_value = payload.get("items")
            items = [item for item in items_value if isinstance(item, dict)] if isinstance(items_value, list) else []
            stored_count = self.database.upsert_hot_events(items, refreshed_at)
            self._hot_events_last_refresh_monotonic = time.monotonic()
            self._hot_events_last_refresh_error = ""
            warnings = self._coerce_string_list(payload.get("warnings"))
            source_status = self._coerce_dict(payload.get("source_status"))
            translation_warnings = self._pre_translate_hot_events(items)
            self._hot_events_last_warnings = warnings + translation_warnings
            self._hot_events_last_source_status = source_status
            log_level = logging.WARNING if payload.get("warnings") else logging.INFO
            log_event(
                logger,
                log_level,
                "hot_events_refresh_persisted",
                hours=bounded_hours,
                stored_count=stored_count,
                warnings=self._hot_events_last_warnings,
                source_status=source_status,
            )
            return self._get_hot_events_response(
                hours=bounded_hours,
                limit=bounded_limit,
                warnings=self._hot_events_last_warnings,
                source_status=self._hot_events_last_source_status,
                last_refreshed_at=refreshed_at,
                last_attempted_at=attempted_at,
                force_stale=False,
                throttled=False,
                next_refresh_available_in_seconds=0,
                refreshing=False,
                language=language,
            )
        finally:
            self._hot_events_refreshing.clear()
            self._hot_events_refresh_lock.release()

    def generate_trending_content(self, payload: TrendingGenerateRequest, request_id: str) -> dict[str, Any]:
        selected_event = self._resolve_trending_event(payload)
        topic = str(selected_event.get("title") or "").strip()
        summary = str(selected_event.get("summary") or "").strip()
        if not topic:
            raise ValueError("Selected event is missing a title")

        user_comment = payload.comment.strip()
        idea = user_comment
        if summary:
            if idea:
                idea = f"{idea}\n\nEvent context: {topic}. {summary}"
            else:
                idea = summary
        if not idea:
            idea = topic

        keyword_seed = " ".join(
            part
            for part in [
                topic,
                summary,
                str(selected_event.get("source") or ""),
                str(selected_event.get("source_domain") or ""),
            ]
            if part
        )
        keywords = extract_theme_keywords(keyword_seed)[:20]
        generate_payload = ContentGenerateRequest(
            username=payload.username,
            mode="B",
            idea=idea,
            direction=str(selected_event.get("category") or ""),
            domain=str(selected_event.get("subcategory") or ""),
            topic=topic,
            keywords=keywords,
            draft_count=payload.draft_count,
        )
        return self.generate_content(generate_payload, request_id=request_id)

    def analyze_exposure(self, *, username: str, text: str, topic: str, domain: str) -> dict[str, Any]:
        keywords = extract_theme_keywords(f"{topic} {domain} {text}")
        hashtags = [f"#{token.strip('$')}" for token in keywords[:8] if token and len(token.strip("$")) >= 2]
        windows = self._best_posting_windows(username)
        heat_score, reasons = self._predict_heat_score(text, topic, keywords)
        if heat_score >= 75:
            heat_label = "high"
        elif heat_score >= 50:
            heat_label = "medium"
        else:
            heat_label = "low"
        return {
            "hashtags": hashtags,
            "best_posting_windows": windows,
            "heat_score": heat_score,
            "heat_label": heat_label,
            "reasons": reasons,
        }

    def get_debug(self, request_id: str) -> dict[str, Any] | None:
        return self._debug_runs.get(request_id)

    def generate_content(self, payload: ContentGenerateRequest, request_id: str) -> dict[str, Any]:
        topic = self._resolve_topic(payload)
        if payload.mode == "B" and not topic:
            raise ValueError("Mode B requires a topic after idea selection. Call /api/v1/content/ideas first.")
        if not topic:
            raise ValueError("Missing topic. Provide topic, idea, or keywords.")

        user = self.database.get_user_by_username(payload.username)
        if user is None:
            raise LookupError("Profile not found")
        snapshot = self.database.get_latest_persona_snapshot(payload.username)
        if snapshot is None:
            raise LookupError("Persona not found. Run /api/v1/profiles/ingest first")

        tweet_rows = self.database.get_user_tweets(user["id"])
        source_texts = [row["text"] for row in tweet_rows if row.get("text")]

        base_keywords = self._build_base_keywords(payload, topic)
        matched = select_theme_tweets(tweet_rows, base_keywords) if base_keywords else []
        personal_phrases = extract_personal_phrases_unbounded(matched)

        web_enrichment_used = False
        web_keywords: list[str] = []
        source_facts: list[dict[str, Any]] = []
        if len(matched) < 3 and self.settings.web_enrichment.enabled:
            web = self.web_enricher.search_recent_topic_signals(topic, base_keywords)
            web_keywords = web.get("keywords", [])
            source_facts = web.get("facts", [])
            web_enrichment_used = bool(web_keywords or source_facts)

        used_keywords = expand_related_keywords(base_keywords, web_keywords, personal_phrases, limit=30)
        themed_tweets = select_theme_tweets(tweet_rows, used_keywords) if used_keywords else matched
        if not themed_tweets:
            themed_tweets = matched
        theme_top_keywords = extract_top_theme_keywords(
            themed_tweets, used_keywords, prompt=payload.idea or topic, limit=5
        )

        variants: list[dict[str, Any]] = []
        variant_debug: list[dict[str, Any]] = []
        variant_failures: list[dict[str, str]] = []
        quality_gate_event = threading.Event()
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(self.settings.content.variant_max_workers, len(self.VARIANTS)),
        ) as executor:
            future_to_variant = {
                executor.submit(
                    self._run_variant_generation,
                    variant=variant,
                    payload=payload,
                    topic=topic,
                    snapshot=snapshot,
                    source_texts=source_texts,
                    tweet_rows=tweet_rows,
                    used_keywords=used_keywords,
                    web_keywords=web_keywords,
                    personal_phrases=personal_phrases,
                    source_facts=source_facts,
                    theme_top_keywords=theme_top_keywords,
                    web_enrichment_used=web_enrichment_used,
                    request_id=request_id,
                    quality_gate_event=quality_gate_event,
                ): variant
                for variant in self.VARIANTS
            }
            for future in concurrent.futures.as_completed(future_to_variant):
                variant = future_to_variant[future]
                try:
                    variant_result = future.result()
                except RuntimeError as exc:
                    error_text = str(exc)
                    variant_failures.append({"variant": variant, "error": error_text})
                    log_event(
                        logger,
                        logging.WARNING,
                        "content_variant_generation_failed",
                        request_id=request_id,
                        topic=topic,
                        variant=variant,
                        error=error_text,
                    )
                    continue
                variants.append(variant_result["output"])
                variant_debug.append(variant_result["debug"])

        if not variants:
            detail = variant_failures[0]["error"] if variant_failures else "No variants produced content"
            raise LLMError(detail)

        recommended = max(variants, key=lambda item: float(item["score"]["final_score"]))
        quality_gate_met = any(bool(item.get("target_score_met", False)) for item in variants)
        overall_web_enrichment_used = web_enrichment_used or any(
            any(bool(round_item.get("web_enrichment_used", False)) for round_item in debug_item.get("rounds", []))
            for debug_item in variant_debug
        )
        quality_gate_reason = ""
        if not quality_gate_met:
            quality_gate_reason = (
                "No variant reached score >= 9.0 after retries. "
                "Web enrichment was applied when available; "
                "consider refining topic/idea or increasing history coverage."
            )
        response = {
            "request_id": request_id,
            "mode": payload.mode,
            "topic": topic,
            "variants": variants,
            "recommended_variant": recommended["variant"],
            "drafts": recommended["drafts"],
            "formatted_drafts": recommended["formatted_drafts"],
            "score": recommended["score"],
            "target_score_met": recommended["target_score_met"],
            "quality_gate_met": quality_gate_met,
            "quality_gate_reason": quality_gate_reason,
            "retry_count": recommended["retry_count"],
            "history_match_count": len(matched),
            "web_enrichment_used": overall_web_enrichment_used,
            "used_keywords": used_keywords,
            "web_keywords": web_keywords,
            "personal_phrases": personal_phrases,
            "source_facts": source_facts[:8],
            "debug_summary": self._debug_summary(
                len(matched), overall_web_enrichment_used, float(recommended["score"]["final_score"])
            ),
        }

        self._debug_runs[request_id] = {
            "request_id": request_id,
            "mode": payload.mode,
            "topic": topic,
            "history_match_count": len(matched),
            "web_enrichment_used": overall_web_enrichment_used,
            "rounds": next((item["rounds"] for item in variant_debug if item["variant"] == recommended["variant"]), []),
            "variants": variant_debug,
            "recommended_variant": recommended["variant"],
            "score": recommended["score"],
            "used_keywords": used_keywords,
            "web_keywords": web_keywords,
            "source_facts": source_facts[:8],
        }

        log_event(
            logger,
            logging.INFO,
            "content_orchestrator_completed",
            request_id=request_id,
            topic=topic,
            history_match_count=len(matched),
            web_enrichment_used=response["web_enrichment_used"],
            final_score=recommended["score"]["final_score"],
            recommended_variant=recommended["variant"],
        )
        return response

    def _run_variant_generation(
        self,
        *,
        variant: ContentVariantType,
        payload: ContentGenerateRequest,
        topic: str,
        snapshot: dict[str, Any],
        source_texts: list[str],
        tweet_rows: list[dict[str, Any]],
        used_keywords: list[str],
        web_keywords: list[str],
        personal_phrases: list[str],
        source_facts: list[dict[str, Any]],
        theme_top_keywords: list[str],
        web_enrichment_used: bool,
        request_id: str,
        quality_gate_event: threading.Event | None = None,
    ) -> dict[str, Any]:
        rounds: list[dict[str, Any]] = []
        best_result: dict[str, Any] | None = None
        best_score: dict[str, float] | None = None
        local_web_used = web_enrichment_used
        local_web_keywords = list(web_keywords)
        local_source_facts = list(source_facts)
        local_used_keywords = list(used_keywords)

        for round_index in range(1, self.settings.content.rewrite_max_rounds + 1):
            if quality_gate_event is not None and quality_gate_event.is_set() and best_result is not None:
                break
            prompt = self._build_generation_prompt(
                payload=payload,
                topic=topic,
                used_keywords=local_used_keywords,
                personal_phrases=personal_phrases,
                source_facts=local_source_facts,
                theme_top_keywords=theme_top_keywords,
                variant=variant,
                rewrite_hint="" if best_score is None else self._rewrite_hint(best_score),
            )
            try:
                draft_result = self.llm.generate_drafts(
                    persona=snapshot["persona"],
                    prompt=prompt,
                    representative_tweets=snapshot["representative_tweets"],
                    source_texts=source_texts,
                    tweet_rows=tweet_rows,
                    draft_count=payload.draft_count,
                    request_id=request_id,
                )
            except LLMError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "content_variant_round_failed",
                    request_id=request_id,
                    variant=variant,
                    round_index=round_index,
                    error=str(exc),
                )
                if best_result is not None and best_score is not None:
                    break
                raise
            score = self._score_generated_content(
                draft_result=draft_result,
                topic=topic,
                used_keywords=local_used_keywords,
                personal_phrases=personal_phrases,
            )
            rounds.append(
                {
                    "round_index": round_index,
                    "final_score": score["final_score"],
                    "web_enrichment_used": local_web_used,
                    "used_keywords": local_used_keywords,
                    "note": "ok" if score["final_score"] >= 9.0 else "needs_revision",
                }
            )

            if best_result is None or score["final_score"] > (best_score or {}).get("final_score", 0.0):
                best_result = draft_result
                best_score = score

            target_met = score["final_score"] >= 9.0 and bool(draft_result.get("target_score_met", False))
            if target_met:
                if quality_gate_event is not None:
                    quality_gate_event.set()
                break

            if self.settings.web_enrichment.enabled:
                web = self.web_enricher.search_recent_topic_signals(topic, local_used_keywords)
                extra_keywords = web.get("keywords", [])
                extra_facts = web.get("facts", [])
                if extra_keywords or extra_facts:
                    local_web_used = True
                    local_web_keywords = expand_related_keywords(local_web_keywords, extra_keywords, [], limit=30)
                    local_source_facts = local_source_facts + extra_facts
                    local_used_keywords = expand_related_keywords(
                        local_used_keywords, local_web_keywords, personal_phrases, limit=30
                    )

        if best_result is None or best_score is None:
            raise LookupError("Content generation could not produce any draft candidates")
        drafts = best_result.get("drafts", [])
        formatted_drafts = [f"{index}. {item.get('text', '').strip()}" for index, item in enumerate(drafts, 1)]
        target_score_met = best_score["final_score"] >= 9.0 and bool(best_result.get("target_score_met", False))
        output = {
            "variant": variant,
            "label": self._variant_label(variant),
            "drafts": drafts,
            "formatted_drafts": formatted_drafts,
            "score": best_score,
            "target_score_met": target_score_met,
            "retry_count": max(0, len(rounds) - 1),
            "quality_gate_reason": "" if target_score_met else self._variant_not_met_reason(best_score, rounds),
            "compensation_used": any(bool(item.get("web_enrichment_used", False)) for item in rounds),
            "used_keywords": local_used_keywords,
            "source_facts": local_source_facts[:8],
        }
        debug = {
            "variant": variant,
            "rounds": rounds,
            "score": best_score,
            "target_score_met": target_score_met,
        }
        return {"output": output, "debug": debug}

    def _resolve_trending_event(self, payload: TrendingGenerateRequest) -> dict[str, Any]:
        event_payload = payload.event_payload
        if isinstance(event_payload, dict):
            title = str(event_payload.get("title") or "").strip()
            if not title:
                raise ValueError("event_payload.title is required")
            return event_payload

        event_id = payload.event_id.strip()
        if not event_id:
            raise ValueError("event_id or event_payload is required")

        event = self.database.get_hot_event_by_id(event_id, published_since=self._hot_events_cutoff_iso(24))
        if event is None:
            raise LookupError("Selected hot event was not found")
        return self._public_hot_event_item(event)

    @staticmethod
    def _bound_hot_events_hours(hours: int) -> int:
        return max(1, min(72, int(hours)))

    @staticmethod
    def _bound_hot_events_limit(limit: int) -> int:
        return max(1, min(200, int(limit)))

    @staticmethod
    def _utc_now_iso() -> str:
        return datetime.now(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        text = str(value or "").strip()
        if not text:
            return None

        normalized = text.replace("Z", "+00:00")
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(UTC)

    def _hot_events_cutoff_iso(self, hours: int) -> str:
        return (datetime.now(UTC).replace(microsecond=0) - self._hours_delta(hours)).isoformat()

    def _get_hot_events_response(
        self,
        *,
        hours: int,
        limit: int,
        warnings: list[str] | None = None,
        source_status: dict[str, Any] | None = None,
        last_refresh_error: str = "",
        last_refreshed_at: str | None = None,
        last_attempted_at: str | None = None,
        force_stale: bool | None = None,
        throttled: bool = False,
        next_refresh_available_in_seconds: int = 0,
        refreshing: bool | None = None,
        allow_live_translation: bool | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        resolved_refreshing = self._hot_events_refreshing.is_set() if refreshing is None else bool(refreshing)
        resolved_allow_live_translation = (
            not resolved_refreshing if allow_live_translation is None else bool(allow_live_translation)
        )
        items = self.database.list_hot_events(
            published_since=self._hot_events_cutoff_iso(hours),
            limit=self._bound_hot_events_limit(limit),
        )
        latest_refresh_time = str(last_refreshed_at or self.database.get_latest_hot_events_refresh_time() or "")
        response_items, translation_warnings = self._build_translated_hot_event_items(
            items,
            language=language,
            allow_live_translation=resolved_allow_live_translation,
        )
        refresh_interval_seconds = max(1, int(self.settings.hot_events.auto_refresh_interval_seconds))
        is_stale = (
            bool(force_stale)
            if force_stale is not None
            else self._is_hot_events_refresh_stale(latest_refresh_time, refresh_interval_seconds)
        )
        resolved_warnings = (
            self._coerce_string_list(warnings) if warnings is not None else list(self._hot_events_last_warnings)
        )
        resolved_warnings.extend(translation_warnings)
        resolved_source_status = (
            self._coerce_dict(source_status) if source_status is not None else dict(self._hot_events_last_source_status)
        )

        return {
            "hours": hours,
            "count": len(response_items),
            "items": response_items,
            "warnings": resolved_warnings,
            "source_status": resolved_source_status,
            "last_refreshed_at": latest_refresh_time,
            "last_attempted_at": str(last_attempted_at or self._hot_events_last_attempted_at or latest_refresh_time),
            "refresh_interval_seconds": refresh_interval_seconds,
            "is_stale": is_stale,
            "refreshing": resolved_refreshing,
            "throttled": bool(throttled),
            "next_refresh_available_in_seconds": max(0, int(next_refresh_available_in_seconds)),
            "last_refresh_error": str(last_refresh_error or self._hot_events_last_refresh_error or ""),
        }

    def _is_hot_events_refresh_stale(self, last_refreshed_at: Any, refresh_interval_seconds: int) -> bool:
        refreshed_at = self._parse_iso_datetime(last_refreshed_at)
        if refreshed_at is None:
            return False
        age_seconds = (datetime.now(UTC) - refreshed_at).total_seconds()
        return age_seconds > max(1, int(refresh_interval_seconds))

    @staticmethod
    def _coerce_string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item or "").strip() for item in value if str(item or "").strip()]

    @staticmethod
    def _coerce_dict(value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        return value

    @staticmethod
    def _public_hot_event_item(
        item: dict[str, Any],
        *,
        translation: dict[str, str] | None = None,
        is_translated: bool = False,
    ) -> dict[str, Any]:
        return {
            "id": str(item.get("id") or ""),
            "title": str(item.get("title") or ""),
            "summary": str(item.get("summary") or ""),
            "title_translated": str((translation or {}).get("title_translated") or item.get("title") or ""),
            "summary_translated": str((translation or {}).get("summary_translated") or item.get("summary") or ""),
            "is_translated": bool(is_translated),
            "url": str(item.get("url") or ""),
            "source": str(item.get("source") or ""),
            "source_domain": str(item.get("source_domain") or ""),
            "published_at": str(item.get("published_at") or ""),
            "relative_age_hint": str(item.get("relative_age_hint") or ""),
            "heat_score": float(item.get("heat_score") or 0.0),
            "category": str(item.get("category") or ""),
            "subcategory": str(item.get("subcategory") or ""),
            "content_type": str(item.get("content_type") or "news"),
            "author_handle": str(item.get("author_handle") or ""),
        }

    def _get_hot_events_refresh_throttle(self) -> tuple[bool, int]:
        cooldown_seconds = max(0, int(self.settings.hot_events.min_refresh_cooldown_seconds))
        if cooldown_seconds <= 0 or self._hot_events_last_refresh_monotonic <= 0:
            return False, 0
        remaining_seconds = cooldown_seconds - (time.monotonic() - self._hot_events_last_refresh_monotonic)
        if remaining_seconds <= 0:
            return False, 0
        return True, int(remaining_seconds + 0.999)

    def _pre_translate_hot_events(self, items: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        for language in self.settings.hot_events.pre_translate_languages:
            try:
                self._ensure_hot_event_translations(
                    items,
                    target_language=language,
                    request_id=f"hot-events-pretranslate-{language}",
                )
            except LLMError as exc:
                warnings.append(f"hot events pre-translation failed for {language}: {exc}")
        return warnings

    def _build_translated_hot_event_items(
        self,
        items: list[dict[str, Any]],
        *,
        language: str | None,
        allow_live_translation: bool = True,
    ) -> tuple[list[dict[str, Any]], list[str]]:
        target_language = self._normalize_hot_events_language(language)
        warnings: list[str] = []
        event_ids = [str(item.get("id") or "").strip() for item in items if str(item.get("id") or "").strip()]
        translations = self.database.get_hot_event_translations(event_ids, target_language)
        if allow_live_translation:
            try:
                translations = self._ensure_hot_event_translations(
                    items,
                    target_language=target_language,
                    request_id=f"hot-events-request-{target_language}",
                )
            except LLMError as exc:
                warnings.append(f"hot events translation failed for {target_language}: {exc}")

        response_items: list[dict[str, Any]] = []
        for item in items:
            event_id = str(item.get("id") or "")
            translation = translations.get(event_id)
            source_matches_target = self._hot_event_matches_target_language(item, target_language)
            response_items.append(
                self._public_hot_event_item(
                    item,
                    translation=translation,
                    is_translated=bool(translation) and not source_matches_target,
                )
            )
        return response_items, warnings

    def _ensure_hot_event_translations(
        self,
        items: list[dict[str, Any]],
        *,
        target_language: str,
        request_id: str | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_target_language = self._normalize_hot_events_language(target_language)
        event_ids = [str(item.get("id") or "").strip() for item in items if str(item.get("id") or "").strip()]
        translations = self.database.get_hot_event_translations(event_ids, normalized_target_language)
        missing_items = [
            item
            for item in items
            if str(item.get("id") or "").strip()
            and str(item.get("id") or "").strip() not in translations
            and not self._hot_event_matches_target_language(item, normalized_target_language)
        ]
        if not missing_items:
            return translations

        translated_items = self.llm.translate_hot_events_batch(
            items={
                str(item.get("id") or ""): {
                    "title": str(item.get("title") or ""),
                    "summary": str(item.get("summary") or ""),
                }
                for item in missing_items
                if str(item.get("id") or "").strip()
            },
            target_language=normalized_target_language,
            request_id=request_id,
        )
        created_at = self._utc_now_iso()
        rows = []
        for item in missing_items:
            event_id = str(item.get("id") or "").strip()
            if not event_id:
                continue
            translation = translated_items.get(event_id)
            if not isinstance(translation, dict):
                continue
            original_title = str(item.get("title") or "")
            original_summary = str(item.get("summary") or "")
            title_translated = str(translation.get("title_translated") or original_title)
            summary_translated = str(translation.get("summary_translated") or original_summary)
            if title_translated == original_title and summary_translated == original_summary:
                continue
            rows.append(
                {
                    "event_id": event_id,
                    "target_language": normalized_target_language,
                    "title_translated": title_translated,
                    "summary_translated": summary_translated,
                    "created_at": created_at,
                }
            )
        if rows:
            self.database.save_hot_event_translations(rows)
            translations.update(self.database.get_hot_event_translations(event_ids, normalized_target_language))
        return translations

    def _normalize_hot_events_language(self, language: str | None) -> str:
        normalized = str(language or "en").strip()
        if normalized == "auto":
            normalized = "en"
        if normalized not in SUPPORTED_TRANSLATION_LANGUAGES:
            supported = ", ".join(sorted(SUPPORTED_TRANSLATION_LANGUAGES))
            raise ValueError(f"`lang` must be one of: {supported}")
        return normalized

    def _hot_event_matches_target_language(self, item: dict[str, Any], target_language: str) -> bool:
        source_language = self._detect_hot_event_language(
            f"{str(item.get('title') or '').strip()}\n{str(item.get('summary') or '').strip()}"
        )
        return source_language == self._language_family(target_language)

    def _detect_hot_event_language(self, text: str) -> str:
        normalized = str(text or "").strip()
        if not normalized:
            return "unknown"
        if _HIRAGANA_KATAKANA_RE.search(normalized):
            return "ja"
        if _HANGUL_RE.search(normalized):
            return "ko"
        if _CJK_RE.search(normalized):
            return "zh"
        lowered = normalized.lower()
        if _SPANISH_HINT_RE.search(normalized):
            return "es"
        tokens = re.findall(r"[a-zA-ZÀ-ÿ']+", lowered)
        if len(_SPANISH_STOPWORDS.intersection(tokens)) >= 2:
            return "es"
        if tokens:
            return "en"
        return "unknown"

    @staticmethod
    def _language_family(language: str) -> str:
        if language in {"zh-CN", "zh-TW"}:
            return "zh"
        return language

    @staticmethod
    def _hours_delta(hours: int) -> timedelta:
        return timedelta(hours=max(1, int(hours)))

    def _resolve_topic(self, payload: ContentGenerateRequest) -> str:
        if payload.topic.strip():
            return payload.topic.strip()
        if payload.idea.strip():
            return payload.idea.strip()[:80]
        if payload.keywords:
            return payload.keywords[0].strip()
        return ""

    def _build_base_keywords(self, payload: ContentGenerateRequest, topic: str) -> list[str]:
        seeds: list[str] = []
        seeds.extend(payload.keywords)
        seeds.extend(extract_theme_keywords(f"{payload.idea} {payload.direction} {payload.domain} {topic}"))
        if topic:
            seeds.insert(0, topic)
        deduped: list[str] = []
        seen: set[str] = set()
        for token in seeds:
            normalized = token.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(token.strip())
        return deduped

    def _build_generation_prompt(
        self,
        *,
        payload: ContentGenerateRequest,
        topic: str,
        used_keywords: list[str],
        personal_phrases: list[str],
        source_facts: list[dict[str, Any]],
        theme_top_keywords: list[str],
        variant: ContentVariantType,
        rewrite_hint: str = "",
    ) -> str:
        facts_lines = []
        for item in source_facts[:5]:
            title = item.get("title", "")
            source = item.get("source", "")
            published_at = item.get("published_at", "")
            if title:
                facts_lines.append(f"- {title} | {source} | {published_at}")
        facts_block = "\n".join(facts_lines) if facts_lines else "- (no fresh web facts)"
        phrases_block = " | ".join(personal_phrases) if personal_phrases else "(none)"
        tone = payload.tone or "贴合用户习惯，简洁可发布"
        style_instruction = self._variant_instruction(variant)

        prompt = (
            f"direction: {payload.direction}\n"
            f"domain: {payload.domain}\n"
            f"topic: {topic}\n"
            f"idea: {payload.idea}\n"
            f"tone: {tone}\n"
            f"variant: {variant}\n"
            f"variant_style: {style_instruction}\n"
            f"keywords: {'、'.join(used_keywords)}\n"
            f"top_theme_keywords: {'、'.join(theme_top_keywords)}\n"
            f"personal_phrases_unbounded: {phrases_block}\n"
            f"latest_24h_public_facts:\n{facts_block}\n"
            "output requirements:\n"
            "- output publish-ready posts only\n"
            "- keep Chinese if user asks Chinese\n"
            "- do not copy source facts verbatim\n"
            "- each draft <= 280 chars\n"
            "- keep persona and writing style\n"
        )
        if rewrite_hint:
            prompt += f"\nrewrite_hint: {rewrite_hint}\n"
        return prompt

    def _variant_instruction(self, variant: ContentVariantType) -> str:
        if variant == "normal":
            return "直接表达，贴近原意，结论清晰，可发布性优先。"
        if variant == "expansion":
            return "在原意上补充关联场景、二阶影响和延展观察，但不偏题。"
        return "开放性发散，多给假设与新切口，最后回扣主题和账号人设。"

    def _variant_label(self, variant: ContentVariantType) -> str:
        if variant == "normal":
            return "正常写法"
        if variant == "expansion":
            return "扩展性思维"
        return "开放性思维"

    def _score_generated_content(
        self,
        *,
        draft_result: dict[str, Any],
        topic: str,
        used_keywords: list[str],
        personal_phrases: list[str],
    ) -> dict[str, float]:
        drafts = draft_result.get("drafts", [])
        if not drafts:
            return {"theme_relevance": 0.0, "style_similarity": 0.0, "publishability": 0.0, "final_score": 0.0}

        texts = [item.get("text", "") for item in drafts]
        joined = "\n".join(texts).lower()
        topic_hit = 1.0 if topic.lower() in joined else 0.0
        keyword_hits = sum(1 for keyword in used_keywords[:12] if keyword and keyword.lower() in joined)
        theme_relevance = min(10.0, 6.0 * topic_hit + min(4.0, keyword_hits * 0.6))

        phrase_hits = sum(1 for phrase in personal_phrases[:60] if phrase and phrase.lower() in joined)
        style_similarity = min(10.0, 4.0 + min(6.0, phrase_hits * 0.2))

        best_score = float(draft_result.get("best_score", 0.0))
        length_penalty = 2.5 if any(len(text.strip()) > 280 for text in texts) else 0.0
        publishability = max(0.0, min(10.0, best_score - length_penalty))

        final_score = theme_relevance * 0.4 + style_similarity * 0.4 + publishability * 0.2
        return {
            "theme_relevance": round(theme_relevance, 3),
            "style_similarity": round(style_similarity, 3),
            "publishability": round(publishability, 3),
            "final_score": round(final_score, 3),
        }

    def _rewrite_hint(self, score: dict[str, float]) -> str:
        hints: list[str] = []
        if score["theme_relevance"] < 9.0:
            hints.append("增强主题相关细节，贴近关键词")
        if score["style_similarity"] < 9.0:
            hints.append("融入更多历史惯用表达，强化人设语气")
        if score["publishability"] < 9.0:
            hints.append("提高可发布性，控制篇幅并优化结构")
        return "；".join(hints) if hints else "保持优点并微调语义自然度"

    def _variant_not_met_reason(self, score: dict[str, float], rounds: list[dict[str, Any]]) -> str:
        reasons: list[str] = []
        if score["theme_relevance"] < 9.0:
            reasons.append("theme_relevance<9")
        if score["style_similarity"] < 9.0:
            reasons.append("style_similarity<9")
        if score["publishability"] < 9.0:
            reasons.append("publishability<9")
        if any(bool(item.get("web_enrichment_used", False)) for item in rounds):
            reasons.append("web_compensation_applied")
        if not reasons:
            reasons.append("llm_target_not_met")
        return ",".join(reasons)

    def _debug_summary(self, history_match_count: int, web_enrichment_used: bool, final_score: float) -> str:
        return (
            f"history_match_count={history_match_count}, "
            f"web_enrichment_used={web_enrichment_used}, final_score={final_score}"
        )

    def _best_posting_windows(self, username: str) -> list[str]:
        fallback = ["09:00-10:00", "12:00-13:00", "20:00-22:00"]
        if not username:
            return fallback
        user = self.database.get_user_by_username(username)
        if user is None:
            return fallback
        rows = self.database.get_user_tweets(user["id"], limit=500)
        if not rows:
            return fallback

        hour_scores: dict[int, float] = defaultdict(float)
        for row in rows:
            created_at = row.get("created_at", "")
            try:
                parsed = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                hour = parsed.hour
            except (ValueError, TypeError):
                continue
            score = (
                int(row.get("like_count", 0))
                + int(row.get("retweet_count", 0)) * 2
                + int(row.get("reply_count", 0)) * 2
                + int(row.get("quote_count", 0)) * 3
            )
            hour_scores[hour] += score

        if not hour_scores:
            return fallback
        ranked_hours = sorted(hour_scores.items(), key=lambda item: item[1], reverse=True)[:3]
        windows: list[str] = []
        for hour, _ in ranked_hours:
            next_hour = (hour + 1) % 24
            windows.append(f"{hour:02d}:00-{next_hour:02d}:00")
        return windows

    def _predict_heat_score(self, text: str, topic: str, keywords: list[str]) -> tuple[float, list[str]]:
        reasons: list[str] = []
        score = 35.0
        length = len(text.strip())
        if 50 <= length <= 220:
            score += 18
            reasons.append("篇幅处于易读区间")
        elif length < 30:
            score -= 8
            reasons.append("篇幅偏短，信息密度不足")
        else:
            score += 4
            reasons.append("篇幅偏长，可能降低完读率")

        if topic and topic in text:
            score += 15
            reasons.append("主题锚点明确")
        keyword_hits = sum(1 for keyword in keywords[:8] if keyword and keyword in text)
        if keyword_hits >= 3:
            score += 15
            reasons.append("关键词覆盖充分")
        elif keyword_hits > 0:
            score += 8
            reasons.append("关键词有一定覆盖")
        else:
            reasons.append("关键词覆盖较少")

        if "?" in text or "？" in text:
            score += 8
            reasons.append("包含互动提问，提升评论概率")
        if re.search(r"(欢迎|留言|评论|转发|私信|你怎么看)", text):
            score += 10
            reasons.append("包含明确互动动作")

        score = min(100.0, max(0.0, score))
        return round(score, 2), reasons
