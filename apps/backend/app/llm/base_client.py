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
    prompt_language_mode,
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
SARCASM_LITERAL_MARKERS = {
    "yeah sure",
    "yeah right",
    "笑死",
    "离谱",
    "又来了",
    "呵呵",
    "真有你的",
    "好家伙",
    "绝了",
}
SARCASM_REGEX_PATTERNS = (
    re.compile(r"\b(?:lol|lmao|lmfao|rofl)\b", flags=re.IGNORECASE),
    re.compile(r"\b(?:sure|of course|right),\s+(?:because|as if|why not)\b", flags=re.IGNORECASE),
    re.compile(r"\bwhat could possibly go wrong\b", flags=re.IGNORECASE),
)
LINK_FORWARD_MARKERS = {
    "link below",
    "full article",
    "read more",
    "点击链接",
    "详见链接",
    "见下方链接",
}


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
                "generation_guardrails, risk_notes, language_profile, domain_expertise, "
                "emotional_baseline, audience_profile, interaction_style, posting_cadence, "
                "media_habits, geo_context, stance_patterns, banned_phrases."
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
        full_chinese_mode = prompt_language_mode(prompt) == "full_chinese"
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
                    "Use the full style_brief, including emotional_baseline, audience_profile, "
                    "interaction_style, posting_cadence, media_habits, geo_context, and stance_patterns. "
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
                        "language_profile": persona.get("language_profile", {}),
                        "emotional_baseline": persona.get("emotional_baseline", {}),
                        "audience_profile": persona.get("audience_profile", {}),
                        "interaction_style": persona.get("interaction_style", {}),
                        "posting_cadence": persona.get("posting_cadence", {}),
                        "media_habits": persona.get("media_habits", {}),
                        "geo_context": persona.get("geo_context", {}),
                        "stance_patterns": persona.get("stance_patterns", {}),
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
                        "Check whether the emotional register, sarcasm level, and humor "
                        "feel aligned with emotional_baseline.",
                        "Check whether the amount of polish and assumed context fit audience_profile.",
                        "Check whether the tone feels consistent with interaction_style for the likely post type.",
                        "Check whether the draft matches the persona's posting cadence and media habit defaults.",
                        "Check whether the draft invents unsupported local context or event proximity inconsistent "
                        "with geo_context.",
                        "Check whether hot-take intensity, controversy posture, and endorsement style fit "
                        "stance_patterns.",
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
                        "language_profile": persona.get("language_profile", {}),
                        "emotional_baseline": persona.get("emotional_baseline", {}),
                        "audience_profile": persona.get("audience_profile", {}),
                        "interaction_style": persona.get("interaction_style", {}),
                        "posting_cadence": persona.get("posting_cadence", {}),
                        "media_habits": persona.get("media_habits", {}),
                        "geo_context": persona.get("geo_context", {}),
                        "stance_patterns": persona.get("stance_patterns", {}),
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
                        "Check whether emotional register, sarcasm level, and humor "
                        "feel aligned with emotional_baseline.",
                        "Check whether the amount of polish and assumed context fit audience_profile.",
                        "Check whether the tone feels consistent with interaction_style for the likely post type.",
                        "Check whether each draft matches the persona's posting cadence and media habit defaults.",
                        "Check whether the draft invents unsupported local context or event proximity inconsistent "
                        "with geo_context.",
                        "Check whether hot-take intensity, controversy posture, and endorsement style fit "
                        "stance_patterns.",
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
        language_mode = prompt_language_mode(prompt)

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

        full_chinese_mode = language_mode == "full_chinese"
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

        has_summary_drift = False
        for phrase in SUMMARY_DRIFT_PHRASES:
            if phrase in candidate_text:
                has_summary_drift = True
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
        reads_too_complete = len(candidate_text) > 220 or sentence_count > 3
        if reads_too_complete:
            score -= 1.0
            issues.append("Reads too complete or essay-like for a compact timeline post")

        too_polished = reads_too_complete or has_summary_drift
        audience_formality = self._persona_audience_formality(persona)
        if audience_formality in {"raw", "casual"} and too_polished:
            score -= 1.0
            issues.append("Polish level is especially misaligned for this persona's casual audience")

        sarcasm_level = self._persona_sarcasm_level(persona)
        if sarcasm_level in {"frequent", "defining"} and self._draft_sounds_earnest(candidate_text):
            score -= 1.5
            issues.append("Draft lacks expected sarcasm for this persona")

        posting_cadence = self._normalize_posting_cadence(persona.get("posting_cadence"))
        if (
            posting_cadence["preferred_post_length"] == "short" or posting_cadence["posting_style"] == "burst-poster"
        ) and reads_too_complete:
            score -= 1.0
            issues.append("Too complete for this persona's posting cadence")

        media_habits = self._normalize_media_habits(persona.get("media_habits"))
        if media_habits["dominant_format"] == "text-only" and self._draft_is_link_forward(candidate_text):
            score -= 1.0
            issues.append("Too link-forward for this persona's text-only habit")
        if media_habits["dominant_format"] == "media-led" and reads_too_complete:
            score -= 0.5
            issues.append("Too self-contained for this persona's media-led habit")

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

        normalized["persona_version"] = "v1"
        normalized["author_summary"] = clean_text(str(normalized.get("author_summary") or ""))
        normalized["voice_traits"] = _as_string_list(normalized.get("voice_traits"))
        normalized["lexical_markers"] = _as_string_list(normalized.get("lexical_markers"))
        normalized["do_not_sound_like"] = _as_string_list(normalized.get("do_not_sound_like"))
        normalized["generation_guardrails"] = _normalize_generation_guardrails(normalized.get("generation_guardrails"))
        normalized["risk_notes"] = _as_string_list(normalized.get("risk_notes"))
        normalized["topic_clusters"] = self._normalize_topic_clusters(normalized.get("topic_clusters"))
        normalized["writing_patterns"] = self._normalize_writing_patterns(normalized.get("writing_patterns"))
        normalized["language_profile"] = self._normalize_language_profile(
            normalized.get("language_profile"),
            fallback_primary_language=normalized.get("primary_language"),
        )
        normalized["domain_expertise"] = self._normalize_domain_expertise(normalized.get("domain_expertise"))
        normalized["emotional_baseline"] = self._normalize_emotional_baseline(normalized.get("emotional_baseline"))
        normalized["audience_profile"] = self._normalize_audience_profile(normalized.get("audience_profile"))
        normalized["interaction_style"] = self._normalize_interaction_style(normalized.get("interaction_style"))
        normalized["posting_cadence"] = self._normalize_posting_cadence(normalized.get("posting_cadence"))
        normalized["media_habits"] = self._normalize_media_habits(normalized.get("media_habits"))
        normalized["geo_context"] = self._normalize_geo_context(normalized.get("geo_context"))
        normalized["stance_patterns"] = self._normalize_stance_patterns(normalized.get("stance_patterns"))
        normalized["banned_phrases"] = _as_string_list(normalized.get("banned_phrases"))

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

    def _normalize_topic_clusters(self, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else ([value] if value else [])
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                topic = clean_text(str(item.get("topic") or item.get("name") or ""))
                evidence_terms = _as_string_list(
                    item.get("evidence_terms") or item.get("evidence") or item.get("keywords")
                )
                frequency = clean_text(str(item.get("frequency") or "moderate")).lower() or "moderate"
            else:
                topic = clean_text(str(item))
                evidence_terms = []
                frequency = "moderate"
            if not topic:
                continue
            normalized_items.append(
                {
                    "topic": topic,
                    "evidence_terms": evidence_terms,
                    "frequency": frequency,
                }
            )
        return normalized_items

    def _normalize_writing_patterns(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            source = value
        elif isinstance(value, list):
            source = {"patterns": _as_string_list(value)}
        elif value:
            source = {"patterns": [clean_text(str(value))]}
        else:
            source = {}

        return {
            "avg_sentence_length": clean_text(
                str(
                    source.get("avg_sentence_length")
                    or self._coerce_sentence_length(source.get("average_length") or source.get("avg_length"))
                    or "medium"
                )
            ).lower()
            or "medium",
            "punctuation_habits": _as_string_list(
                source.get("punctuation_habits") or source.get("punctuation") or source.get("patterns")
            ),
            "paragraph_structure": clean_text(
                str(source.get("paragraph_structure") or source.get("structure") or "single-shot")
            )
            or "single-shot",
            "code_switching_style": clean_text(
                str(
                    source.get("code_switching_style")
                    or source.get("code_switching")
                    or source.get("language_notes")
                    or ""
                )
            ),
            "emoji_usage": (
                clean_text(
                    str(source.get("emoji_usage") or self._coerce_emoji_usage(source.get("emoji_ratio")) or "none")
                ).lower()
                or "none"
            ),
        }

    def _normalize_language_profile(
        self,
        value: Any,
        *,
        fallback_primary_language: Any = None,
    ) -> dict[str, Any]:
        raw = value
        if not isinstance(raw, dict):
            raw = {}

        primary_language = (
            clean_text(
                str(raw.get("primary_language") or raw.get("primary") or fallback_primary_language or "unknown")
            ).lower()
            or "unknown"
        )
        secondary_languages = [
            clean_text(language).lower()
            for language in _as_string_list(raw.get("secondary_languages") or raw.get("secondary"))
            if clean_text(language)
        ]
        mixing_pattern = (
            clean_text(
                str(raw.get("mixing_pattern") or raw.get("mix") or raw.get("code_switch_style") or "none")
            ).lower()
            or "none"
        )
        mixing_notes = clean_text(
            str(raw.get("mixing_notes") or raw.get("notes") or raw.get("code_switching_style") or "")
        )

        return {
            "primary_language": primary_language,
            "secondary_languages": secondary_languages,
            "mixing_pattern": mixing_pattern,
            "mixing_notes": mixing_notes,
        }

    def _normalize_domain_expertise(self, value: Any) -> list[dict[str, Any]]:
        items = value if isinstance(value, list) else ([value] if value else [])
        normalized_items: list[dict[str, Any]] = []
        for item in items:
            if isinstance(item, dict):
                domain = clean_text(str(item.get("domain") or item.get("industry") or item.get("topic") or ""))
                depth = clean_text(str(item.get("depth") or item.get("level") or "unknown")).lower() or "unknown"
                jargon_examples = _as_string_list(
                    item.get("jargon_examples") or item.get("jargon") or item.get("examples")
                )
            else:
                domain = clean_text(str(item))
                depth = "unknown"
                jargon_examples = []
            if not domain:
                continue
            normalized_items.append(
                {
                    "domain": domain,
                    "depth": depth,
                    "jargon_examples": jargon_examples,
                }
            )
        return normalized_items

    def _normalize_emotional_baseline(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "default_valence": clean_text(
                str(raw.get("default_valence") or raw.get("valence") or raw.get("dominant") or "neutral")
            ).lower()
            or "neutral",
            "intensity": clean_text(str(raw.get("intensity") or "moderate")).lower() or "moderate",
            "sarcasm_level": clean_text(str(raw.get("sarcasm_level") or raw.get("sarcasm") or "none")).lower()
            or "none",
            "humor_style": clean_text(str(raw.get("humor_style") or raw.get("humor") or "")),
        }

    def _normalize_audience_profile(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "primary_audience": clean_text(str(raw.get("primary_audience") or raw.get("type") or "unknown"))
            or "unknown",
            "assumed_knowledge": _as_string_list(raw.get("assumed_knowledge") or raw.get("knowledge")),
            "formality": clean_text(str(raw.get("formality") or "casual")).lower() or "casual",
        }

    def _normalize_interaction_style(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "original_post_tone": clean_text(
                str(raw.get("original_post_tone") or raw.get("original_tone") or "unknown")
            )
            or "unknown",
            "reply_tone": clean_text(str(raw.get("reply_tone") or "")),
            "quote_tone": clean_text(str(raw.get("quote_tone") or "")),
            "engagement_triggers": _as_string_list(
                raw.get("engagement_triggers") or raw.get("triggers") or raw.get("topics")
            ),
        }

    def _normalize_posting_cadence(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        avg_daily_tweets = self._coerce_float(raw.get("avg_daily_tweets"), default=0.0)
        active_windows = self._coerce_int_list(raw.get("active_windows_utc") or raw.get("active_hours"))
        posting_style = clean_text(str(raw.get("posting_style") or raw.get("style") or "steady")).lower() or "steady"
        preferred_post_length = (
            clean_text(str(raw.get("preferred_post_length") or raw.get("length_preference") or "medium")).lower()
            or "medium"
        )
        return {
            "avg_daily_tweets": avg_daily_tweets,
            "posting_style": posting_style,
            "preferred_post_length": preferred_post_length,
            "active_windows_utc": active_windows,
        }

    def _normalize_media_habits(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "text_only_ratio": self._coerce_float(raw.get("text_only_ratio"), default=0.0),
            "link_ratio": self._coerce_float(raw.get("link_ratio"), default=0.0),
            "media_attachment_ratio": self._coerce_float(raw.get("media_attachment_ratio"), default=0.0),
            "dominant_format": (
                clean_text(str(raw.get("dominant_format") or raw.get("format") or "text-only")).lower() or "text-only"
            ),
            "notes": clean_text(str(raw.get("notes") or "")),
        }

    def _normalize_geo_context(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "declared_location": clean_text(
                str(raw.get("declared_location") or raw.get("location") or raw.get("declared") or "")
            ),
            "region_hint": clean_text(str(raw.get("region_hint") or raw.get("region") or "unknown")).lower()
            or "unknown",
            "timezone_hint": (
                clean_text(str(raw.get("timezone_hint") or raw.get("timezone") or raw.get("tz") or "unknown"))
                or "unknown"
            ),
            "confidence": clean_text(str(raw.get("confidence") or "low")).lower() or "low",
            "notes": clean_text(str(raw.get("notes") or raw.get("rationale") or "")),
        }

    def _normalize_stance_patterns(self, value: Any) -> dict[str, Any]:
        raw = value if isinstance(value, dict) else {}
        return {
            "hot_take_style": clean_text(str(raw.get("hot_take_style") or raw.get("hot_take") or "mixed")).lower()
            or "mixed",
            "controversy_posture": clean_text(
                str(raw.get("controversy_posture") or raw.get("controversy") or "mixed")
            ).lower()
            or "mixed",
            "endorsement_style": clean_text(
                str(raw.get("endorsement_style") or raw.get("endorsement") or "selective")
            ).lower()
            or "selective",
            "notes": clean_text(str(raw.get("notes") or raw.get("rationale") or "")),
        }

    def _coerce_sentence_length(self, value: Any) -> str | None:
        if isinstance(value, str):
            normalized = clean_text(value).lower()
            if normalized in {"short", "medium", "long"}:
                return normalized
            try:
                value = float(normalized)
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            if value <= 80:
                return "short"
            if value <= 180:
                return "medium"
            return "long"
        return None

    def _coerce_emoji_usage(self, value: Any) -> str | None:
        if isinstance(value, str):
            normalized = clean_text(value).lower()
            if normalized in {"none", "light", "heavy"}:
                return normalized
            try:
                value = float(normalized)
            except ValueError:
                return None
        if isinstance(value, (int, float)):
            if value <= 0:
                return "none"
            if value < 0.08:
                return "light"
            return "heavy"
        return None

    def _coerce_float(self, value: Any, *, default: float) -> float:
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return default

    def _coerce_int_list(self, value: Any) -> list[int]:
        if not isinstance(value, list):
            return []
        results: list[int] = []
        for item in value:
            try:
                results.append(int(item))
            except (TypeError, ValueError):
                continue
        return results

    def _persona_language_guidance(self, persona: dict[str, Any]) -> str:
        language_profile = self._normalize_language_profile(persona.get("language_profile"))
        primary_language = language_profile["primary_language"]
        if primary_language == "unknown":
            return (
                "Match the user's requested language. "
                "If the prompt does not specify one, stay close to the persona's historical language texture."
            )

        guidance = f"Default to {primary_language}"
        secondary_languages = language_profile["secondary_languages"]
        if secondary_languages:
            guidance += f", with optional support from {', '.join(secondary_languages[:2])}"

        mixing_pattern = language_profile["mixing_pattern"]
        if mixing_pattern != "none":
            guidance += f". Mixing pattern: {mixing_pattern}"
        else:
            guidance += "."

        mixing_notes = language_profile["mixing_notes"]
        if mixing_notes:
            guidance += f" Notes: {mixing_notes}"
        return guidance

    def _persona_audience_formality(self, persona: dict[str, Any]) -> str:
        audience_profile = persona.get("audience_profile")
        if not isinstance(audience_profile, dict):
            return "casual"
        return clean_text(str(audience_profile.get("formality") or "casual")).lower() or "casual"

    def _persona_sarcasm_level(self, persona: dict[str, Any]) -> str:
        emotional_baseline = persona.get("emotional_baseline")
        if not isinstance(emotional_baseline, dict):
            return "none"
        return clean_text(str(emotional_baseline.get("sarcasm_level") or "none")).lower() or "none"

    def _draft_sounds_earnest(self, candidate_text: str) -> bool:
        lowered_text = candidate_text.lower()
        if any(marker in lowered_text for marker in SARCASM_LITERAL_MARKERS):
            return False
        if any(pattern.search(candidate_text) for pattern in SARCASM_REGEX_PATTERNS):
            return False
        return True

    def _draft_is_link_forward(self, candidate_text: str) -> bool:
        lowered_text = candidate_text.lower()
        if "http://" in lowered_text or "https://" in lowered_text:
            return True
        return any(marker in lowered_text or marker in candidate_text for marker in LINK_FORWARD_MARKERS)

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
                'persona_version must always be "v1".',
                "Keep author_summary to 3 sentences max.",
                "voice_traits should be 4 to 8 short traits.",
                "topic_clusters should be 3 to 6 clusters with topic, evidence_terms, and frequency.",
                "writing_patterns must be a structured object with avg_sentence_length, punctuation_habits, "
                "paragraph_structure, code_switching_style, and emoji_usage.",
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
                "language_profile must identify the primary language using ISO 639-1 when possible and describe "
                "code-switching patterns with concrete evidence from the tweets.",
                "domain_expertise should list 1 to 3 domains with depth level and jargon_examples.",
                "emotional_baseline should capture default_valence, intensity, sarcasm_level, and humor_style.",
                "audience_profile should infer primary_audience, assumed_knowledge, and formality.",
                "interaction_style should differentiate original posts, replies, and quote tweets, and list "
                "engagement_triggers.",
                "posting_cadence should use avg_daily_tweets, active_windows_utc, and posting_style to describe "
                "whether this author is bursty, steady, or sporadic, and infer preferred_post_length.",
                "media_habits should capture text_only_ratio, link_ratio, media_attachment_ratio, dominant_format, "
                "and notes. Use only tweet evidence; do not invent off-platform habits.",
                "geo_context should infer only coarse location or timezone hints from profile.location and UTC "
                "posting windows. Keep confidence conservative and do not invent exact residence, travel, or "
                "event attendance.",
                "stance_patterns should summarize the author's usual hot-take style, controversy posture, and "
                "endorsement style based on observable posts. Do not invent unsupported beliefs or affiliations.",
                "banned_phrases should list internet cliches or phrases this author would not naturally use.",
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
        writing_patterns = self._normalize_writing_patterns(persona.get("writing_patterns"))
        language_profile = self._normalize_language_profile(persona.get("language_profile"))
        emotional_baseline = self._normalize_emotional_baseline(persona.get("emotional_baseline"))
        audience_profile = self._normalize_audience_profile(persona.get("audience_profile"))
        interaction_style = self._normalize_interaction_style(persona.get("interaction_style"))
        posting_cadence = self._normalize_posting_cadence(persona.get("posting_cadence"))
        media_habits = self._normalize_media_habits(persona.get("media_habits"))
        geo_context = self._normalize_geo_context(persona.get("geo_context"))
        stance_patterns = self._normalize_stance_patterns(persona.get("stance_patterns"))

        language_mode = prompt_language_mode(prompt)
        full_chinese_mode = language_mode == "full_chinese"
        allowed_english_tokens_set = (
            self._allowed_english_tokens_for_full_chinese_prompt(
                prompt=prompt,
                theme_keywords=theme_keywords,
            )
            if full_chinese_mode
            else set()
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
            "Use geo_context only as soft localization texture when it is relevant to the topic.",
            "Do not invent precise local presence, local time, or event attendance beyond what geo_context supports.",
            "Keep the draft's hot-take, controversy, and endorsement posture aligned with stance_patterns. "
            "If the user prompt asks for a stronger stance, follow the prompt while staying as close as possible "
            "to the persona's normal posture.",
        ]
        if full_chinese_mode:
            drafting_rules.append(
                "Full-Chinese mode is required: keep the draft in Chinese. "
                "Use English only for exact tokens that already exist in user_prompt/theme_keywords."
            )
        elif language_mode == "english_or_bilingual":
            drafting_rules.append(
                "The user explicitly asked for English or bilingual output. Follow that first, "
                "while keeping the persona's natural code-switching texture."
            )
        else:
            drafting_rules.append(
                "When the prompt does not force a language, default to the persona's primary language profile."
            )
        if posting_cadence["posting_style"] == "burst-poster" or posting_cadence["preferred_post_length"] == "short":
            drafting_rules.append(
                "This persona posts in short bursts. Prefer compressed, single-point drafts over complete arguments."
            )
        if media_habits["dominant_format"] == "text-only":
            drafting_rules.append(
                "This persona is mostly text-only. Do not add links or image-style framing unless the prompt needs it."
            )
        elif media_habits["dominant_format"] == "link-led":
            drafting_rules.append(
                "This persona often uses links. Reference a source naturally if needed, but do not force a real URL."
            )
        elif media_habits["dominant_format"] == "media-led":
            drafting_rules.append(
                "This persona often posts around media attachments. A short caption-like draft is acceptable."
            )

        if full_chinese_mode:
            language_constraint = "Full-Chinese only (unless exact user-provided English tokens are necessary)."
        elif language_mode == "english_or_bilingual":
            language_constraint = (
                "Follow the user's explicit English or bilingual request first, "
                "while keeping the persona's natural language texture."
            )
        else:
            language_constraint = self._persona_language_guidance(persona)
        return {
            "persona": persona,
            "style_brief": {
                "author_summary": clean_text(str(persona.get("author_summary") or "")),
                "voice_traits": _as_string_list(persona.get("voice_traits")),
                "lexical_markers": _as_string_list(persona.get("lexical_markers"))[:20],
                "do_not_sound_like": _as_string_list(persona.get("do_not_sound_like")),
                "writing_patterns": writing_patterns,
                "language_profile": language_profile,
                "emotional_baseline": emotional_baseline,
                "audience_profile": audience_profile,
                "interaction_style": interaction_style,
                "posting_cadence": posting_cadence,
                "media_habits": media_habits,
                "geo_context": geo_context,
                "stance_patterns": stance_patterns,
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
                "language_mode": language_constraint,
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
