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


class TopicCluster(BaseModel):
    topic: str = ""
    evidence_terms: list[str] = Field(default_factory=list)
    frequency: str = "moderate"


class WritingPatterns(BaseModel):
    avg_sentence_length: str = "medium"
    punctuation_habits: list[str] = Field(default_factory=list)
    paragraph_structure: str = "single-shot"
    code_switching_style: str = ""
    emoji_usage: str = "none"


class LanguageProfile(BaseModel):
    primary_language: str = "unknown"
    secondary_languages: list[str] = Field(default_factory=list)
    mixing_pattern: str = "none"
    mixing_notes: str = ""


class DomainExpertise(BaseModel):
    domain: str = ""
    depth: str = "unknown"
    jargon_examples: list[str] = Field(default_factory=list)


class EmotionalBaseline(BaseModel):
    default_valence: str = "neutral"
    intensity: str = "moderate"
    sarcasm_level: str = "none"
    humor_style: str = ""


class AudienceProfile(BaseModel):
    primary_audience: str = "unknown"
    assumed_knowledge: list[str] = Field(default_factory=list)
    formality: str = "casual"


class InteractionStyle(BaseModel):
    original_post_tone: str = "unknown"
    reply_tone: str = ""
    quote_tone: str = ""
    engagement_triggers: list[str] = Field(default_factory=list)


class PostingCadence(BaseModel):
    avg_daily_tweets: float = 0.0
    posting_style: str = "steady"
    preferred_post_length: str = "medium"
    active_windows_utc: list[int] = Field(default_factory=list)


class MediaHabits(BaseModel):
    text_only_ratio: float = 0.0
    link_ratio: float = 0.0
    media_attachment_ratio: float = 0.0
    dominant_format: str = "text-only"
    notes: str = ""


class GeoContext(BaseModel):
    declared_location: str = ""
    region_hint: str = "unknown"
    timezone_hint: str = "unknown"
    confidence: str = "low"
    notes: str = ""


class StancePatterns(BaseModel):
    hot_take_style: str = "mixed"
    controversy_posture: str = "mixed"
    endorsement_style: str = "selective"
    notes: str = ""


class VoiceSignal(BaseModel):
    trait: str = ""
    evidence: str = ""


class SignaturePattern(BaseModel):
    pattern: str = ""
    instruction: str = ""
    evidence: str = ""


class LexicalMarkerDetail(BaseModel):
    marker: str = ""
    usage: str = ""
    frequency: str = "medium"


class GuardrailExample(BaseModel):
    instruction: str = ""
    positive_example: str = ""
    negative_example: str = ""


class GenerationGuardrailsDetailed(BaseModel):
    preferred_openings: list[GuardrailExample] = Field(default_factory=list)
    preferred_formats: list[GuardrailExample] = Field(default_factory=list)
    compression_rules: list[GuardrailExample] = Field(default_factory=list)
    anti_patterns: list[GuardrailExample] = Field(default_factory=list)
    language_notes: list[GuardrailExample] = Field(default_factory=list)


class PersonaOutput(BaseModel):
    persona_version: str = "v1"
    author_summary: str
    voice_traits: list[str]
    voice_signals: list[VoiceSignal] = Field(default_factory=list)
    signature_patterns: list[SignaturePattern] = Field(default_factory=list)
    topic_clusters: list[TopicCluster] = Field(default_factory=list)
    writing_patterns: WritingPatterns = Field(default_factory=WritingPatterns)
    lexical_markers: list[str]
    lexical_markers_detailed: list[LexicalMarkerDetail] = Field(default_factory=list)
    do_not_sound_like: list[str]
    cta_style: str
    generation_guardrails: dict[str, list[str]] = Field(default_factory=dict)
    generation_guardrails_detailed: GenerationGuardrailsDetailed = Field(default_factory=GenerationGuardrailsDetailed)
    risk_notes: list[str]
    language_profile: LanguageProfile = Field(default_factory=LanguageProfile)
    domain_expertise: list[DomainExpertise] = Field(default_factory=list)
    emotional_baseline: EmotionalBaseline = Field(default_factory=EmotionalBaseline)
    audience_profile: AudienceProfile = Field(default_factory=AudienceProfile)
    interaction_style: InteractionStyle = Field(default_factory=InteractionStyle)
    posting_cadence: PostingCadence = Field(default_factory=PostingCadence)
    media_habits: MediaHabits = Field(default_factory=MediaHabits)
    geo_context: GeoContext = Field(default_factory=GeoContext)
    stance_patterns: StancePatterns = Field(default_factory=StancePatterns)
    banned_phrases: list[str] = Field(default_factory=list)


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


class HotEventItem(BaseModel):
    id: str
    title: str
    summary: str = ""
    title_translated: str = ""
    summary_translated: str = ""
    is_translated: bool = False
    url: str = ""
    source: str = ""
    source_domain: str = ""
    published_at: str = ""
    relative_age_hint: str = ""
    heat_score: float = 0.0
    category: str = ""
    subcategory: str = ""
    content_type: Literal["news", "tweet"] = "news"
    author_handle: str = ""


class HotEventsSourceStatus(BaseModel):
    status: Literal["ok", "error"] = "ok"
    count: int = 0
    error: str = ""


class HotEventsResponse(BaseModel):
    hours: int = 24
    count: int = 0
    items: list[HotEventItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_status: dict[str, HotEventsSourceStatus] = Field(default_factory=dict)
    last_refreshed_at: str = ""
    last_attempted_at: str = ""
    refresh_interval_seconds: int = 3600
    is_stale: bool = False
    refreshing: bool = False
    throttled: bool = False
    next_refresh_available_in_seconds: int = 0
    last_refresh_error: str = ""


class TrendingGenerateRequest(BaseModel):
    username: str = Field(..., strip_whitespace=True, min_length=1)
    event_id: str = ""
    event_payload: dict[str, Any] | None = None
    comment: str = ""
    draft_count: int = Field(3, gt=0, le=10)


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
