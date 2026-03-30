from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

import requests
from pydantic import ValidationError

from app.config import Settings
from app.logging_utils import get_logger, log_event, redact_for_log
from app.persona import (
    SUMMARY_DRIFT_PHRASES,
    clean_text,
    extract_english_words,
    extract_theme_keywords,
    extract_top_theme_keywords,
    is_too_similar,
    keyword_in_text,
    phrase_frequency,
    prompt_requests_full_chinese,
    select_theme_tweets,
)
from app.schemas import DraftCandidateEvaluation, DraftItem, DraftsOutput, PersonaOutput


GENERATION_GUARDRAIL_KEYS = (
    "preferred_openings",
    "preferred_formats",
    "compression_rules",
    "anti_patterns",
    "language_notes",
)
TARGET_DRAFT_SCORE = 9.0
MAX_GENERATION_ATTEMPTS = 5
MIN_RULE_SCORE_FOR_LLM_REVIEW = 7.0


logger = get_logger(__name__)


class LLMError(RuntimeError):
    """Raised when the configured LLM integration fails."""


class LLMTransportError(LLMError):
    """Raised when the LLM transport fails after transient retry handling."""

    def __init__(self, message: str, *, category: str):
        super().__init__(message)
        self.category = category


OpenAIError = LLMError


class LLMClient:
    def __init__(self, settings: Settings, *, provider_name: str):
        self.settings = settings
        self.provider_name = provider_name

    def _resolve_timeout_seconds(self, *, purpose: str, timeout_seconds: float | None) -> float:
        if timeout_seconds is not None:
            return timeout_seconds
        if purpose == "score":
            return float(self.settings.llm_score_timeout_seconds)
        return float(self.settings.request_timeout_seconds)

    def _post_json_with_retries(
        self,
        *,
        endpoint: str,
        headers: dict[str, str],
        json_payload: dict[str, Any],
        model: str,
        request_id: str | None,
        purpose: str,
        timeout_seconds: float | None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_timeout = self._resolve_timeout_seconds(
            purpose=purpose,
            timeout_seconds=timeout_seconds,
        )
        max_attempts = max(1, self.settings.llm_max_retries + 1)

        for attempt in range(1, max_attempts + 1):
            started_at = time.perf_counter()
            log_event(
                logger,
                logging.INFO,
                "llm_provider_request_started",
                request_id=request_id,
                provider=self.provider_name,
                model=model,
                endpoint=endpoint,
                temperature=json_payload.get("temperature")
                or (json_payload.get("generationConfig") or {}).get("temperature"),
                system_prompt_len=len(str((json_payload.get("messages") or [{"content": ""}])[0].get("content", "")))
                if "messages" in json_payload
                else len(str((((json_payload.get("system_instruction") or {}).get("parts") or [{"text": ""}])[0]).get("text", ""))),
                user_prompt_len=len(str((json_payload.get("messages") or [{}, {"content": ""}])[-1].get("content", "")))
                if "messages" in json_payload
                else len(str(((((json_payload.get("contents") or [{}])[0]).get("parts") or [{"text": ""}])[0]).get("text", ""))),
                proxy_enabled=bool(self.settings.upstream_proxies),
                attempt=attempt,
                max_attempts=max_attempts,
                purpose=purpose,
                timeout_seconds=resolved_timeout,
            )
            try:
                response = requests.post(
                    endpoint,
                    params=params,
                    headers=headers,
                    json=json_payload,
                    proxies=self.settings.upstream_proxies,
                    timeout=resolved_timeout,
                )
                response.raise_for_status()
            except requests.HTTPError as exc:
                status_code = exc.response.status_code if exc.response is not None else None
                detail = (exc.response.text if exc.response is not None else "")[:1000]
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                if status_code is not None and status_code >= 500 and attempt < max_attempts:
                    backoff_seconds = round(self.settings.llm_retry_backoff_seconds * (2 ** (attempt - 1)), 3)
                    log_event(
                        logger,
                        logging.WARNING,
                        "llm_provider_request_retrying",
                        request_id=request_id,
                        provider=self.provider_name,
                        model=model,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        purpose=purpose,
                        status_code=status_code,
                        duration_ms=duration_ms,
                        backoff_seconds=backoff_seconds,
                        retry_reason="http_5xx",
                    )
                    time.sleep(backoff_seconds)
                    continue
                log_event(
                    logger,
                    logging.ERROR,
                    "llm_provider_request_failed",
                    request_id=request_id,
                    provider=self.provider_name,
                    model=model,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    purpose=purpose,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    response_snippet=redact_for_log(detail, self.settings.log_max_body_chars),
                )
                provider_label = "OpenAI" if self.provider_name == "openai" else "Gemini"
                raise LLMTransportError(
                    f"{provider_label} request failed: {detail}",
                    category="http_error",
                ) from exc
            except (requests.Timeout, requests.ConnectionError) as exc:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                retry_reason = type(exc).__name__
                if attempt < max_attempts:
                    backoff_seconds = round(self.settings.llm_retry_backoff_seconds * (2 ** (attempt - 1)), 3)
                    log_event(
                        logger,
                        logging.WARNING,
                        "llm_provider_request_retrying",
                        request_id=request_id,
                        provider=self.provider_name,
                        model=model,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        purpose=purpose,
                        duration_ms=duration_ms,
                        backoff_seconds=backoff_seconds,
                        retry_reason=retry_reason,
                    )
                    time.sleep(backoff_seconds)
                    continue
                provider_label = "OpenAI" if self.provider_name == "openai" else "Gemini"
                log_event(
                    logger,
                    logging.ERROR,
                    "llm_provider_request_failed",
                    request_id=request_id,
                    provider=self.provider_name,
                    model=model,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    purpose=purpose,
                    duration_ms=duration_ms,
                    error_type=retry_reason,
                    error=str(exc),
                )
                raise LLMTransportError(
                    f"{provider_label} request failed: {retry_reason}: {exc}",
                    category="transport_error",
                ) from exc
            except requests.RequestException as exc:
                duration_ms = round((time.perf_counter() - started_at) * 1000, 2)
                provider_label = "OpenAI" if self.provider_name == "openai" else "Gemini"
                log_event(
                    logger,
                    logging.ERROR,
                    "llm_provider_request_failed",
                    request_id=request_id,
                    provider=self.provider_name,
                    model=model,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    purpose=purpose,
                    duration_ms=duration_ms,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                raise LLMTransportError(
                    f"{provider_label} request failed: {type(exc).__name__}: {exc}",
                    category="request_error",
                ) from exc

            body = response.json()
            log_event(
                logger,
                logging.INFO,
                "llm_provider_response_received",
                request_id=request_id,
                provider=self.provider_name,
                model=model,
                status_code=response.status_code,
                duration_ms=round((time.perf_counter() - started_at) * 1000, 2),
                body_keys=sorted(body.keys()) if isinstance(body, dict) else None,
                body_type=type(body).__name__,
                attempt=attempt,
                max_attempts=max_attempts,
                purpose=purpose,
            )
            return body

        raise LLMTransportError("LLM request failed after retries", category="retry_exhausted")

    def generate_persona(
        self,
        *,
        profile: dict[str, Any],
        corpus_stats: dict[str, Any],
        representative_tweets: list[dict[str, Any]],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        log_event(
            logger,
            logging.INFO,
            "persona_generation_started",
            request_id=request_id,
            provider=self.provider_name,
            username=profile.get("username"),
            representative_tweet_count=len(representative_tweets),
        )
        request_payload = self._build_persona_request_payload(
            profile=profile,
            corpus_stats=corpus_stats,
            representative_tweets=representative_tweets,
        )
        payload = self._chat_completion_json(
            system_prompt=(
                "You analyze a public X user's profile and tweets to build a reusable writing persona. "
                "Infer tone and style only from provided evidence. Do not fabricate facts. "
                "Return strict JSON with keys: persona_version, author_summary, voice_traits, "
                "topic_clusters, writing_patterns, lexical_markers, do_not_sound_like, cta_style, "
                "generation_guardrails, risk_notes."
            ),
            user_prompt=json.dumps(request_payload, ensure_ascii=True),
            temperature=0.4,
            request_id=request_id,
            purpose="persona",
        )
        normalized_payload = self._normalize_persona_payload(payload)
        try:
            persona = PersonaOutput.parse_obj(normalized_payload).dict()
        except ValidationError as exc:
            log_event(
                logger,
                logging.ERROR,
                "persona_generation_schema_failed",
                request_id=request_id,
                provider=self.provider_name,
                error=str(exc),
            )
            raise LLMError(f"Persona schema validation failed: {exc}") from exc
        log_event(
            logger,
            logging.INFO,
            "persona_generation_completed",
            request_id=request_id,
            provider=self.provider_name,
            username=profile.get("username"),
            voice_trait_count=len(persona.get("voice_traits", [])),
            topic_cluster_count=len(persona.get("topic_clusters", [])),
        )
        return persona

    def generate_drafts(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        representative_tweets: list[dict[str, Any]],
        source_texts: list[str],
        tweet_rows: list[dict[str, Any]],
        draft_count: int,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        log_event(
            logger,
            logging.INFO,
            "draft_generation_started",
            request_id=request_id,
            provider=self.provider_name,
            draft_count=draft_count,
            prompt_len=len(prompt),
            prompt_snippet=redact_for_log(prompt, self.settings.log_max_body_chars),
            source_text_count=len(source_texts),
            tweet_row_count=len(tweet_rows),
        )
        theme_keywords = extract_theme_keywords(prompt)
        matched_theme_tweets = select_theme_tweets(tweet_rows, theme_keywords)
        if not matched_theme_tweets:
            matched_theme_tweets = [
                {
                    "id": item.get("id", ""),
                    "text": clean_text(item.get("text", "")),
                    "created_at": item.get("created_at", ""),
                    "match_terms": [],
                    "engagement_score": int(item.get("engagement_score", 0)),
                }
                for item in representative_tweets[:12]
                if clean_text(item.get("text", ""))
            ]
        theme_top_keywords = extract_top_theme_keywords(
            matched_theme_tweets,
            theme_keywords,
            prompt=prompt,
        )
        log_event(
            logger,
            logging.INFO,
            "draft_generation_context_ready",
            request_id=request_id,
            provider=self.provider_name,
            theme_keywords=theme_keywords,
            matched_theme_tweet_count=len(matched_theme_tweets),
            theme_top_keywords=theme_top_keywords,
        )

        accepted: list[dict[str, Any]] = []
        all_candidates: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        rejected_texts: list[str] = []
        attempt_feedback: list[str] = []
        attempts: list[dict[str, Any]] = []

        for attempt in range(MAX_GENERATION_ATTEMPTS):
            needed = draft_count - len(accepted)
            if needed <= 0:
                break
            log_event(
                logger,
                logging.INFO,
                "draft_generation_attempt_started",
                request_id=request_id,
                provider=self.provider_name,
                attempt=attempt + 1,
                needed_count=needed,
                accepted_count=len(accepted),
                rejected_count=len(rejected_texts),
            )

            request_payload = self._build_draft_request_payload(
                persona=persona,
                prompt=prompt,
                representative_tweets=representative_tweets,
                matched_theme_tweets=matched_theme_tweets,
                theme_keywords=theme_keywords,
                theme_top_keywords=theme_top_keywords,
                rejected_texts=rejected_texts,
                attempt_feedback=attempt_feedback,
                draft_count=needed + 2,
            )
            payload = self._chat_completion_json(
                system_prompt=(
                    "You write original X posts that sound like the provided persona. "
                    "The goal is inspired-by writing, not copying. "
                    "Treat the persona's generation_guardrails as hard style guidance. "
                    "Prioritize the theme-matched historical tweets over generic persona habits. "
                    "Prefer concrete, timeline-native phrasing over polished summary language. "
                    "Return strict JSON with a top-level 'drafts' array. "
                    "Each draft object must have keys: text, tone_tags, rationale."
                ),
                user_prompt=json.dumps(request_payload, ensure_ascii=True),
                temperature=0.9,
                request_id=request_id,
                purpose="draft_generation",
            )
            log_event(
                logger,
                logging.INFO,
                "draft_generation_payload_received",
                request_id=request_id,
                provider=self.provider_name,
                attempt=attempt + 1,
                payload_type=type(payload).__name__,
            )

            normalized_payload = self._normalize_drafts_payload(payload)
            try:
                generated = DraftsOutput.parse_obj(normalized_payload).drafts
            except ValidationError as exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "draft_generation_schema_failed",
                    request_id=request_id,
                    provider=self.provider_name,
                    attempt=attempt + 1,
                    error=str(exc),
                    payload_snippet=redact_for_log(normalized_payload, self.settings.log_max_body_chars),
                )
                raise LLMError(f"Draft schema validation failed: {exc}") from exc

            attempt_candidates: list[dict[str, Any]] = []
            for item in generated:
                text = clean_text(item.text)
                if not text or len(text) > 280:
                    if text:
                        rejected_texts.append(text)
                        attempt_candidates.append(
                            self._candidate_result(
                                text=text,
                                tone_tags=item.tone_tags[:4],
                                rationale=clean_text(item.rationale),
                                evaluation={
                                    "rule_score": 0.0,
                                    "llm_score": 0.0,
                                    "final_score": 0.0,
                                    "passed": False,
                                    "rule_issues": ["Rejected before scoring: exceeded max chars"],
                                    "rule_strengths": [],
                                    "llm_verdict": "skipped",
                                    "llm_issues": [],
                                    "llm_strengths": [],
                                    "must_fix": ["Shorten the draft to 280 chars or fewer"],
                                    "failure_reasons": ["Rejected before scoring: exceeded max chars"],
                                },
                            )
                        )
                        log_event(
                            logger,
                            logging.INFO,
                            "draft_candidate_rejected_pre_score",
                            request_id=request_id,
                            provider=self.provider_name,
                            attempt=attempt + 1,
                            reason="exceeded_max_chars",
                            text_snippet=redact_for_log(text, 160),
                        )
                    continue
                normalized = text.lower()
                if normalized in seen_texts:
                    rejected_texts.append(text)
                    attempt_candidates.append(
                        self._candidate_result(
                            text=text,
                            tone_tags=item.tone_tags[:4],
                            rationale=clean_text(item.rationale),
                            evaluation={
                                "rule_score": 0.0,
                                "llm_score": 0.0,
                                "final_score": 0.0,
                                "passed": False,
                                "rule_issues": ["Rejected before scoring: duplicate candidate"],
                                "rule_strengths": [],
                                "llm_verdict": "skipped",
                                "llm_issues": [],
                                "llm_strengths": [],
                                "must_fix": ["Generate a meaningfully different draft"],
                                "failure_reasons": ["Rejected before scoring: duplicate candidate"],
                            },
                        )
                    )
                    log_event(
                        logger,
                        logging.INFO,
                        "draft_candidate_rejected_pre_score",
                        request_id=request_id,
                        provider=self.provider_name,
                        attempt=attempt + 1,
                        reason="duplicate_candidate",
                        text_snippet=redact_for_log(text, 160),
                    )
                    continue
                evaluation = self._evaluate_candidate(
                    persona=persona,
                    prompt=prompt,
                    candidate_text=text,
                    source_texts=source_texts,
                    matched_theme_tweets=matched_theme_tweets,
                    theme_keywords=theme_keywords,
                    theme_top_keywords=theme_top_keywords,
                    request_id=request_id,
                )
                candidate = {
                    "text": text,
                    "tone_tags": item.tone_tags[:4],
                    "rationale": clean_text(item.rationale),
                    "evaluation": evaluation,
                }
                seen_texts.add(normalized)
                all_candidates.append(candidate)
                attempt_candidates.append(self._candidate_result(**candidate))
                log_event(
                    logger,
                    logging.INFO,
                    "draft_candidate_scored",
                    request_id=request_id,
                    provider=self.provider_name,
                    attempt=attempt + 1,
                    final_score=evaluation["final_score"],
                    rule_score=evaluation["rule_score"],
                    llm_score=evaluation["llm_score"],
                    passed=evaluation["final_score"] >= TARGET_DRAFT_SCORE,
                    failure_reasons=evaluation["failure_reasons"][:3],
                    text_snippet=redact_for_log(text, 160),
                )
                if evaluation["final_score"] >= TARGET_DRAFT_SCORE:
                    accepted.append(candidate)
                else:
                    rejected_texts.append(text)
                if len(accepted) >= draft_count:
                    break

            attempt_feedback = self._build_attempt_feedback(attempt_candidates)
            attempts.append(
                {
                    "attempt": attempt + 1,
                    "best_score": max(
                        (float(item.get("final_score", 0.0)) for item in attempt_candidates),
                        default=0.0,
                    ),
                    "target_score_met": any(item["passed"] for item in attempt_candidates),
                    "candidates": attempt_candidates,
                    "issues": attempt_feedback,
                }
            )
            log_event(
                logger,
                logging.INFO,
                "draft_generation_attempt_completed",
                request_id=request_id,
                provider=self.provider_name,
                attempt=attempt + 1,
                best_score=attempts[-1]["best_score"],
                target_score_met=attempts[-1]["target_score_met"],
                candidate_count=len(attempt_candidates),
                feedback=attempt_feedback,
            )
            if len(accepted) >= draft_count:
                break

        ranked_candidates = sorted(
            all_candidates,
            key=lambda item: item["evaluation"]["final_score"],
            reverse=True,
        )
        selected_candidates = ranked_candidates[:draft_count]
        if not selected_candidates:
            log_event(
                logger,
                logging.ERROR,
                "draft_generation_no_candidates",
                request_id=request_id,
                provider=self.provider_name,
            )
            raise LLMError("Could not generate any candidate drafts")

        drafts = [
            DraftItem(
                text=item["text"],
                tone_tags=item["tone_tags"],
                rationale=item["rationale"],
            ).dict()
            for item in selected_candidates
        ]
        best_candidate = selected_candidates[0]
        target_score_met = (
            len(selected_candidates) >= draft_count
            and all(item["evaluation"]["final_score"] >= TARGET_DRAFT_SCORE for item in selected_candidates)
        )
        log_event(
            logger,
            logging.INFO,
            "draft_generation_completed",
            request_id=request_id,
            provider=self.provider_name,
            best_score=best_candidate["evaluation"]["final_score"],
            target_score=TARGET_DRAFT_SCORE,
            target_score_met=target_score_met,
            attempt_count=len(attempts),
            selected_count=len(selected_candidates),
        )

        return {
            "drafts": drafts,
            "theme_keywords": theme_keywords,
            "theme_top_keywords": theme_top_keywords,
            "matched_theme_tweets": [
                {
                    "created_at": item.get("created_at", ""),
                    "text": item.get("text", ""),
                    "match_terms": item.get("match_terms", []),
                }
                for item in matched_theme_tweets[:10]
            ],
            "best_score": best_candidate["evaluation"]["final_score"],
            "target_score": TARGET_DRAFT_SCORE,
            "target_score_met": target_score_met,
            "attempt_count": len(attempts),
            "attempts": attempts,
            "evaluation": {
                "best_candidate": best_candidate["evaluation"],
                "attempt_summaries": [
                    {
                        "attempt": item["attempt"],
                        "best_score": item["best_score"],
                        "issues": item.get("issues", []),
                    }
                    for item in attempts
                ],
                "attempts": attempts,
            },
        }

    def score_draft(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        candidate_text: str,
        matched_theme_tweets: list[dict[str, Any]],
        theme_keywords: list[str],
        theme_top_keywords: list[str],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        payload = self._chat_completion_json(
            system_prompt=(
                "You are a strict evaluator for whether a generated X post sounds like the same author "
                "for the specific topic at hand. Score style fit from 0 to 10. "
                "Return strict JSON with keys: score, verdict, strengths, issues, must_fix."
            ),
            user_prompt=json.dumps(
                {
                    "persona": {
                        "author_summary": persona.get("author_summary", ""),
                        "voice_traits": persona.get("voice_traits", []),
                        "do_not_sound_like": persona.get("do_not_sound_like", []),
                        "generation_guardrails": persona.get("generation_guardrails", {}),
                    },
                    "prompt": prompt,
                    "candidate_text": candidate_text,
                    "theme_keywords": theme_keywords,
                    "theme_top_keywords": theme_top_keywords,
                    "matched_theme_tweets": matched_theme_tweets[:8],
                    "instructions": [
                        "Score whether this post sounds like the same author on this topic, not whether it is generally well-written.",
                        "Penalize generic summary language, topic drift, unnatural words, and phrases that do not fit the matched historical tweets.",
                        "Do not reward polished completeness if the author's style is naturally compressed.",
                    ],
                },
                ensure_ascii=True,
            ),
            temperature=0.2,
            request_id=request_id,
            purpose="score",
            timeout_seconds=float(self.settings.llm_score_timeout_seconds),
        )
        score = payload.get("score", 0)
        try:
            score_value = max(0.0, min(10.0, round(float(score), 1)))
        except (TypeError, ValueError):
            score_value = 0.0
        return {
            "score": score_value,
            "verdict": clean_text(str(payload.get("verdict") or "")),
            "strengths": _as_string_list(payload.get("strengths")),
            "issues": _as_string_list(payload.get("issues")),
            "must_fix": _as_string_list(payload.get("must_fix")),
        }

    def _evaluate_candidate(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        candidate_text: str,
        source_texts: list[str],
        matched_theme_tweets: list[dict[str, Any]],
        theme_keywords: list[str],
        theme_top_keywords: list[str],
        request_id: str | None = None,
    ) -> dict[str, Any]:
        rule_evaluation = self._rule_score_draft(
            persona=persona,
            prompt=prompt,
            candidate_text=candidate_text,
            source_texts=source_texts,
            matched_theme_tweets=matched_theme_tweets,
            theme_keywords=theme_keywords,
            theme_top_keywords=theme_top_keywords,
        )
        llm_evaluation = {
            "score": round(rule_evaluation["score"], 1),
            "verdict": "Skipped due to rule score gate",
            "strengths": [],
            "issues": [],
            "must_fix": rule_evaluation["issues"][:4],
        }
        if rule_evaluation["passed"] and not rule_evaluation["hard_fail"]:
            try:
                llm_evaluation = self.score_draft(
                    persona=persona,
                    prompt=prompt,
                    candidate_text=candidate_text,
                    matched_theme_tweets=matched_theme_tweets,
                    theme_keywords=theme_keywords,
                    theme_top_keywords=theme_top_keywords,
                    request_id=request_id,
                )
            except LLMTransportError as exc:
                llm_evaluation = {
                    "score": round(rule_evaluation["score"], 1),
                    "verdict": "provider_timeout_fallback",
                    "strengths": [],
                    "issues": [f"LLM scoring skipped after transient provider failure: {exc.category}"],
                    "must_fix": [],
                }
                log_event(
                    logger,
                    logging.WARNING,
                    "draft_candidate_score_fallback",
                    request_id=request_id,
                    provider=self.provider_name,
                    fallback_score=llm_evaluation["score"],
                    error_category=exc.category,
                    text_snippet=redact_for_log(candidate_text, 160),
                )
        final_score = round(min(rule_evaluation["score"], llm_evaluation["score"]), 1)
        failure_reasons = []
        if final_score < TARGET_DRAFT_SCORE:
            failure_reasons = _dedupe_preserve_order(
                rule_evaluation["issues"] + llm_evaluation["issues"] + llm_evaluation["must_fix"]
            )
        return {
            "rule_score": round(rule_evaluation["score"], 1),
            "llm_score": round(llm_evaluation["score"], 1),
            "final_score": final_score,
            "passed": final_score >= TARGET_DRAFT_SCORE,
            "rule_issues": rule_evaluation["issues"],
            "rule_strengths": rule_evaluation["strengths"],
            "llm_verdict": llm_evaluation["verdict"],
            "llm_issues": llm_evaluation["issues"],
            "llm_strengths": llm_evaluation["strengths"],
            "must_fix": llm_evaluation["must_fix"] or rule_evaluation["issues"][:4],
            "failure_reasons": failure_reasons,
        }

    def _rule_score_draft(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        candidate_text: str,
        source_texts: list[str],
        matched_theme_tweets: list[dict[str, Any]],
        theme_keywords: list[str],
        theme_top_keywords: list[str],
    ) -> dict[str, Any]:
        issues: list[str] = []
        strengths: list[str] = []
        score = 10.0

        banned_phrases = _as_string_list(persona.get("banned_phrases"))
        for phrase in banned_phrases:
            if keyword_in_text(phrase, candidate_text):
                return {
                    "score": 0.0,
                    "passed": False,
                    "hard_fail": True,
                    "issues": [f"Uses banned phrase: {phrase}"],
                    "strengths": [],
                }

        if is_too_similar(candidate_text, source_texts, self.settings.similarity_threshold):
            return {
                "score": 0.0,
                "passed": False,
                "hard_fail": True,
                "issues": ["Too similar to a historical tweet"],
                "strengths": [],
            }

        theme_hits = [keyword for keyword in theme_keywords if keyword_in_text(keyword, candidate_text)]
        if theme_hits:
            strengths.append(f"Theme keyword hits: {', '.join(theme_hits[:3])}")
        else:
            score -= 2.5
            issues.append("Does not use any explicit theme keyword")

        top_hits = [keyword for keyword in theme_top_keywords if keyword_in_text(keyword, candidate_text)]
        if top_hits:
            strengths.append(f"Theme corpus hits: {', '.join(top_hits[:3])}")
        else:
            score -= 1.5
            issues.append("Misses the top keywords from matched historical tweets")

        if prompt_requests_full_chinese(prompt):
            allowed_english = {
                keyword.lower()
                for keyword in theme_keywords
                if not any("\u4e00" <= char <= "\u9fff" for char in keyword)
            }
            disallowed_english = [
                word
                for word in extract_english_words(candidate_text)
                if word.lower() not in allowed_english
            ]
        else:
            disallowed_english = []
        if disallowed_english:
            score -= 2.0
            issues.append("Contains English despite full-Chinese prompt")

        for phrase in SUMMARY_DRIFT_PHRASES:
            if phrase in candidate_text:
                score -= 1.5
                issues.append(f"Summary-style drift phrase detected: {phrase}")

        lexical_markers = _as_string_list(persona.get("lexical_markers"))
        for marker in lexical_markers:
            if keyword_in_text(marker, candidate_text):
                marker_frequency = phrase_frequency(matched_theme_tweets, marker)
                if marker_frequency == 0 and matched_theme_tweets:
                    score -= 2.0
                    issues.append(f"Low-frequency topic drift phrase: {marker}")

        sentence_count = max(
            1,
            len([part for part in re.split(r"[.!?。！？]+", candidate_text) if clean_text(part)]),
        )
        if len(candidate_text) > 220 or sentence_count > 3:
            score -= 1.0
            issues.append("Reads too complete or essay-like for a compact timeline post")

        score = max(0.0, round(score, 1))
        return {
            "score": score,
            "passed": score >= MIN_RULE_SCORE_FOR_LLM_REVIEW,
            "hard_fail": False,
            "issues": issues,
            "strengths": strengths,
        }

    def _build_attempt_feedback(self, attempt_candidates: list[dict[str, Any]]) -> list[str]:
        if not attempt_candidates:
            return []
        best_failed = sorted(
            attempt_candidates,
            key=lambda item: item["final_score"],
            reverse=True,
        )[0]
        feedback = best_failed.get("must_fix") or best_failed.get("rule_issues") or []
        return feedback[:4]

    def _candidate_result(
        self,
        *,
        text: str,
        tone_tags: list[str],
        rationale: str,
        evaluation: dict[str, Any],
    ) -> dict[str, Any]:
        return DraftCandidateEvaluation(
            text=text,
            tone_tags=tone_tags,
            rationale=rationale,
            rule_score=float(evaluation.get("rule_score", 0.0)),
            llm_score=float(evaluation.get("llm_score", 0.0)),
            final_score=float(evaluation.get("final_score", 0.0)),
            passed=bool(evaluation.get("passed", False)),
            rule_issues=_as_string_list(evaluation.get("rule_issues")),
            rule_strengths=_as_string_list(evaluation.get("rule_strengths")),
            llm_verdict=clean_text(str(evaluation.get("llm_verdict") or "")),
            llm_issues=_as_string_list(evaluation.get("llm_issues")),
            llm_strengths=_as_string_list(evaluation.get("llm_strengths")),
            must_fix=_as_string_list(evaluation.get("must_fix")),
            failure_reasons=_as_string_list(evaluation.get("failure_reasons")),
        ).dict()

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_id: str | None = None,
        purpose: str = "generation",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def _normalize_persona_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)

        normalized["persona_version"] = str(normalized.get("persona_version") or "v1")
        normalized["author_summary"] = clean_text(str(normalized.get("author_summary") or ""))
        normalized["voice_traits"] = _as_string_list(normalized.get("voice_traits"))
        normalized["lexical_markers"] = _as_string_list(normalized.get("lexical_markers"))
        normalized["do_not_sound_like"] = _as_string_list(normalized.get("do_not_sound_like"))
        normalized["generation_guardrails"] = _normalize_generation_guardrails(
            normalized.get("generation_guardrails")
        )
        normalized["risk_notes"] = _as_string_list(normalized.get("risk_notes"))

        topic_clusters = normalized.get("topic_clusters")
        if not isinstance(topic_clusters, list):
            topic_clusters = [topic_clusters] if topic_clusters else []
        normalized["topic_clusters"] = [
            cluster if isinstance(cluster, dict) else {"topic": clean_text(str(cluster)), "evidence": []}
            for cluster in topic_clusters
            if cluster
        ]

        writing_patterns = normalized.get("writing_patterns")
        if isinstance(writing_patterns, dict):
            normalized["writing_patterns"] = writing_patterns
        elif isinstance(writing_patterns, list):
            normalized["writing_patterns"] = {"patterns": _as_string_list(writing_patterns)}
        elif writing_patterns:
            normalized["writing_patterns"] = {"summary": clean_text(str(writing_patterns))}
        else:
            normalized["writing_patterns"] = {}

        cta_style = normalized.get("cta_style")
        if isinstance(cta_style, dict):
            overall = clean_text(str(cta_style.get("overall") or ""))
            common_forms = _as_string_list(cta_style.get("common_forms"))
            if overall and common_forms:
                normalized["cta_style"] = f"{overall} Common forms: {'; '.join(common_forms[:3])}."
            else:
                normalized["cta_style"] = overall or "; ".join(common_forms[:3])
        elif isinstance(cta_style, list):
            normalized["cta_style"] = "; ".join(_as_string_list(cta_style)[:3])
        else:
            normalized["cta_style"] = clean_text(str(cta_style or ""))

        return normalized

    def _build_persona_request_payload(
        self,
        *,
        profile: dict[str, Any],
        corpus_stats: dict[str, Any],
        representative_tweets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "profile": {
                "name": profile.get("name"),
                "username": profile.get("username"),
                "description": profile.get("description"),
                "location": profile.get("location"),
                "followers_count": (profile.get("public_metrics") or {}).get("followers_count", 0),
                "following_count": (profile.get("public_metrics") or {}).get("following_count", 0),
            },
            "corpus_stats": corpus_stats,
            "representative_tweets": representative_tweets,
            "instructions": [
                "Keep author_summary to 3 sentences max.",
                "voice_traits should be 4 to 8 short traits.",
                "topic_clusters should be 3 to 6 clusters with topic and evidence terms.",
                "do_not_sound_like should capture style drift risks.",
                "generation_guardrails should translate the style into concrete writing rules for generation.",
                "generation_guardrails.preferred_openings should capture native ways this author often starts posts.",
                "generation_guardrails.preferred_formats should describe post shapes such as reaction, observation, link drop, thesis-lite, or scene-first.",
                "generation_guardrails.compression_rules should explain how much the author usually leaves implied instead of fully explained.",
                "generation_guardrails.anti_patterns should list the specific failure modes that would sound too polished, too abstract, too symmetrical, or too essay-like.",
                "generation_guardrails.language_notes should explain how to handle bilingual texture or code-switching naturally.",
                "risk_notes should mention limits of inference and sensitive content caution.",
            ],
        }

    def _build_draft_request_payload(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        representative_tweets: list[dict[str, Any]],
        matched_theme_tweets: list[dict[str, Any]],
        theme_keywords: list[str],
        theme_top_keywords: list[str],
        rejected_texts: list[str],
        attempt_feedback: list[str],
        draft_count: int,
    ) -> dict[str, Any]:
        guardrails = _normalize_generation_guardrails(persona.get("generation_guardrails"))
        return {
            "persona": persona,
            "style_brief": {
                "author_summary": clean_text(str(persona.get("author_summary") or "")),
                "voice_traits": _as_string_list(persona.get("voice_traits")),
                "lexical_markers": _as_string_list(persona.get("lexical_markers"))[:20],
                "do_not_sound_like": _as_string_list(persona.get("do_not_sound_like")),
                "generation_guardrails": guardrails,
            },
            "user_prompt": prompt,
            "representative_tweets": representative_tweets[:12],
            "matched_theme_tweets": matched_theme_tweets[:8],
            "theme_keywords": theme_keywords,
            "theme_top_keywords": theme_top_keywords,
            "avoid_texts": rejected_texts,
            "attempt_feedback": attempt_feedback,
            "drafting_rules": [
                "Prefer the persona's native opening moves and post formats over generic summary framing.",
                "Prioritize the matched theme tweets and their keyword patterns over unrelated global persona habits.",
                "If compression_rules are present, follow them closely: one sharp observation is better than a fully explained argument.",
                "Do not use anti_patterns even if they make the writing sound more polished.",
                "Keep the draft timeline-native. Fragments, incompleteness, or media-friendly endings are allowed when they fit the persona.",
                "Match the language requested by the user prompt. If the persona is bilingual, code-switch only when it feels native rather than decorative.",
            ],
            "constraints": {
                "draft_count": draft_count,
                "max_chars": 280,
                "language_mode": "Match the user's requested language and the persona's natural language texture.",
                "no_threads": True,
                "no_hashtags_unless_natural": True,
                "must_feel_like_same_author": True,
                "target_score": TARGET_DRAFT_SCORE,
            },
        }

    def _normalize_drafts_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, list):
            drafts = payload
        else:
            drafts = payload.get("drafts")
        if not isinstance(drafts, list):
            if isinstance(payload, dict) and isinstance(payload.get("items"), list):
                drafts = payload.get("items")
            else:
                drafts = []

        normalized_drafts = []
        for item in drafts:
            if isinstance(item, str):
                normalized_drafts.append(
                    {
                        "text": clean_text(item),
                        "tone_tags": [],
                        "rationale": "",
                    }
                )
                continue

            if not isinstance(item, dict):
                continue

            text = clean_text(str(item.get("text") or item.get("draft") or ""))
            if not text:
                continue
            tone_tags = item.get("tone_tags") or item.get("tags") or []
            rationale = item.get("rationale") or item.get("why") or ""
            normalized_drafts.append(
                {
                    "text": text,
                    "tone_tags": _as_string_list(tone_tags),
                    "rationale": clean_text(str(rationale)),
                }
            )

        return {"drafts": normalized_drafts}


class OpenAIClient(LLMClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, provider_name="openai")

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_id: str | None = None,
        purpose: str = "generation",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.settings.openai_api_key:
            raise LLMError("OPENAI_API_KEY is not configured")

        endpoint = f"{self.settings.openai_base_url.rstrip('/')}/chat/completions"
        body = self._post_json_with_retries(
            endpoint=endpoint,
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json_payload={
                "model": self.settings.openai_model,
                "temperature": temperature,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            model=self.settings.openai_model,
            request_id=request_id,
            purpose=purpose,
            timeout_seconds=timeout_seconds,
        )
        choices = body.get("choices") or []
        if not choices:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_missing_choices",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.openai_model,
            )
            raise LLMError("OpenAI response did not include any choices")

        content = choices[0].get("message", {}).get("content", "")
        content_text = _coerce_content_text(content)
        if not content_text:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_empty_content",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.openai_model,
            )
            raise LLMError("OpenAI response content was empty")

        return _parse_json_response(
            content_text,
            provider_name="OpenAI",
            request_id=request_id,
            max_body_chars=self.settings.log_max_body_chars,
        )


class GeminiClient(LLMClient):
    def __init__(self, settings: Settings):
        super().__init__(settings, provider_name="gemini")

    def _chat_completion_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        request_id: str | None = None,
        purpose: str = "generation",
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        if not self.settings.gemini_api_key:
            raise LLMError("GEMINI_API_KEY is not configured")

        endpoint = (
            f"{self.settings.gemini_base_url.rstrip('/')}/models/"
            f"{self.settings.gemini_model}:generateContent"
        )
        body = self._post_json_with_retries(
            endpoint=endpoint,
            params={"key": self.settings.gemini_api_key},
            headers={"Content-Type": "application/json"},
            json_payload={
                "system_instruction": {
                    "parts": [{"text": system_prompt}],
                },
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}],
                    }
                ],
                "generationConfig": {
                    "temperature": temperature,
                    "responseMimeType": "application/json",
                },
            },
            model=self.settings.gemini_model,
            request_id=request_id,
            purpose=purpose,
            timeout_seconds=timeout_seconds,
        )
        candidates = body.get("candidates") or []
        if not candidates:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_missing_candidates",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.gemini_model,
            )
            raise LLMError("Gemini response did not include any candidates")

        content = candidates[0].get("content", {}).get("parts", [])
        content_text = _coerce_content_text(content)
        if not content_text:
            log_event(
                logger,
                logging.ERROR,
                "llm_provider_empty_content",
                request_id=request_id,
                provider=self.provider_name,
                model=self.settings.gemini_model,
            )
            raise LLMError("Gemini response content was empty")

        return _parse_json_response(
            content_text,
            provider_name="Gemini",
            request_id=request_id,
            max_body_chars=self.settings.log_max_body_chars,
        )


def create_llm_client(settings: Settings) -> LLMClient:
    if settings.llm_provider == "gemini":
        return GeminiClient(settings)
    return OpenAIClient(settings)


def _as_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [clean_text(str(item)) for item in value if clean_text(str(item))]
    if isinstance(value, str):
        text = clean_text(value)
        return [text] if text else []
    text = clean_text(str(value))
    return [text] if text else []


def _normalize_generation_guardrails(value: Any) -> dict[str, list[str]]:
    if not value:
        return {}

    normalized = {key: [] for key in GENERATION_GUARDRAIL_KEYS}
    if isinstance(value, dict):
        for key in GENERATION_GUARDRAIL_KEYS:
            normalized[key] = _as_string_list(value.get(key))
    else:
        normalized["anti_patterns"] = _as_string_list(value)

    return {key: items for key, items in normalized.items() if items}


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        text = clean_text(value)
        if not text or text in seen:
            continue
        seen.add(text)
        results.append(text)
    return results


def _coerce_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for chunk in content:
            if isinstance(chunk, dict):
                parts.append(str(chunk.get("text", "")))
            else:
                parts.append(str(chunk))
        return "".join(parts)
    return str(content or "")


def _parse_json_response(
    content: str,
    *,
    provider_name: str,
    request_id: str | None = None,
    max_body_chars: int = 500,
) -> dict[str, Any]:
    candidates: list[tuple[str, str]] = [("raw", content)]
    fenced_content = _strip_json_fence(content)
    if fenced_content and fenced_content != content:
        candidates.append(("fence_stripped", fenced_content))

    extracted_candidates: list[tuple[str, str]] = []
    for strategy, candidate_text in candidates:
        extracted = _extract_first_json_value(candidate_text)
        if extracted and extracted != candidate_text:
            extracted_candidates.append((f"{strategy}_extracted", extracted))
    candidates.extend(extracted_candidates)

    seen_texts: set[str] = set()
    last_error: json.JSONDecodeError | None = None
    for strategy, candidate_text in candidates:
        if candidate_text in seen_texts:
            continue
        seen_texts.add(candidate_text)
        try:
            payload = json.loads(candidate_text)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        log_event(
            logger,
            logging.INFO,
            "llm_provider_json_parsed",
            request_id=request_id,
            provider=provider_name.lower(),
            payload_type=type(payload).__name__,
            parse_strategy=strategy,
        )
        return payload

    exc = last_error or json.JSONDecodeError("Could not parse JSON", content, 0)
    log_event(
        logger,
        logging.WARNING,
        "llm_provider_invalid_json",
        request_id=request_id,
        provider=provider_name.lower(),
        response_snippet=redact_for_log(content, max_body_chars),
    )
    raise LLMError(f"{provider_name} returned invalid JSON: {content[:500]}") from exc


def _strip_json_fence(content: str) -> str | None:
    match = re.search(r"```(?:json)?\s*(.*?)```", content, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return None
    stripped = match.group(1).strip()
    if stripped.lower().startswith("json\n"):
        stripped = stripped[5:].strip()
    return stripped or None


def _extract_first_json_value(content: str) -> str | None:
    start = None
    opening_char = ""
    for index, char in enumerate(content):
        if char in "[{":
            start = index
            opening_char = char
            break
    if start is None:
        return None

    stack = ["]" if opening_char == "[" else "}"]
    in_string = False
    escaped = False

    for index in range(start + 1, len(content)):
        char = content[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
            continue
        if char == "{":
            stack.append("}")
            continue
        if char == "[":
            stack.append("]")
            continue
        if char in "}]":
            if not stack or char != stack[-1]:
                return None
            stack.pop()
            if not stack:
                return content[start : index + 1]

    return None
