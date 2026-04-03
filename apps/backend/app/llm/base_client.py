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

from .errors import LLMError, LLMTransportError
from .utils import (
    MIN_RULE_SCORE_FOR_LLM_REVIEW,
    TARGET_DRAFT_SCORE,
    _as_string_list,
    _dedupe_preserve_order,
    _normalize_generation_guardrails,
)

logger = get_logger(__name__)


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
    ) -> Any:
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
                else len(
                    str(
                        (((json_payload.get("system_instruction") or {}).get("parts") or [{"text": ""}])[0]).get(
                            "text", ""
                        )
                    )
                ),
                user_prompt_len=len(str((json_payload.get("messages") or [{}, {"content": ""}])[-1].get("content", "")))
                if "messages" in json_payload
                else len(
                    str(
                        ((((json_payload.get("contents") or [{}])[0]).get("parts") or [{"text": ""}])[0]).get(
                            "text", ""
                        )
                    )
                ),
                proxy_enabled=bool(self.settings.llm_proxies),
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
                    proxies=self.settings.llm_proxies,
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
        full_chinese_mode = prompt_requests_full_chinese(prompt)
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

        candidates_per_round = min(draft_count * 2, 5)
        max_rounds = self.settings.max_generation_attempts
        all_candidates: list[dict[str, Any]] = []
        attempts: list[dict[str, Any]] = []
        seen_texts: set[str] = set()
        rejected_texts: list[str] = []
        attempt_feedback: list[str] = []

        for round_index in range(1, max_rounds + 1):
            accepted_count = sum(1 for c in all_candidates if c["evaluation"]["final_score"] >= TARGET_DRAFT_SCORE)
            needed_count = draft_count - accepted_count
            log_event(
                logger,
                logging.INFO,
                "draft_generation_attempt_started",
                request_id=request_id,
                provider=self.provider_name,
                attempt=round_index,
                needed_count=needed_count,
                accepted_count=accepted_count,
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
                draft_count=candidates_per_round,
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

            normalized_payload = self._normalize_drafts_payload(payload)
            log_event(
                logger,
                logging.INFO,
                "draft_generation_payload_received",
                request_id=request_id,
                provider=self.provider_name,
                attempt=round_index,
                payload_type=type(payload).__name__,
            )
            try:
                generated = DraftsOutput.parse_obj(normalized_payload).drafts
            except ValidationError as exc:
                log_event(
                    logger,
                    logging.ERROR,
                    "draft_generation_schema_failed",
                    request_id=request_id,
                    provider=self.provider_name,
                    round_index=round_index,
                    error=str(exc),
                    payload_snippet=redact_for_log(normalized_payload, self.settings.log_max_body_chars),
                )
                raise LLMError(f"Draft schema validation failed: {exc}") from exc

            to_evaluate: list[tuple[str, DraftItem]] = []
            for item in generated:
                text = clean_text(item.text)
                if not text or len(text) > 280:
                    if text:
                        rejected_texts.append(text)
                    continue
                normalized = text.lower()
                if normalized in seen_texts:
                    rejected_texts.append(text)
                    continue
                seen_texts.add(normalized)
                to_evaluate.append((text, item))

            round_candidates: list[dict[str, Any]] = []
            rule_results: list[dict[str, Any]] = []
            for text, _ in to_evaluate:
                rule_eval = self._rule_score_draft(
                    persona=persona,
                    prompt=prompt,
                    candidate_text=text,
                    source_texts=source_texts,
                    matched_theme_tweets=matched_theme_tweets,
                    theme_keywords=theme_keywords,
                    theme_top_keywords=theme_top_keywords,
                )
                rule_results.append(rule_eval)

            llm_eligible_indices = [
                i for i, rule_eval in enumerate(rule_results) if rule_eval["passed"] and not rule_eval["hard_fail"]
            ]

            llm_batch_results: list[dict[str, Any]] = []
            if llm_eligible_indices:
                eligible_texts = [to_evaluate[i][0] for i in llm_eligible_indices]
                try:
                    llm_batch_results = self.score_drafts_batch(
                        persona=persona,
                        prompt=prompt,
                        candidate_texts=eligible_texts,
                        matched_theme_tweets=matched_theme_tweets,
                        theme_keywords=theme_keywords,
                        theme_top_keywords=theme_top_keywords,
                        request_id=request_id,
                    )
                except LLMTransportError as exc:
                    llm_batch_results = [
                        {
                            "score": round(rule_results[i]["score"], 1),
                            "verdict": "provider_timeout_fallback",
                            "strengths": [],
                            "issues": [f"LLM scoring skipped after transient failure: {exc.category}"],
                            "must_fix": [],
                        }
                        for i in llm_eligible_indices
                    ]
                    log_event(
                        logger,
                        logging.WARNING,
                        "draft_batch_score_fallback",
                        request_id=request_id,
                        provider=self.provider_name,
                        error_category=exc.category,
                        eligible_count=len(llm_eligible_indices),
                    )

            llm_result_map: dict[int, dict[str, Any]] = {}
            for batch_idx, orig_idx in enumerate(llm_eligible_indices):
                if batch_idx < len(llm_batch_results):
                    llm_result_map[orig_idx] = llm_batch_results[batch_idx]

            for i, (text, eval_item) in enumerate(to_evaluate):
                rule_eval = rule_results[i]
                llm_eval = llm_result_map.get(
                    i,
                    {
                        "score": round(rule_eval["score"], 1),
                        "verdict": "Skipped due to rule score gate",
                        "strengths": [],
                        "issues": [],
                        "must_fix": rule_eval["issues"][:4],
                    },
                )
                final_score = self._compute_final_score(rule_eval["score"], llm_eval["score"])
                failure_reasons = []
                if final_score < TARGET_DRAFT_SCORE:
                    failure_reasons = _dedupe_preserve_order(
                        rule_eval["issues"] + llm_eval["issues"] + llm_eval.get("must_fix", [])
                    )
                evaluation = {
                    "rule_score": round(rule_eval["score"], 1),
                    "llm_score": round(llm_eval["score"], 1),
                    "final_score": final_score,
                    "passed": final_score >= TARGET_DRAFT_SCORE,
                    "rule_issues": rule_eval["issues"],
                    "rule_strengths": rule_eval["strengths"],
                    "llm_verdict": llm_eval["verdict"],
                    "llm_issues": llm_eval.get("issues", []),
                    "llm_strengths": llm_eval.get("strengths", []),
                    "must_fix": llm_eval.get("must_fix", []) or rule_eval["issues"][:4],
                    "failure_reasons": failure_reasons,
                }
                candidate = {
                    "text": text,
                    "tone_tags": eval_item.tone_tags[:4],
                    "rationale": clean_text(eval_item.rationale),
                    "evaluation": evaluation,
                }
                round_candidates.append(candidate)
                all_candidates.append(candidate)
                log_event(
                    logger,
                    logging.INFO,
                    "draft_candidate_scored",
                    request_id=request_id,
                    provider=self.provider_name,
                    attempt=round_index,
                    final_score=evaluation["final_score"],
                    rule_score=evaluation["rule_score"],
                    llm_score=evaluation["llm_score"],
                    passed=evaluation["passed"],
                    failure_reasons=evaluation["failure_reasons"][:3],
                    text_snippet=redact_for_log(text, 160),
                )

            round_candidate_results = [self._candidate_result(**c) for c in round_candidates]
            best_round_score = max(
                (float(c.get("final_score", 0.0)) for c in round_candidate_results),
                default=0.0,
            )
            target_met = any(c["passed"] for c in round_candidate_results)
            attempt_feedback = self._build_attempt_feedback(round_candidate_results)
            attempts.append(
                {
                    "attempt": round_index,
                    "best_score": best_round_score,
                    "target_score_met": target_met,
                    "candidates": round_candidate_results,
                    "issues": attempt_feedback,
                }
            )
            for c in round_candidates:
                if c["evaluation"]["final_score"] < TARGET_DRAFT_SCORE:
                    rejected_texts.append(c["text"])

            log_event(
                logger,
                logging.INFO,
                "draft_generation_attempt_completed",
                request_id=request_id,
                provider=self.provider_name,
                attempt=round_index,
                best_score=best_round_score,
                target_score_met=target_met,
                candidate_count=len(round_candidates),
                feedback=attempt_feedback,
            )

            passed_count = sum(1 for c in all_candidates if c["evaluation"]["final_score"] >= TARGET_DRAFT_SCORE)
            if passed_count >= draft_count:
                break

        ranked_candidates = sorted(
            all_candidates,
            key=lambda item: item["evaluation"]["final_score"],
            reverse=True,
        )
        if full_chinese_mode:
            full_chinese_candidates = [
                item
                for item in ranked_candidates
                if not any(
                    issue.startswith("Contains English despite full-Chinese prompt")
                    for issue in item["evaluation"]["rule_issues"]
                )
            ]
            if full_chinese_candidates:
                ranked_candidates = full_chinese_candidates
            else:
                log_event(
                    logger,
                    logging.WARNING,
                    "draft_generation_full_chinese_fallback",
                    request_id=request_id,
                    provider=self.provider_name,
                    candidate_count=len(ranked_candidates),
                    reason="no_full_chinese_candidate",
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
        target_score_met = len(selected_candidates) >= draft_count and all(
            item["evaluation"]["final_score"] >= TARGET_DRAFT_SCORE for item in selected_candidates
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
                        "Score whether this post sounds like the same author on this topic, "
                        "not whether it is generally well-written.",
                        "Penalize generic summary language, topic drift, unnatural words, "
                        "and phrases that do not fit the matched historical tweets.",
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
        normalized_payload = self._normalize_score_payload(payload, request_id=request_id)
        score = normalized_payload.get("score", 0)
        try:
            score_value = max(0.0, min(10.0, round(float(score), 1)))
        except (TypeError, ValueError):
            score_value = 0.0
        return {
            "score": score_value,
            "verdict": clean_text(str(normalized_payload.get("verdict") or "")),
            "strengths": _as_string_list(normalized_payload.get("strengths")),
            "issues": _as_string_list(normalized_payload.get("issues")),
            "must_fix": _as_string_list(normalized_payload.get("must_fix")),
        }

    def score_drafts_batch(
        self,
        *,
        persona: dict[str, Any],
        prompt: str,
        candidate_texts: list[str],
        matched_theme_tweets: list[dict[str, Any]],
        theme_keywords: list[str],
        theme_top_keywords: list[str],
        request_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if not candidate_texts:
            return []
        candidates_input = [{"index": i, "text": text} for i, text in enumerate(candidate_texts)]
        payload = self._chat_completion_json(
            system_prompt=(
                "You are a strict evaluator for whether generated X posts sound like the same author "
                "for the specific topic at hand. Score each candidate's style fit from 0 to 10. "
                "Return strict JSON with key 'scores': an array of objects, one per candidate, "
                "each with keys: index, score, verdict, strengths, issues, must_fix."
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
                    "candidates": candidates_input,
                    "theme_keywords": theme_keywords,
                    "theme_top_keywords": theme_top_keywords,
                    "matched_theme_tweets": matched_theme_tweets[:8],
                    "instructions": [
                        "Score whether each post sounds like the same author on this topic, "
                        "not whether it is generally well-written.",
                        "Penalize generic summary language, topic drift, unnatural words, "
                        "and phrases that do not fit the matched historical tweets.",
                        "Do not reward polished completeness if the author's style is naturally compressed.",
                        "Return one score object per candidate in the same order.",
                    ],
                },
                ensure_ascii=True,
            ),
            temperature=0.2,
            request_id=request_id,
            purpose="score_batch",
            timeout_seconds=float(self.settings.llm_score_timeout_seconds) + len(candidate_texts) * 3,
        )
        scores_raw = payload.get("scores") if isinstance(payload, dict) else None
        if not isinstance(scores_raw, list):
            if isinstance(payload, list):
                scores_raw = payload
            else:
                scores_raw = []

        results: list[dict[str, Any]] = [
            {"score": 0.0, "verdict": "missing", "strengths": [], "issues": [], "must_fix": []} for _ in candidate_texts
        ]
        for position, item in enumerate(scores_raw):
            if not isinstance(item, dict):
                continue
            idx = item.get("index")
            if idx is None:
                idx = position
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                idx = position
            if 0 <= idx < len(candidate_texts):
                score_val = item.get("score", 0)
                try:
                    score_val = max(0.0, min(10.0, round(float(score_val), 1)))
                except (TypeError, ValueError):
                    score_val = 0.0
                results[idx] = {
                    "score": score_val,
                    "verdict": clean_text(str(item.get("verdict") or "")),
                    "strengths": _as_string_list(item.get("strengths")),
                    "issues": _as_string_list(item.get("issues")),
                    "must_fix": _as_string_list(item.get("must_fix")),
                }
        return results

    @staticmethod
    def _compute_final_score(rule_score: float, llm_score: float) -> float:
        return round(rule_score * 0.4 + llm_score * 0.6, 1)

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
            except LLMError as exc:
                error_category = getattr(exc, "category", "response_schema")
                fallback_verdict = (
                    "provider_timeout_fallback" if isinstance(exc, LLMTransportError) else "provider_response_fallback"
                )
                llm_evaluation = {
                    "score": round(rule_evaluation["score"], 1),
                    "verdict": fallback_verdict,
                    "strengths": [],
                    "issues": [f"LLM scoring skipped after provider failure: {error_category}"],
                    "must_fix": [],
                }
                log_event(
                    logger,
                    logging.WARNING,
                    "draft_candidate_score_fallback",
                    request_id=request_id,
                    provider=self.provider_name,
                    fallback_score=llm_evaluation["score"],
                    error_category=error_category,
                    text_snippet=redact_for_log(candidate_text, 160),
                )
        final_score = self._compute_final_score(rule_evaluation["score"], llm_evaluation["score"])
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

        full_chinese_mode = prompt_requests_full_chinese(prompt)
        if full_chinese_mode:
            allowed_english = self._allowed_english_tokens_for_full_chinese_prompt(
                prompt=prompt,
                theme_keywords=theme_keywords,
            )
            disallowed_english = [
                word for word in extract_english_words(candidate_text) if word.lower() not in allowed_english
            ]
        else:
            disallowed_english = []
        if disallowed_english:
            score -= 6.0
            sample = ", ".join(sorted(set(word.lower() for word in disallowed_english))[:4])
            issues.append(f"Contains English despite full-Chinese prompt: {sample}")

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
    ) -> Any:
        raise NotImplementedError

    def _normalize_persona_payload(self, payload: Any) -> dict[str, Any]:
        if isinstance(payload, list):
            payload = next((item for item in payload if isinstance(item, dict)), {})
        if not isinstance(payload, dict):
            payload = {}
        normalized = dict(payload)

        normalized["persona_version"] = str(normalized.get("persona_version") or "v1")
        normalized["author_summary"] = clean_text(str(normalized.get("author_summary") or ""))
        normalized["voice_traits"] = _as_string_list(normalized.get("voice_traits"))
        normalized["lexical_markers"] = _as_string_list(normalized.get("lexical_markers"))
        normalized["do_not_sound_like"] = _as_string_list(normalized.get("do_not_sound_like"))
        normalized["generation_guardrails"] = _normalize_generation_guardrails(normalized.get("generation_guardrails"))
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

    def _normalize_score_payload(self, payload: Any, *, request_id: str | None = None) -> dict[str, Any]:
        if not isinstance(payload, dict):
            log_event(
                logger,
                logging.ERROR,
                "draft_score_schema_failed",
                request_id=request_id,
                provider=self.provider_name,
                payload_type=type(payload).__name__,
                payload_snippet=redact_for_log(payload, self.settings.log_max_body_chars),
            )
            raise LLMError(f"Score schema validation failed: expected object, got {type(payload).__name__}")

        return {
            "score": payload.get("score", 0),
            "verdict": payload.get("verdict", ""),
            "strengths": payload.get("strengths", []),
            "issues": payload.get("issues", []),
            "must_fix": payload.get("must_fix", []),
        }

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
                "generation_guardrails.preferred_formats should describe post shapes "
                "such as reaction, observation, link drop, thesis-lite, or scene-first.",
                "generation_guardrails.compression_rules should explain how much "
                "the author usually leaves implied instead of fully explained.",
                "generation_guardrails.anti_patterns should list the specific failure modes "
                "that would sound too polished, too abstract, too symmetrical, or too essay-like.",
                "generation_guardrails.language_notes should explain "
                "how to handle bilingual texture or code-switching naturally.",
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
        full_chinese_mode = prompt_requests_full_chinese(prompt)
        allowed_english_tokens_set = self._allowed_english_tokens_for_full_chinese_prompt(
            prompt=prompt,
            theme_keywords=theme_keywords,
        )
        prompt_for_generation = (
            self._sanitize_prompt_for_full_chinese_mode(
                prompt=prompt,
                theme_keywords=theme_keywords,
                allowed_english_tokens=allowed_english_tokens_set,
            )
            if full_chinese_mode
            else prompt
        )
        allowed_english_tokens = sorted(allowed_english_tokens_set)
        drafting_rules = [
            "Prefer the persona's native opening moves and post formats over generic summary framing.",
            "Prioritize the matched theme tweets and their keyword patterns over unrelated global persona habits.",
            "If compression_rules are present, follow them closely: "
            "one sharp observation is better than a fully explained argument.",
            "Do not use anti_patterns even if they make the writing sound more polished.",
            "Keep the draft timeline-native. Fragments, incompleteness, "
            "or media-friendly endings are allowed when they fit the persona.",
            "Match the language requested by the user prompt. If the persona is bilingual, "
            "code-switch only when it feels native rather than decorative.",
        ]
        if full_chinese_mode:
            drafting_rules.append(
                "Full-Chinese mode is required: keep the draft in Chinese. "
                "Use English only for exact tokens that already exist in user_prompt/theme_keywords."
            )
        return {
            "persona": persona,
            "style_brief": {
                "author_summary": clean_text(str(persona.get("author_summary") or "")),
                "voice_traits": _as_string_list(persona.get("voice_traits")),
                "lexical_markers": _as_string_list(persona.get("lexical_markers"))[:20],
                "do_not_sound_like": _as_string_list(persona.get("do_not_sound_like")),
                "generation_guardrails": guardrails,
            },
            "user_prompt": prompt_for_generation,
            "representative_tweets": representative_tweets[:12],
            "matched_theme_tweets": matched_theme_tweets[:8],
            "theme_keywords": theme_keywords,
            "theme_top_keywords": theme_top_keywords,
            "avoid_texts": rejected_texts,
            "attempt_feedback": attempt_feedback,
            "drafting_rules": drafting_rules,
            "constraints": {
                "draft_count": draft_count,
                "max_chars": 280,
                "language_mode": (
                    "Full-Chinese only (unless exact user-provided English tokens are necessary)."
                    if full_chinese_mode
                    else "Match the user's requested language and the persona's natural language texture."
                ),
                "full_chinese_only": full_chinese_mode,
                "allowed_english_tokens": allowed_english_tokens,
                "no_threads": True,
                "no_hashtags_unless_natural": True,
                "must_feel_like_same_author": True,
                "target_score": TARGET_DRAFT_SCORE,
            },
        }

    def _allowed_english_tokens_for_full_chinese_prompt(
        self,
        *,
        prompt: str,
        theme_keywords: list[str],
    ) -> set[str]:
        allowed_tokens: set[str] = set()
        for keyword in theme_keywords:
            for token in extract_english_words(keyword):
                lowered = token.lower()
                if len(lowered) >= 2:
                    allowed_tokens.add(lowered)

        lowered_prompt = prompt.lower()
        allow_markers = ("保留英文", "英文术语", "专有名词英文", "可以英文")
        if any(marker in lowered_prompt for marker in allow_markers):
            for token in extract_english_words(prompt):
                lowered = token.lower()
                if len(lowered) >= 2:
                    allowed_tokens.add(lowered)
        return allowed_tokens

    def _sanitize_prompt_for_full_chinese_mode(
        self,
        *,
        prompt: str,
        theme_keywords: list[str],
        allowed_english_tokens: set[str],
    ) -> str:
        preserved_tokens: set[str] = set(allowed_english_tokens)
        for keyword in theme_keywords:
            for token in extract_english_words(keyword):
                lowered = token.lower()
                if len(lowered) >= 2:
                    preserved_tokens.add(lowered)

        def replace_english_word(match: re.Match[str]) -> str:
            token = match.group(0)
            if token.lower() in preserved_tokens:
                return token
            return "某工具"

        normalized_prompt = re.sub(r"[A-Za-z][A-Za-z0-9']*", replace_english_word, prompt)
        normalized_prompt = re.sub(r"(某工具\s*){2,}", "某工具", normalized_prompt)
        return clean_text(normalized_prompt)

    def _normalize_drafts_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        if isinstance(payload, list):
            drafts = payload
        else:
            drafts = payload.get("drafts")
        if not isinstance(drafts, list):
            items = payload.get("items") if isinstance(payload, dict) else None
            drafts = items if isinstance(items, list) else []

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
