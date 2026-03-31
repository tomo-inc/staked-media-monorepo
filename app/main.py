from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, Request

from app.config import Settings, get_settings
from app.database import Database
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
    DraftGenerateRequest,
    DraftGenerateResponse,
    ExposureAnalyzeRequest,
    ExposureAnalyzeResponse,
    IngestResponse,
    MAX_INGEST_TWEETS,
    ProfileIngestRequest,
    ProfileResponse,
    ProfileSummary,
)
from app.upstream import UpstreamClient, UpstreamError


logger = get_logger(__name__)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def create_app(
    settings: Optional[Settings] = None,
    *,
    upstream_client: Optional[UpstreamClient] = None,
    llm_client: Optional[LLMClient] = None,
    content_orchestrator: Optional[ContentOrchestrator] = None,
) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings)
    database = Database(settings.database_path)
    database.init()
    app = FastAPI(title="Staked Media MVP", version="0.1.0")
    app.state.settings = settings
    app.state.database = database
    app.state.upstream = upstream_client or UpstreamClient(settings)
    app.state.llm = llm_client or create_llm_client(settings)
    app.state.content_orchestrator = content_orchestrator or ContentOrchestrator(
        settings=settings,
        database=database,
        llm=app.state.llm,
    )

    @app.on_event("startup")
    def on_startup() -> None:
        app.state.database.init()
        log_event(
            logger,
            logging.INFO,
            "app_startup_completed",
            provider=settings.llm_provider,
            model=settings.gemini_model if settings.llm_provider == "gemini" else settings.openai_model,
            proxy_enabled=bool(settings.upstream_proxies),
            log_level=settings.log_level,
            log_file_enabled=settings.log_enable_file,
            log_file_path=settings.log_file_path if settings.log_enable_file else None,
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
        ingested_at = utc_now_iso()
        log_event(
            logger,
            logging.INFO,
            "api_ingest_started",
            request_id=request_id,
            username=payload.username,
            max_tweets=payload.max_tweets,
        )

        try:
            user = upstream.fetch_user_by_username(payload.username, request_id=request_id)
            tweet_items = upstream.fetch_user_tweets(user["id"], max_tweets=payload.max_tweets, request_id=request_id)
        except UpstreamError as exc:
            log_event(
                logger,
                logging.ERROR,
                "api_ingest_upstream_failed",
                request_id=request_id,
                username=payload.username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        database.upsert_user(user, ingested_at)
        fetched_tweet_count = database.upsert_tweets(user["id"], tweet_items, ingested_at)
        tweet_rows = database.get_user_tweets(user["id"], limit=payload.max_tweets)
        corpus_stats = build_corpus_stats(user, tweet_rows, sample_size=settings.persona_sample_size)
        representative_tweets = corpus_stats["representative_tweets"]

        try:
            persona = llm.generate_persona(
                profile=user,
                corpus_stats=corpus_stats,
                representative_tweets=representative_tweets,
                request_id=request_id,
            )
        except LLMError as exc:
            log_event(
                logger,
                logging.ERROR,
                "api_ingest_llm_failed",
                request_id=request_id,
                username=payload.username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception:
            logger.exception(
                format_log_event(
                    "api_ingest_unhandled_error",
                    request_id=request_id,
                    username=payload.username,
                )
            )
            raise

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
                username=payload.username,
            )
            raise HTTPException(status_code=500, detail="Stored user could not be reloaded")

        log_event(
            logger,
            logging.INFO,
            "api_ingest_completed",
            request_id=request_id,
            username=payload.username,
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
        stored_user = database.get_user_by_username(username)
        if stored_user is None:
            raise HTTPException(status_code=404, detail="Profile not found")

        tweets = database.get_user_tweets(stored_user["id"])
        latest_persona = database.get_latest_persona_snapshot(username)
        return ProfileResponse(
            profile=_profile_summary_from_row(stored_user),
            stored_tweet_count=len(tweets),
            latest_persona_snapshot=latest_persona,
        )

    @app.post("/api/v1/drafts/generate", response_model=DraftGenerateResponse)
    def generate_drafts(payload: DraftGenerateRequest, request: Request) -> DraftGenerateResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
        database: Database = request.app.state.database
        llm: LLMClient = request.app.state.llm
        created_at = utc_now_iso()
        log_event(
            logger,
            logging.INFO,
            "api_draft_generate_started",
            request_id=request_id,
            username=payload.username,
            draft_count=payload.draft_count,
            prompt_len=len(payload.prompt),
            prompt_snippet=redact_for_log(payload.prompt, request.app.state.settings.log_max_body_chars),
        )

        stored_user = database.get_user_by_username(payload.username)
        if stored_user is None:
            log_event(
                logger,
                logging.WARNING,
                "api_draft_generate_profile_missing",
                request_id=request_id,
                username=payload.username,
            )
            raise HTTPException(status_code=404, detail="Profile not found")

        snapshot = database.get_latest_persona_snapshot(payload.username)
        if snapshot is None:
            log_event(
                logger,
                logging.WARNING,
                "api_draft_generate_persona_missing",
                request_id=request_id,
                username=payload.username,
            )
            raise HTTPException(status_code=409, detail="Persona not found. Run /api/v1/profiles/ingest first")

        tweet_rows = database.get_user_tweets(stored_user["id"], limit=MAX_INGEST_TWEETS)
        source_texts = [row["text"] for row in tweet_rows if row["text"]]
        log_event(
            logger,
            logging.INFO,
            "api_draft_generate_context_ready",
            request_id=request_id,
            username=payload.username,
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
                username=payload.username,
                error=str(exc),
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except Exception:
            logger.exception(
                format_log_event(
                    "api_draft_generate_unhandled_error",
                    request_id=request_id,
                    username=payload.username,
                )
            )
            raise

        database.save_draft_request(
            username=payload.username,
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
            username=payload.username,
            persona_snapshot_id=snapshot["id"],
            best_score=float(draft_result.get("best_score", 0.0)),
            target_score_met=bool(draft_result.get("target_score_met", False)),
            attempt_count=int(draft_result.get("attempt_count", 0)),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )

        return DraftGenerateResponse(
            username=payload.username,
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

    @app.post("/api/v1/content/generate", response_model=ContentGenerateResponse)
    def content_generate(payload: ContentGenerateRequest, request: Request) -> ContentGenerateResponse:
        request_id = uuid.uuid4().hex[:12]
        started_at = time.perf_counter()
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

        database: Database = request.app.state.database
        latest_persona_snapshot = database.get_latest_persona_snapshot(payload.username)
        if latest_persona_snapshot is None:
            raise HTTPException(status_code=409, detail="Persona not found. Run /api/v1/profiles/ingest first")
        database.save_draft_request(
            username=payload.username,
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
            username=payload.username,
            mode=payload.mode,
            topic=result.get("topic", ""),
            final_score=result.get("score", {}).get("final_score", 0.0),
            target_score_met=result.get("target_score_met", False),
            duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
        )
        return ContentGenerateResponse(**result)

    @app.post("/api/v1/exposure/analyze", response_model=ExposureAnalyzeResponse)
    def exposure_analyze(payload: ExposureAnalyzeRequest, request: Request) -> ExposureAnalyzeResponse:
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        result = orchestrator.analyze_exposure(
            username=payload.username,
            text=payload.text,
            topic=payload.topic,
            domain=payload.domain,
        )
        return ExposureAnalyzeResponse(**result)

    @app.get("/api/v1/content/debug/{request_id}", response_model=ContentDebugResponse)
    def content_debug(request_id: str, request: Request) -> ContentDebugResponse:
        orchestrator: ContentOrchestrator = request.app.state.content_orchestrator
        debug_payload = orchestrator.get_debug(request_id)
        if debug_payload is None:
            raise HTTPException(status_code=404, detail="Debug record not found")
        return ContentDebugResponse(**debug_payload)

    return app


def _profile_summary_from_row(row: dict[str, object]) -> ProfileSummary:
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


app = create_app()
