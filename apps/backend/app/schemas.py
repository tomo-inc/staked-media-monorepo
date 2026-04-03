from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ProfileIngestRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)


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
    latest_persona_snapshot: dict[str, Any] | None = None


class DraftGenerateRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)
    prompt: str = Field(..., strip_whitespace=True, min_length=3)
    draft_count: int = Field(5, gt=0, le=10)


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


class ContentGenerateRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)
    mode: Literal["A", "B"] = "A"
    idea: str = ""
    direction: str = ""
    domain: str = ""
    topic: str = ""
    keywords: list[str] = Field(default_factory=list)
    tone: str = ""
    draft_count: int = Field(3, gt=0, le=10)


class ContentScoreBreakdown(BaseModel):
    theme_relevance: float = 0.0
    style_similarity: float = 0.0
    publishability: float = 0.0
    final_score: float = 0.0


ContentVariantType = Literal["normal", "expansion", "open"]


class ContentVariantOutput(BaseModel):
    variant: ContentVariantType
    label: str
    drafts: list[DraftItem]
    formatted_drafts: list[str] = Field(default_factory=list)
    score: ContentScoreBreakdown = Field(default_factory=ContentScoreBreakdown)
    target_score_met: bool = False
    retry_count: int = 0
    quality_gate_reason: str = ""
    compensation_used: bool = False
    used_keywords: list[str] = Field(default_factory=list)
    source_facts: list[dict[str, Any]] = Field(default_factory=list)


class ContentGenerateResponse(BaseModel):
    request_id: str
    mode: Literal["A", "B"]
    topic: str
    variants: list[ContentVariantOutput] = Field(default_factory=list)
    recommended_variant: ContentVariantType = "normal"
    drafts: list[DraftItem]
    formatted_drafts: list[str] = Field(default_factory=list)
    score: ContentScoreBreakdown = Field(default_factory=ContentScoreBreakdown)
    target_score_met: bool = False
    quality_gate_met: bool = False
    quality_gate_reason: str = ""
    retry_count: int = 0
    history_match_count: int = 0
    web_enrichment_used: bool = False
    used_keywords: list[str] = Field(default_factory=list)
    web_keywords: list[str] = Field(default_factory=list)
    personal_phrases: list[str] = Field(default_factory=list)
    source_facts: list[dict[str, Any]] = Field(default_factory=list)
    debug_summary: str = ""


class ContentIdeasRequest(BaseModel):
    direction: str = ""
    domain: str = ""
    topic_hint: str = ""
    limit: int = Field(8, gt=0, le=20)


class IdeaItem(BaseModel):
    topic: str
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    source: str = ""
    published_at: str = ""
    url: str = ""


class ContentIdeasResponse(BaseModel):
    ideas: list[IdeaItem] = Field(default_factory=list)
    query: str = ""
    suggested_keywords: list[str] = Field(default_factory=list)


class ExposureAnalyzeRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)
    text: str = Field(..., strip_whitespace=True, min_length=3)
    topic: str = ""
    domain: str = ""


class ExposureAnalyzeResponse(BaseModel):
    hashtags: list[str] = Field(default_factory=list)
    best_posting_windows: list[str] = Field(default_factory=list)
    heat_score: float = 0.0
    heat_label: str = "low"
    reasons: list[str] = Field(default_factory=list)


class WhitelistUsernameRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)


class WhitelistUsernamesResponse(BaseModel):
    usernames: list[str] = Field(default_factory=list)


class ContentDebugRound(BaseModel):
    round_index: int
    final_score: float
    web_enrichment_used: bool
    used_keywords: list[str] = Field(default_factory=list)
    note: str = ""


class ContentDebugVariant(BaseModel):
    variant: ContentVariantType
    rounds: list[ContentDebugRound] = Field(default_factory=list)
    score: ContentScoreBreakdown = Field(default_factory=ContentScoreBreakdown)
    target_score_met: bool = False


class ContentDebugResponse(BaseModel):
    request_id: str
    mode: Literal["A", "B"]
    topic: str
    history_match_count: int
    web_enrichment_used: bool
    rounds: list[ContentDebugRound] = Field(default_factory=list)
    variants: list[ContentDebugVariant] = Field(default_factory=list)
    recommended_variant: ContentVariantType = "normal"
    score: ContentScoreBreakdown = Field(default_factory=ContentScoreBreakdown)
    used_keywords: list[str] = Field(default_factory=list)
    web_keywords: list[str] = Field(default_factory=list)
    source_facts: list[dict[str, Any]] = Field(default_factory=list)
