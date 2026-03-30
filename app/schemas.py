from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field, conint, constr


MAX_INGEST_TWEETS = 1000


class ProfileIngestRequest(BaseModel):
    username: constr(strip_whitespace=True, min_length=1)
    max_tweets: conint(gt=0, le=MAX_INGEST_TWEETS)


class ProfileSummary(BaseModel):
    id: str
    username: str
    name: str
    description: str = ""
    location: str = ""
    profile_url: str = ""
    followers_count: int
    following_count: int
    tweet_count: int
    verified: bool
    last_ingested_at: str


class IngestResponse(BaseModel):
    username: str
    user_id: str
    fetched_tweet_count: int
    source_original_tweet_count: int
    persona_snapshot_id: int
    ingested_at: str
    profile: ProfileSummary
    persona: dict[str, Any]


class ProfileResponse(BaseModel):
    profile: ProfileSummary
    stored_tweet_count: int
    latest_persona_snapshot: Optional[dict[str, Any]] = None


class DraftGenerateRequest(BaseModel):
    username: constr(strip_whitespace=True, min_length=1)
    prompt: constr(strip_whitespace=True, min_length=3)
    draft_count: conint(gt=0, le=10) = 5


class DraftItem(BaseModel):
    text: str
    tone_tags: list[str] = Field(default_factory=list)
    rationale: str = ""


class DraftCandidateEvaluation(BaseModel):
    text: str
    tone_tags: list[str] = Field(default_factory=list)
    rationale: str = ""
    rule_score: float = 0.0
    llm_score: float = 0.0
    final_score: float = 0.0
    passed: bool = False
    rule_issues: list[str] = Field(default_factory=list)
    rule_strengths: list[str] = Field(default_factory=list)
    llm_verdict: str = ""
    llm_issues: list[str] = Field(default_factory=list)
    llm_strengths: list[str] = Field(default_factory=list)
    must_fix: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)


class DraftAttemptResult(BaseModel):
    attempt: int
    candidates: list[DraftCandidateEvaluation] = Field(default_factory=list)
    best_score: float = 0.0
    target_score_met: bool = False


class DraftGenerateResponse(BaseModel):
    username: str
    prompt: str
    persona_snapshot_id: int
    drafts: list[DraftItem]
    theme_keywords: list[str] = Field(default_factory=list)
    theme_top_keywords: list[str] = Field(default_factory=list)
    matched_theme_tweets: list[dict[str, Any]] = Field(default_factory=list)
    best_score: float = 0.0
    target_score: float = 0.0
    target_score_met: bool = False
    attempt_count: int = 0
    attempts: list[DraftAttemptResult] = Field(default_factory=list)
    evaluation: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class PersonaOutput(BaseModel):
    persona_version: str = "v1"
    author_summary: str
    voice_traits: list[str]
    topic_clusters: list[dict[str, Any]]
    writing_patterns: dict[str, Any]
    lexical_markers: list[str]
    do_not_sound_like: list[str]
    cta_style: str
    generation_guardrails: dict[str, list[str]] = Field(default_factory=dict)
    risk_notes: list[str]


class DraftsOutput(BaseModel):
    drafts: list[DraftItem]
