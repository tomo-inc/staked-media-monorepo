# Product Requirements Document (Detailed)

Date: 2026-03-27  
Version: v1.0 Detailed  
Product: X/Twitter Copilot Plugin

## 1. Executive Summary
This product is a browser plugin for X that helps users create posts in their own voice with lower effort and faster publish time.

The product combines:
- personalization from user-approved writing signals,
- guided ideation when users do not know what to post,
- multi-variant draft generation,
- pre-publish safety checks,
- manual handoff to X composer (no auto-posting).

Commercial model:
- Early launch warm-up: free usage.
- Monetized stage: free tier + Pro subscription.

## 2. Product Goals
- Reduce median time-to-first-draft.
- Increase accepted-draft rate.
- Improve perceived "sounds-like-me" quality.
- Maintain privacy-first data handling and explicit user consent.
- Keep safety/legal risk inside defined operational guardrails.
- Achieve sustainable unit economics under observed usage patterns.

## 3. Non-Goals (MVP)
- Fully automatic posting.
- Multi-account bulk campaign publishing.
- Enterprise team workflows.
- Native mobile app as primary experience.
- DM ingestion or private-message analysis.

## 4. Target Users
Primary:
- Individual creators and operators posting frequently on X.

Secondary:
- Founders, indie builders, and community operators who need consistent posting cadence.

## 5. Core User Journeys
### Journey A: "I know what to say, help me write it better"
1. User opens plugin on X.
2. User inputs intent/topic.
3. System asks clarifying questions when confidence is low.
4. System returns three candidate drafts.
5. User accepts/edits/regenerates and manually publishes.

### Journey B: "I want to post but have no topic"
1. User requests topic suggestions.
2. System returns up to 10 ranked ideas with confidence labels.
3. User picks one topic.
4. System generates three drafts and user publishes manually.

## 6. Scope
### In Scope
- X OAuth account linking.
- Voice profile setup from user-approved content.
- Draft generation and revision loop.
- Topic suggestion with source confidence labels.
- Safety risk checks with block/warn flows.
- Consent logging, revocation, and data controls.
- Basic experimentation and KPI instrumentation.

### Out of Scope
- Auto-posting.
- Multi-account scheduling/publishing.
- Team seat management and approvals.
- Cross-platform posting integrations.

## 7. Functional Requirements
### FR-1 Authentication and Authorization
- Must use X OAuth 2.0 with PKCE.
- Minimum scopes: `tweet.read`, `users.read`.
- Optional scopes must be off by default and user-enabled.
- User revocation must be supported from product settings and X app access settings.

### FR-2 Personalization and Cold Start
- Tier users by available historical posts:
  - Tier A: >= 200 posts.
  - Tier B: 50-199 posts.
  - Tier C: 10-49 posts.
  - Tier D: < 10 posts.
- Tier C/D require guided onboarding and should not overclaim style confidence.

### FR-3 Draft Generation
- Generate three variants per request.
- Ask up to three clarification questions when needed.
- Expose actions: accept, edit, regenerate, reject.
- Show style-confidence indicator.

### FR-4 Topic Suggestions
- Return up to 10 suggestions.
- Rank by relevance, recency, novelty, and style fit.
- Show source confidence label:
  - verified
  - emerging/unconfirmed

### FR-5 Safety and Abuse Controls
- Run pre-publish risk checks for:
  - defamation/targeted harassment,
  - copyright-heavy reproduction,
  - high-risk financial certainty claims.
- Decision thresholds:
  - risk >= 0.85: block and regenerate guidance.
  - risk 0.60-0.84: warning and explicit confirmation.
  - risk < 0.60: normal flow.
- No unattended auto-posting.
- Enforce rate limits and anti-abuse throttles.

### FR-6 Consent and Data Control
- Data collection must be minimum necessary by default.
- Optional context permissions must require explicit opt-in.
- Consent log must be append-only and auditable.
- Revocation must lock access quickly and stop async processing.

### FR-7 Composer Handoff
- Draft-to-composer handoff target: <= 2.0s p95.
- Final publish action must always be user-confirmed.

## 8. Non-Functional Requirements
Performance:
- First draft response target: <= 4s p95.
- Composer handoff: <= 2s p95.

Reliability:
- Monthly availability target: >= 99.5%.
- Graceful degradation under API throttling/outage.

Security:
- TLS in transit, encryption at rest.
- Secret rotation and least-privilege access.

Privacy/Compliance:
- DSAR workflow for access/delete/correct requests.
- Consent records retained for audit needs.

## 9. Data Policy
Collected by default:
- User-approved X profile and historical post signals.
- In-product interaction events (accept/edit/reject/regenerate).

Optional:
- Additional preference scopes when user enables them.

Explicitly not collected:
- DMs,
- account credentials/passwords,
- off-X browsing history by default.

## 10. Pricing and Rate Governance (Final)
### Phase A: Early Launch Warm-Up
- Free tier only.
- Limit: `5 drafts/day`.

### Phase B: Monetized Stage
- Free:
  - `5 drafts/month`.
- Pro:
  - `$9.9/month`.
  - `100 drafts/month`.

## 11. Unit Economics Model
Assumptions:
- Per-draft usage cost (LLM + API): `$0.01202`.
- Additional non-usage paid variable cost: `$3.3486/paid-user-month`.

Derived:
- Pro usage-linked cost: `100 * 0.01202 = $1.202`.
- Total paid variable cost: `$1.202 + $3.3486 = $4.5506`.
- Paid contribution margin (CM1): `$9.9 - $4.5506 = $5.3494`.
- Free-user monthly variable cost at 5 drafts/month: `5 * 0.01202 = $0.0601`.

## 12. Profitability and Break-Even Logic
Variable-cost profitability condition:

`5.3494 * P > 0.0601 * F`

Where:
- `P` = paid users,
- `F` = free users.

Equivalent paid-rate threshold:
- `paid_rate > 1.11%` (variable-cost break-even floor only).

Business interpretation:
- `~1%` is not a healthy commercial target.
- Operational target should be materially higher.

## 13. Commercial Targets
Minimum acceptable:
- Free-to-paid conversion >= 3%.

Target band:
- Free-to-paid conversion 3%-5%.

Strong performance:
- Free-to-paid conversion 5%-8%.

Supporting targets:
- Paid month-1 churn <= 12%.
- Draft acceptance rate and WADAC trend must improve week over week in early rollout.

## 14. KPI Framework
Primary product KPI:
- Weekly Accepted Drafts per Active Creator (WADAC).

Core operating KPIs:
- Draft acceptance rate.
- Median time-to-publish.
- Free-to-paid conversion.
- Paid month-1 churn.
- Safety incident rate.
- Legal complaint rate.

## 15. Experimentation Plan
Primary evaluation endpoint:
- CEI (continuous bounded index).

Design baseline:
- User-level randomized evaluation for major feature changes.
- Powered MDE target: 3.0pp CEI at 1,700 analyzable users.
- Primary model: fractional logit.
- Robustness checks: beta regression and quantile treatment effects.

Success interpretation:
- Quality improvements must not come from unsafe behavior or excessive false blocks.

## 16. Rollout Plan
Phase 0 (Build readiness):
- Core drafting flow, safety checks, telemetry, consent controls.

Phase 1 (Warm-up launch):
- Free-only with 5 drafts/day limit.
- Focus on activation, quality, and safety stability.

Phase 2 (Monetization activation):
- Switch to free 5/month + Pro 9.9/month with 100/month.
- Monitor conversion, churn, and abuse.

Phase 3 (Optimization):
- Tune onboarding, personalization confidence, and topic quality.
- Iterate pricing/packaging only if conversion/churn misses targets.

## 17. Risk Register and Mitigations
Risk: low conversion despite positive quality metrics.  
Mitigation: tighten onboarding to first accepted draft and adjust paywall timing.

Risk: quota-value mismatch (too strict or too loose).  
Mitigation: monitor quota utilization distribution and churn monthly.

Risk: platform dependency on X policy changes.  
Mitigation: keep web fallback path drill-ready.

Risk: legal/safety incidents.  
Mitigation: threshold governance, incident response SLA, strict escalation.

## 18. Operational Guardrails
- If conversion stays < 3% for 4 consecutive weeks, freeze expansion work and run conversion-focused sprints.
- If paid month-1 churn > 12%, pause growth pushes and review package-value fit.
- If safety/legal weekly red-line triggers fire, execute immediate brake protocol.

## 19. Decision Rule
Scale-up is allowed only when all are true:
- conversion is sustainably >= 3%,
- churn and safety stay within guardrails,
- CM1 remains positive and stable under real usage.

If these are not met, remain in controlled optimization mode and avoid broad growth spend.
