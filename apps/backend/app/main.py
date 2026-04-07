from __future__ import annotations

import logging
import threading
import time
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request

from app.config import Settings, get_settings
from app.database import Database, normalize_username
from app.llm import LLMClient, LLMError, create_llm_client
from app.logging_utils import configure_logging, format_log_event, get_logger, log_event, redact_for_log
from app.orchestrator import ContentOrchestrator
from app.persona import build_corpus_stats
from app.schemas import (
    ContentDebugResponse,
    ContentGenerateRequest,
    ContentGenerateResponse,
    ContentIdeasRequest,
    ContentIdeasResponse,
    ConversationGenerateRequest,
    DraftGenerateRequest,
    DraftGenerateResponse,
    ExposureAnalyzeRequest,
    ExposureAnalyzeResponse,
    HotEventsResponse,
    IngestResponse,
    ProfileIngestRequest,
    ProfileRebuildPersonaRequest,
    ProfileRebuildPersonaResponse,
    ProfileResponse,
    ProfileSummary,
    WhitelistUsernameRequest,
    WhitelistUsernamesResponse,
)
from app.upstream import UpstreamClient, UpstreamError

logger = get_logger(__name__)
WHITELIST_FORBIDDEN_DETAIL = "Target username is not in the trial whitelist"


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _run_hot_events_refresh_once(app: FastAPI, *, trigger: str) -> None:
    refresh_hot_events_snapshot = getattr(app.state.content_orchestrator, "refresh_hot_events_snapshot", None)
    if not callable(refresh_hot_events_snapshot):
        return

    try:
        result = refresh_hot_events_snapshot(hours=24)
    except Exception as exc:  # noqa: BLE001
        logger.exception(
            format_log_event(
                "hot_events_refresh_failed",
                trigger=trigger,
                hours=24,
                error=str(exc),
            )
        )
        return

    result_payload = result if isinstance(result, dict) else {}
    log_event(
        logger,
        logging.INFO,
        "hot_events_refresh_completed",
        trigger=trigger,
        hours=24,
        count=int(result_payload.get("count", 0)),
        is_stale=bool(result_payload.get("is_stale", False)),
        last_refreshed_at=result_payload.get("last_refreshed_at"),
    )


def _hot_events_refresh_scheduler_loop(app: FastAPI, stop_event: threading.Event) -> None:
    interval_seconds = max(1, int(app.state.settings.hot_events_refresh_interval_seconds))
    while not stop_event.wait(interval_seconds):
        _run_hot_events_refresh_once(app, trigger="scheduler")


def create_app(
    settings: Settings | None = None,
    *,
    upstream_client: UpstreamClient | None = None,
    llm_client: LLMClient | None = None,
    content_orchestrator: ContentOrchestrator | None = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    database = Database(settings.database_path)
    database.init()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.database.init()
        stop_event = threading.Event()
        scheduler_thread: threading.Thread | None = None
        refresh_hot_events_snapshot = getattr(app.state.content_orchestrator, "refresh_hot_events_snapshot", None)
        if callable(refresh_hot_events_snapshot):
            _run_hot_events_refresh_once(app, trigger="startup")
            scheduler_thread = threading.Thread(
                target=_hot_events_refresh_scheduler_loop,
                args=(app, stop_event),
                daemon=True,
                name="hot-events-refresh-scheduler",
            )
            scheduler_thread.start()
        log_event(
            logger,
            logging.INFO,
            "app_startup_completed",
            provider=settings.llm_provider,
            model=settings.gemini_model if settings.llm_provider == "gemini" else settings.openai_model,
            twitter_data_proxy_enabled=bool(settings.twitter_data_proxies),
            llm_proxy_enabled=bool(settings.llm_proxies),
            log_level=settings.log_level,
            log_file_enabled=settings.log_enable_file,
            log_file_path=settings.log_file_path if settings.log_enable_file else None,
            hot_events_refresh_interval_seconds=settings.hot_events_refresh_interval_seconds,
            hot_events_scheduler_enabled=callable(refresh_hot_events_snapshot),
        )
        yield
        stop_event.set()
        if scheduler_thread is not None:
            scheduler_thread.join(timeout=1.0)

    app = FastAPI(title="Staked Media MVP", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings
    app.state.database = database
    app.state.upstream = upstream_client or UpstreamClient(settings)
    app.state.llm = llm_client or create_llm_client(settings)
    app.state.content_orchestrator = content_orchestrator or ContentOrchestrator(
        settings=settings,
        database=database,
        llm=app.state.llm,
    )

    @app.get("/healthz")
    def healthcheck() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/api/v1/profiles/ingest", response_model=IngestResponse)
    def ingest_profile(payload: ProfileIngestRequest, request: Request) -> IngestResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        settings = request.app.state.settings
        database: Database = request.app.state.database
        upstream: UpstreamClient = request.app.state.upstream
        llm: LLMClient = request.app.state.llm
        username = _require_allowed_username(database, payload.username, request_id=request_id, route="profiles_ingest")
        ingested_at = utc_now_iso()
        log_event(
            logger,
            logging.INFO,
            "api_ingest_started",
            request_id=request_id,
            username=username,
            max_tweets=settings.max_ingest_tweets,
        )

        try:
            user = upstream.fetch_user_by_username(username, request_id=request_id)
            tweet_items = upstream.fetch_user_tweets(
                user["id"],
                max_tweets=settings.max_ingest_tweets,
                request_id=request_id,
            )
        except UpstreamError as exc:
            log_event(
                logger,
                logging.ERROR,
                "api_ingest_upstream_failed",
                request_id=request_id,
                username=username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        database.upsert_user(user, ingested_at)
        fetched_tweet_count = database.upsert_tweets(user["id"], tweet_items, ingested_at)
        tweet_rows = database.get_user_tweets(user["id"], limit=settings.max_ingest_tweets)
        corpus_stats = build_corpus_stats(user, tweet_rows, sample_size=settings.persona_sample_size)

        try:
            persona = llm.generate_persona(
                profile=user,
                corpus_stats=corpus_stats,
                request_id=request_id,
            )
        except LLMError as exc:
            log_event(
                logger,
                logging.ERROR,
                "api_ingest_llm_failed",
                request_id=request_id,
                username=username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception:
            logger.exception(
                format_log_event(
                    "api_ingest_unhandled_error",
                    request_id=request_id,
                    username=username,
                )
            )
            raise

        representative_tweets = corpus_stats["representative_tweets"]
        persona_snapshot_id = database.save_persona_snapshot(
            user_id=user["id"],
            username=user["username"],
            source_tweet_count=corpus_stats["tweet_counts"]["total"],
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            source_window_start=corpus_stats["source_window"]["start"],
            source_window_end=corpus_stats["source_window"]["end"],
            corpus_stats=corpus_stats,
            representative_tweets=representative_tweets,
            persona=persona,
            created_at=ingested_at,
        )

        stored_user = database.get_user_by_username(user["username"])
        if stored_user is None:
            log_event(
                logger,
                logging.ERROR,
                "api_ingest_reload_failed",
                request_id=request_id,
                username=username,
            )
            raise HTTPException(status_code=500, detail="Stored user could not be reloaded")

        log_event(
            logger,
            logging.INFO,
            "api_ingest_completed",
            request_id=request_id,
            username=username,
            fetched_tweet_count=fetched_tweet_count,
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            persona_snapshot_id=persona_snapshot_id,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return IngestResponse(
            username=user["username"],
            user_id=user["id"],
            fetched_tweet_count=fetched_tweet_count,
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            persona_snapshot_id=persona_snapshot_id,
            ingested_at=ingested_at,
            profile=_profile_summary_from_row(stored_user),
            persona=persona,
        )

    @app.get("/api/v1/profiles/{username}", response_model=ProfileResponse)
    def get_profile(username: str, request: Request) -> ProfileResponse:
        database: Database = request.app.state.database
        normalized_username = _require_allowed_username(database, username, route="profiles_get")
        stored_user = database.get_user_by_username(normalized_username)
        if stored_user is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        tweets = database.get_user_tweets(stored_user["id"])
        latest_persona = database.get_latest_persona_snapshot(normalized_username)
        return ProfileResponse(
            profile=_profile_summary_from_row(stored_user),
            stored_tweet_count=len(tweets),
            latest_persona_snapshot=latest_persona,
        )

    @app.post("/api/v1/profiles/rebuild-persona", response_model=ProfileRebuildPersonaResponse)
    def rebuild_persona(payload: ProfileRebuildPersonaRequest, request: Request) -> ProfileRebuildPersonaResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        settings = request.app.state.settings
        database: Database = request.app.state.database
        llm: LLMClient = request.app.state.llm
        username = _require_allowed_username(
            database,
            payload.username,
            request_id=request_id,
            route="profiles_rebuild_persona",
        )
        rebuilt_at = utc_now_iso()
        stored_user = database.get_user_by_username(username)
        if stored_user is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        tweet_rows = database.get_user_tweets(stored_user["id"], limit=settings.max_ingest_tweets)
        if not tweet_rows:
            raise HTTPException(status_code=409, detail="No tweets found. Run /api/v1/profiles/ingest first")

        profile_payload = _profile_payload_from_stored_user(stored_user)
        corpus_stats = build_corpus_stats(profile_payload, tweet_rows, sample_size=settings.persona_sample_size)
        try:
            persona = llm.generate_persona(
                profile=profile_payload,
                corpus_stats=corpus_stats,
                request_id=request_id,
            )
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        persona_snapshot_id = database.save_persona_snapshot(
            user_id=str(stored_user["id"]),
            username=str(stored_user["username"]),
            source_tweet_count=corpus_stats["tweet_counts"]["total"],
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            source_window_start=corpus_stats["source_window"]["start"],
            source_window_end=corpus_stats["source_window"]["end"],
            corpus_stats=corpus_stats,
            representative_tweets=corpus_stats["representative_tweets"],
            persona=persona,
            created_at=rebuilt_at,
        )
        log_event(
            logger,
            logging.INFO,
            "api_rebuild_persona_completed",
            request_id=request_id,
            username=username,
            source_tweet_count=corpus_stats["tweet_counts"]["total"],
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            persona_snapshot_id=persona_snapshot_id,
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return ProfileRebuildPersonaResponse(
            username=str(stored_user["username"]),
            user_id=str(stored_user["id"]),
            source_tweet_count=corpus_stats["tweet_counts"]["total"],
            source_original_tweet_count=corpus_stats["tweet_counts"]["original"],
            persona_snapshot_id=persona_snapshot_id,
            rebuilt_at=rebuilt_at,
            persona=persona,
        )

    @app.post("/api/v1/drafts/generate", response_model=DraftGenerateResponse)
    def generate_drafts(payload: DraftGenerateRequest, request: Request) -> DraftGenerateResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        database: Database = request.app.state.database
        llm: LLMClient = request.app.state.llm
        username = _require_allowed_username(database, payload.username, request_id=request_id, route="drafts_generate")
        created_at = utc_now_iso()
        log_event(
            logger,
            logging.INFO,
            "api_draft_generate_started",
            request_id=request_id,
            username=username,
            draft_count=payload.draft_count,
            prompt_len=len(payload.prompt),
            prompt_snippet=redact_for_log(payload.prompt, request.app.state.settings.log_max_body_chars),
        )

        stored_user = database.get_user_by_username(username)
        if stored_user is None:
            log_event(
                logger,
                logging.WARNING,
                "api_draft_generate_profile_missing",
                request_id=request_id,
                username=username,
            )
            raise HTTPException(status_code=404, detail="Profile not found")

        snapshot = database.get_latest_persona_snapshot(username)
        if snapshot is None:
            log_event(
                logger,
                logging.WARNING,
                "api_draft_generate_persona_missing",
                request_id=request_id,
                username=username,
            )
            raise HTTPException(status_code=409, detail="Persona not found. Run /api/v1/profiles/ingest first")

        tweet_rows = database.get_user_tweets(stored_user["id"], limit=request.app.state.settings.max_ingest_tweets)
        source_texts = [row["text"] for row in tweet_rows if row["text"]]
        log_event(
            logger,
            logging.INFO,
            "api_draft_generate_context_ready",
            request_id=request_id,
            username=username,
            persona_snapshot_id=snapshot["id"],
            tweet_count=len(tweet_rows),
            source_text_count=len(source_texts),
        )

        try:
            draft_result = llm.generate_drafts(
                persona=snapshot["persona"],
                prompt=payload.prompt,
                representative_tweets=snapshot["representative_tweets"],
                source_texts=source_texts,
                tweet_rows=tweet_rows,
                draft_count=payload.draft_count,
                request_id=request_id,
            )
        except LLMError as exc:
            log_event(
                logger,
                logging.ERROR,
                "api_draft_generate_llm_failed",
                request_id=request_id,
                username=username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception:
            logger.exception(
                format_log_event(
                    "api_draft_generate_unhandled_error",
                    request_id=request_id,
                    username=username,
                )
            )
            raise

        database.save_draft_request(
            username=username,
            persona_snapshot_id=snapshot["id"],
            prompt=payload.prompt,
            draft_count=payload.draft_count,
            output=draft_result,
            created_at=created_at,
        )
        log_event(
            logger,
            logging.INFO,
            "api_draft_generate_completed",
            request_id=request_id,
            username=username,
            persona_snapshot_id=snapshot["id"],
            best_score=float(draft_result.get("best_score", 0.0)),
            target_score_met=bool(draft_result.get("target_score_met", False)),
            attempt_count=int(draft_result.get("attempt_count", 0)),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

        return DraftGenerateResponse(
            username=username,
            prompt=payload.prompt,
            persona_snapshot_id=snapshot["id"],
            drafts=draft_result["drafts"],
            theme_keywords=draft_result.get("theme_keywords", []),
            theme_top_keywords=draft_result.get("theme_top_keywords", []),
            matched_theme_tweets=draft_result.get("matched_theme_tweets", []),
            best_score=float(draft_result.get("best_score", 0.0)),
            target_score=float(draft_result.get("target_score", 0.0)),
            target_score_met=bool(draft_result.get("target_score_met", False)),
            attempt_count=int(draft_result.get("attempt_count", 0)),
            attempts=draft_result.get("attempts", []),
            evaluation=draft_result.get("evaluation", {}),
            created_at=created_at,
        )

    @app.post("/api/v1/content/ideas", response_model=ContentIdeasResponse)
    def content_ideas(payload: ContentIdeasRequest, request: Request) -> ContentIdeasResponse:
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        result = orchestrator.suggest_ideas(
            direction=payload.direction,
            domain=payload.domain,
            topic_hint=payload.topic_hint,
            limit=payload.limit,
        )
        return ContentIdeasResponse(**result)

    @app.get("/api/v1/content/hot-events", response_model=HotEventsResponse)
    def content_hot_events(
        request: Request,
        hours: int = Query(24, ge=1, le=72),
        limit: int = Query(50, ge=1, le=200),
        refresh: bool = Query(False),
    ) -> HotEventsResponse:
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        try:
            result = orchestrator.list_hot_events(hours=hours, limit=limit, refresh=refresh)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return HotEventsResponse(**result)

    @app.post("/api/v1/content/generate", response_model=ContentGenerateResponse)
    def content_generate(payload: ContentGenerateRequest, request: Request) -> ContentGenerateResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        database: Database = request.app.state.database
        username = _require_allowed_username(
            database, payload.username, request_id=request_id, route="content_generate"
        )
        payload = payload.copy(update={"username": username})
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        try:
            result = orchestrator.generate_content(payload, request_id=request_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError as exc:
            message = str(exc)
            status_code = 404 if "Profile not found" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        latest_persona_snapshot = database.get_latest_persona_snapshot(username)
        if latest_persona_snapshot is None:
            raise HTTPException(status_code=409, detail="Persona not found. Run /api/v1/profiles/ingest first")
        database.save_draft_request(
            username=username,
            persona_snapshot_id=latest_persona_snapshot["id"],
            prompt=payload.idea or payload.topic or "content_generate",
            draft_count=payload.draft_count,
            output=result,
            created_at=utc_now_iso(),
        )
        log_event(
            logger,
            logging.INFO,
            "api_content_generate_completed",
            request_id=request_id,
            username=username,
            mode=payload.mode,
            topic=result.get("topic", ""),
            final_score=result.get("score", {}).get("final_score", 0.0),
            target_score_met=result.get("target_score_met", False),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return ContentGenerateResponse(**result)

    @app.post("/api/v1/conversation/generate", response_model=ContentGenerateResponse)
    def conversation_generate(payload: ConversationGenerateRequest, request: Request) -> ContentGenerateResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        database: Database = request.app.state.database
        username = _require_allowed_username(
            database, payload.username, request_id=request_id, route="conversation_generate"
        )
        payload = payload.copy(update={"username": username})
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        try:
            result = orchestrator.generate_conversation_content(payload, request_id=request_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except LookupError as exc:
            message = str(exc)
            status_code = 404 if "Profile not found" in message else 409
            raise HTTPException(status_code=status_code, detail=message) from exc
        except LLMError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        latest_persona_snapshot = database.get_latest_persona_snapshot(username)
        if latest_persona_snapshot is None:
            raise HTTPException(status_code=409, detail="Persona not found. Run /api/v1/profiles/ingest first")
        database.save_draft_request(
            username=username,
            persona_snapshot_id=latest_persona_snapshot["id"],
            prompt=payload.comment.strip() or result.get("topic", "") or "conversation_generate",
            draft_count=payload.draft_count,
            output=result,
            created_at=utc_now_iso(),
        )
        log_event(
            logger,
            logging.INFO,
            "api_conversation_generate_completed",
            request_id=request_id,
            username=username,
            topic=result.get("topic", ""),
            final_score=result.get("score", {}).get("final_score", 0.0),
            target_score_met=result.get("target_score_met", False),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return ContentGenerateResponse(**result)

    @app.post("/api/v1/exposure/analyze", response_model=ExposureAnalyzeResponse)
    def exposure_analyze(payload: ExposureAnalyzeRequest, request: Request) -> ExposureAnalyzeResponse:
        database: Database = request.app.state.database
        username = _require_allowed_username(database, payload.username, route="exposure_analyze")
        payload = payload.copy(update={"username": username})
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        result = orchestrator.analyze_exposure(
            username=payload.username,
            text=payload.text,
            topic=payload.topic,
            domain=payload.domain,
        )
        return ExposureAnalyzeResponse(**result)

    @app.get("/admin/api/v1/whitelist/usernames", response_model=WhitelistUsernamesResponse)
    def whitelist_list(request: Request) -> WhitelistUsernamesResponse:
        database: Database = request.app.state.database
        return WhitelistUsernamesResponse(usernames=database.list_allowed_usernames())

    @app.post("/admin/api/v1/whitelist/usernames", response_model=WhitelistUsernamesResponse)
    def whitelist_add(payload: WhitelistUsernameRequest, request: Request) -> WhitelistUsernamesResponse:
        database: Database = request.app.state.database
        username = database.add_allowed_username(payload.username)
        log_event(
            logger,
            logging.INFO,
            "admin_whitelist_username_added",
            username=username,
        )
        return WhitelistUsernamesResponse(usernames=database.list_allowed_usernames())

    @app.delete("/admin/api/v1/whitelist/usernames/{username}", response_model=WhitelistUsernamesResponse)
    def whitelist_remove(username: str, request: Request) -> WhitelistUsernamesResponse:
        database: Database = request.app.state.database
        normalized_username = database.remove_allowed_username(username)
        log_event(
            logger,
            logging.INFO,
            "admin_whitelist_username_removed",
            username=normalized_username,
        )
        return WhitelistUsernamesResponse(usernames=database.list_allowed_usernames())

    @app.get("/api/v1/content/debug/{request_id}", response_model=ContentDebugResponse)
    def content_debug(request_id: str, request: Request) -> ContentDebugResponse:
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        debug_payload = orchestrator.get_debug(request_id)
        if debug_payload is None:
            raise HTTPException(status_code=404, detail="Debug record not found")
        return ContentDebugResponse(**debug_payload)

    return app


def create_app_from_runtime_config() -> FastAPI:
    return create_app(settings=get_settings())


def _require_allowed_username(
    database: Database,
    username: str,
    *,
    request_id: str | None = None,
    route: str,
) -> str:
    normalized = normalize_username(username)
    if database.is_username_allowed(normalized):
        return normalized

    log_event(
        logger,
        logging.WARNING,
        "api_username_not_whitelisted",
        request_id=request_id,
        route=route,
        username=normalized,
    )
    raise HTTPException(status_code=403, detail=WHITELIST_FORBIDDEN_DETAIL)


def _profile_summary_from_row(row: dict[str, Any]) -> ProfileSummary:
    return ProfileSummary(
        id=str(row["id"]),
        username=str(row["username"]),
        name=str(row["name"]),
        description=str(row.get("description") or ""),
        location=str(row.get("location") or ""),
        profile_url=str(row.get("profile_url") or ""),
        followers_count=int(row.get("followers_count") or 0),
        following_count=int(row.get("following_count") or 0),
        tweet_count=int(row.get("tweet_count") or 0),
        verified=bool(row.get("verified")),
        last_ingested_at=str(row.get("last_ingested_at") or ""),
    )


def _profile_payload_from_stored_user(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = row.get("raw_json")
    payload = dict(raw_payload) if isinstance(raw_payload, dict) else {}
    payload["id"] = str(payload.get("id") or row.get("id") or "")
    payload["username"] = str(payload.get("username") or row.get("username") or "")
    payload["name"] = str(payload.get("name") or row.get("name") or payload["username"])
    payload["description"] = str(payload.get("description") or row.get("description") or "")
    payload["location"] = str(payload.get("location") or row.get("location") or "")
    payload["url"] = str(payload.get("url") or row.get("profile_url") or "")
    payload["verified"] = bool(payload.get("verified") or row.get("verified"))
    public_metrics = payload.get("public_metrics")
    if not isinstance(public_metrics, dict):
        public_metrics = {}
    public_metrics["followers_count"] = int(public_metrics.get("followers_count") or row.get("followers_count") or 0)
    public_metrics["following_count"] = int(public_metrics.get("following_count") or row.get("following_count") or 0)
    public_metrics["tweet_count"] = int(public_metrics.get("tweet_count") or row.get("tweet_count") or 0)
    payload["public_metrics"] = public_metrics
    return payload
