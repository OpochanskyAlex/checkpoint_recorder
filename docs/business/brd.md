---
doc: BRD
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [logging, management, analytics, alerting, account, discovery, General]
refs:
  - {doc: initial_task_setup, version: 1}
updated: 2026-04-26
tags: [project-docs, brd]
---

# Context

People who track personal metrics — health, fitness, finances, mood — are forced to use multiple dedicated applications, each requiring deliberate context-switching and manual navigation. Telegram is already an active daily-use communication tool for the target audience. The core hypothesis: friction of switching to a dedicated tracking app is the primary driver of tracking abandonment, not lack of motivation. If logging lives inside Telegram, where users already are dozens of times a day, they will maintain tracking habits they otherwise abandon.

This is an educational and portfolio project with no monetization intent. Success is defined by personal learning, a functional live deployment, and demonstrated portfolio value. Target cohort: approximately 10 users, each tracking approximately 10 metrics (~100 active metric time series at steady state).

# Goals

- G1 Reduce personal metric tracking abandonment by embedding logging inside Telegram, eliminating the activation cost of switching to a dedicated app
  - Measured by: tracking retention >40% at 14 days (daily metrics) or 5 periods (per-metric periodicity); data input success rate >85%
- G2 Enable personal self-insight by building a persistent, queryable record of any user-defined metric with on-demand visualization and threshold alerting
  - Measured by: chart feature adoption >25% among active users; alert delivery accuracy >95%
- G3 Protect user privacy and maintain trust by storing only opaque user identifiers and enforcing strict per-user data isolation
  - Measured by: zero cross-user data visibility incidents (100% non-negotiable)
- G4 Deliver a portfolio-quality demonstration of NLP parsing, multi-tenancy, async Telegram bot architecture, and structured observability

# Stakeholders

- SH1 Health tracker (end user) — low-friction daily habit logging, data privacy, clear chart output
- SH2 Expense / resource tracker (end user) — flexible parameter naming, reliable history access
- SH3 Athlete (end user) — compound multi-value entries (e.g., `80kg 5reps`), trend visibility over training cycles
- SH4 Bot Operator / System Owner (solo, AI-agent-assisted) — stable single-instance operation, user data isolation, sustainable operating cost
- SH5 Telegram Platform — infrastructure dependency; no primary concern; source of R-004 (API policy change risk)

# Constraints

- Input channel: exclusively Telegram; no web, mobile, or other interface
- Data model: no predefined metric categories; user defines all dimensions freely on first entry
- Multi-tenancy: one bot instance, multiple users; data isolation is mandatory and non-negotiable
- Budget: solo portfolio project; lightweight, zero-cost-tier hosting preferred
- Privacy: only opaque internal user IDs are stored; Telegram identity fields (name, username, phone) are never persisted
- Data retention: minimum 1 year guaranteed after last interaction; lifetime in practice; no data export mechanism
- Parse failure: ambiguous input must never be silently discarded; manual selection fallback is required
- Periodicity vocabulary: closed set — `daily` and `weekly` only; free-form periodicities are out of scope
- Telegram platform: accepted as the delivery channel; no comparative platform analysis required

# Business Requirements

- R1 [must] @logging System accepts free-text metric data entry without requiring structured commands or predefined categories <- G1
- R2 [must] @logging When a user confirms metric creation via the explicit "Create [typed_name]" inline button (R17), the system prompts for periodicity (`daily` or `weekly`); the metric record and the pending entry are created atomically on periodicity confirmation; neither is stored before confirmation <- G1
- R3 [must] @logging When automatic NLP parsing confidence is insufficient, system presents a ranked list of candidate metrics for manual selection; ambiguous input is never silently discarded <- G1
- R4 [must] @analytics System maintains an immutable per-metric entry history and generates on-demand time-series chart images delivered in Telegram <- G2
- R5 [must] @alerting System supports user-defined one-shot threshold alerts; alert fires once when the condition is met and requires explicit user re-arming to fire again <- G2
- R6 [must] @management System allows users to view their metric catalog with activity status, archive/reactivate individual metrics, and permanently delete a metric with all associated data <- G1, G2
- R7 [must] @account System stores only an opaque internal identifier per user; no Telegram name, username, or phone number is persisted <- G3
- R8 [must] @General Per-user data isolation is enforced at the persistence layer; no query or response may surface another user's data <- G3
- R9 [must] @account User data is retained for a minimum of 1 year after last interaction; account deletion initiates a 72-hour grace period before irreversible permanent purge <- G3
- R10 [must] @discovery System responds to `/help` with a complete, static list of all available commands and their descriptions; response is available without registration <- G1
- R11 [must] @account Every new user registration is accompanied by an onboarding message stating: data retention policy, no-export limitation, verbatim message storage, and one-shot alert behavior <- G3
- R12 [must] @logging @management When a user issues any metric-name-required command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`, or the logging/entry flow) with no metric name argument, the system presents the user's complete metric catalog as inline keyboard buttons ordered by most-recently-recorded entry (descending); metrics with no entries appear last, ordered alphabetically <- G1
- R13 [must] @logging @management When a user supplies a metric name argument that does not exactly match any existing metric but produces at least one fuzzy match (rapidfuzz; threshold defined by SA), the system presents matched metrics as inline keyboard buttons ordered by most-recently-recorded entry <- G1
- R14 [must] @logging @management Inline keyboard buttons presenting metric choices are ordered by the timestamp of the most recent entry for each metric, descending; metrics with no entries appear last, ordered alphabetically by metric name (case-insensitive) <- G1
- R15 [should] @logging @management When matched metrics exceed 4, the system displays only the top 4 matches plus a "Show all fits" button; pressing "Show all fits" replaces the message with an inline keyboard listing all matching metrics (native Telegram client scrolling applies; see Q-FEAT-4 for SA clarification on pagination) <- G1
- R16 [should] @logging @management After a user selects a metric via the inline picker in any metric-name-required command, the system displays the last 3 recorded values for that metric (or fewer if fewer exist, with a "no entries yet" note when count is zero) as context before proceeding with the command; in the logging/entry flow this is additionally followed by a prompt for a new value <- G1, G2
- R17 [must] @logging When the picker in the logging/entry flow finds zero fuzzy matches for a typed metric name, the system presents an explicit "Create [typed_name]" inline button instead of metric choices; pressing it initiates the periodicity selection and creation flow (R2) with the typed name pre-filled <- G1
- R18 [must] @management When the picker in any metric-name-required management command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`) finds zero fuzzy matches for a supplied metric name, the system responds with a "no matching metrics found" message and does not execute the command; no "Create" button is offered <- G1

# User Stories

- [[us-1-log-metric|US1 Log a metric in free text]] <- R1, R2, @logging
- [[us-2-resolve-ambiguous|US2 Resolve an ambiguous entry]] <- R3, @logging
- [[us-3-manage-metrics|US3 Manage metric catalog]] <- R6, @management
- [[us-4-view-charts|US4 View trend charts]] <- R4, @analytics
- [[us-5-set-alerts|US5 Set and manage threshold alerts]] <- R5, @alerting
- [[us-6-manage-account|US6 Manage account]] <- R7, R8, R9, R11, @account
- [[us-7-discover-commands|US7 Discover available commands]] <- R10, @discovery
- [[us-8-metric-picker|US8 Select a metric via inline picker]] <- R12, R13, R14, R15, R16, R17, R18, @logging, @management

# Glossary

- Metric — a named, user-defined tracking dimension with a closed periodicity (`daily` | `weekly`); created explicitly or automatically on first entry for an unrecognized name
- Entry — an immutable record of a single metric data point, storing the verbatim original message text (`raw_input`) and numeric value(s); never modified after creation
- ParseAttempt — a disambiguation session created when NLP parsing cannot identify the target metric with sufficient confidence; never silently discarded
- Periodicity — the tracking cadence for a metric: `daily` (one calendar day, 00:00–23:59 UTC) or `weekly` (Monday 00:00 – Sunday 23:59 UTC); closed vocabulary, no other values accepted
- Alert — a user-defined one-shot threshold rule; fires once when an entry value crosses the defined condition (above/below); must be explicitly re-armed to fire again
- Compound entry — a multi-value entry recording multiple named dimensions in a single submission (e.g., `80kg 5reps`)
- InternalUser — the system's representation of a registered user, keyed to an opaque internal identifier; no Telegram identity fields stored
- Active metric — a metric with at least 4 entries out of the last 5 periods of its own periodicity
- Active user — a user with at least one active metric
- Smart Metric Picker — an inline keyboard interaction that surfaces a user's metric catalog (full or fuzzy-filtered) as pressable buttons, ordered by recency, triggered when a metric-name-required command is issued without an exact metric name match
- Fuzzy match — a metric name whose normalized edit-distance similarity score (computed by rapidfuzz) meets or exceeds a threshold defined by SA; at least one match must exist for the picker to show filtered results
- Recency order — metrics sorted descending by the timestamp of their most recent entry; metrics with no entries are sorted alphabetically after all metrics that have entries

# Uncertainty Register

| ID | Type | Item | Impact-if-false | Validation plan |
|---|---|---|---|---|
| U1 | hypothesis | G1 — Core friction hypothesis: that switching-to-app friction (not lack of motivation) is the primary driver of tracking abandonment; accepted as project premise without external research | Product solves the wrong problem; retention target unreachable regardless of implementation quality | Monitor tracking retention in production; if below 40% after 14 days, reconsider hypothesis |
| U2 | assumption | R1, R6 — Users will name their own metrics consistently across sessions; near-duplicate detection (e.g., `mood` vs `Mood`) is not implemented | History fragmentation across duplicate metrics; core value proposition undermined | Inform users at onboarding; consider fuzzy deduplication in a future iteration |

# Open Questions

(None — all questions resolved as of source v0.6.)

<!-- smart-metric-picker feature addition — 2026-04-28 -->

- Q1 [SA] R3 (ParseAttempt) and R12/R13 (smart-metric-picker) both result in inline metric-button presentations but are triggered by different conditions. Does the SA define a single shared ConversationState for "awaiting metric selection" used by both paths, or two independent FSM branches? Impact: affects timeout behavior, deferral behavior, and whether a user in a ParseAttempt session sees the same UX as a user who issued a bare command.
- Q2 [SA] After metric selection via the picker in the logging/entry flow (R16), the system asks for a new value. Is this "ask for new value" a new ConversationState node (e.g., AwaitingNewValue) or does it re-enter the existing entry submission state? Impact: FSM node count and whether existing timeout logic applies.
- Q3 [SA] What is the exact rapidfuzz similarity threshold and scoring function (ratio, partial_ratio, token_sort_ratio) that defines a qualifying "fuzzy match" (R13)? Below this threshold, the picker does not fire and R2 auto-create or a no-match error applies instead. This threshold must be specified in the SRS to make R13 testable.
- Q4 [SA] R15 specifies a "scrollable inline-button list" for "Show all fits". Telegram inline keyboards are scrollable only by the Telegram client when the list is long. SA should confirm whether "scrollable" means relying on native Telegram UI scrolling (no implementation change) or requires pagination buttons. If pagination is required, R15 implementation complexity increases.
- ~~Q5 [stakeholder] R16 shows last 3 values after metric selection in the logging/entry flow. Should the same last-3-values context also appear when the picker resolves a metric for non-logging commands (`/chart`, `/metric_archive`, etc.), or is it exclusive to the logging/entry flow?~~ **Resolved 2026-04-28:** Last-3-values context applies to ALL metric-name-required commands. R16 updated accordingly.
- ~~Q6 [stakeholder] When fuzzy matching yields zero results in the logging/entry flow (R13, zero-match case), should the system proceed directly to R2 auto-create, or should it first display a confirm-before-create prompt asking the user if they want to create a new metric with the typed name?~~ **Resolved 2026-04-28:** Neither. System presents an explicit "Create [typed_name]" inline button; R2 does not fire silently. R17 added.

# Out of Scope

- ML-based trend inference or predictions (requires labelled training data and model infrastructure not available at portfolio scope)
- Multi-language NLP support (adds parsing complexity disproportionate to the initial cohort, assumed single-language)
- Voice input (requires speech-to-text API; not aligned with keyboard-first Telegram usage)
- External API integrations (fitness wearables, financial platforms)
- Data export to external systems (explicitly accepted risk; users informed at onboarding)
- Commercial analytics or monetization

<!-- custom section -->

# Success Metrics

Defined by stakeholder. Measurement requires the Observability Collector to emit the events specified in the architecture.

| Metric | Definition | Target | Measurement |
|---|---|---|---|
| Tracking retention | % of active users still logging after 14 days (daily metrics) or 5 periods (per metric's periodicity) | >40% | Count active users with entries in days 8–14 (or ≥4 of last 5 periods) |
| Data input success rate | % of free-text entries correctly parsed and stored without user correction | >85% | Parsed entries / total entries received |
| Chart feature adoption | % of active users who request at least one chart | >25% | Chart command invocations / active users |
| Alert delivery accuracy | Threshold alerts fired and delivered correctly vs. expected | >95% | Manual or event-log review |
| User data isolation integrity | Zero incidents of cross-user data visibility | 100% (non-negotiable) | Integration test audit; per-query isolation enforcement |

<!-- custom section -->

# Risks

Risks accepted by stakeholder are marked **[Accepted]**.

| ID | Risk | Impact | Probability | Mitigation |
|---|---|---|---|---|
| RISK1 | Core friction hypothesis is wrong — abandonment driven by motivation, not friction | High — product solves the wrong problem | Low–Medium (accepted as premise) | **[Accepted]** Treated as project premise; if retention falls below 40%, revisit hypothesis |
| RISK2 | Free-text parsing ambiguity causes incorrect data storage in immutable entries | High — corrupts user history permanently | High — NLP inherently ambiguous | Manual selection fallback (R3); ~15% incorrect entries at 85% parse accuracy remain a risk |
| RISK3 | Parameter name collision / near-duplicates per user fragment history | Medium — fragmented time series | High — users type inconsistently | Near-duplicate detection deferred (U2); mitigated by user-facing guidance at onboarding |
| RISK4 | Telegram API policy change restricts bot behavior | High — full service disruption | Low–Medium | **[Accepted]** Platform dependency with no in-scope mitigation |
| RISK5 | Cross-user data leak due to implementation error | Critical — irreversible trust failure | Low (if implemented correctly) | Per-user isolation enforced at persistence layer; 100% target (R8) |
| RISK6 | No data export → total data loss on account deletion | Medium — user data unrecoverable | Medium | **[Accepted]** Users informed at onboarding; 1-year retention + 72-hour grace period provide partial mitigation |
| RISK7 | GDPR / data privacy exposure from `raw_input` storage | Medium — personal content in verbatim messages | Low–Medium | Primary: only opaque IDs stored (R7); residual: verbatim message text may contain personal content; users informed at onboarding; purged on deletion |
| RISK8 | Single operational owner creates bus-factor risk | Medium — any unavailability halts incident response | Medium (solo project) | **[Accepted]** AI-agent assistance reduces per-task burden; acceptable for portfolio scope |

<!-- custom section -->

# Hypothesis Statement

**Statement accepted by project owner:** "The friction of switching to a dedicated tracking app is the primary driver of tracking abandonment — not lack of motivation."

**Basis:** Personal experience and project intent (educational/portfolio).
**Risk accepted:** If this premise is incorrect, the product may not achieve retention targets. For a portfolio project at this scale, the research cost is judged disproportionate to the risk.
**Residual signal to watch:** If tracking retention falls below the 40% target during live operation, the motivation hypothesis should be reconsidered as an alternative explanation.

<!-- custom section -->

# Decision Log

| ID | Decision | Rationale | Status |
|---|---|---|---|
| D-001 | Project intent: educational/portfolio, no monetization | Stakeholder confirmed | Confirmed |
| D-002 | Privacy by design: store only de-personalized internal IDs (identity fields) | Eliminates GDPR/personal-data risk for identity fields; residual risk from `raw_input` content documented separately | Confirmed |
| D-003 | Accept friction hypothesis as project premise; no research validation planned | Portfolio scope makes research cost disproportionate | Confirmed |
| D-004 | Accept no-export risk on behalf of users | Stakeholder decision; users informed at onboarding | Confirmed |
| D-005 | Single person + AI agents as operational owner | Stakeholder response to Q-004 | Confirmed |
| D-006 | Parse failure uses manual selection fallback | Preserves data integrity over silent failure | Confirmed |
| D-007 | Data retention: 1 year guaranteed after last interaction; lifetime in practice | Stakeholder decision | Confirmed |
| D-008 | Metric periodicity set at creation time by user from closed vocabulary (daily \| weekly) | Closed vocabulary required for MetricActivityStatus computation | Confirmed |
| D-009 | `raw_input` retained as known residual personal data risk; no scrubbing at portfolio scope | Functionally required for disambiguation and audit tracing; purged on deletion | Confirmed |
| D-010 | Account deletion includes a 72-hour grace period; after that, permanent and irreversible deletion | Stakeholder decision; provides restoration window | Confirmed |
| D-011 | `/help` command is a required feature for in-context discoverability | Without self-service documentation, users unfamiliar with commands abandon rather than experiment | Confirmed |
| D-012 | Alert lifecycle is one-shot: after firing, status = Triggered; user must explicitly re-arm | Stakeholder decision | Confirmed |
| D-013 | ParseAttempt failure or timeout transitions to Deferred, not terminal Expired; user may return later | Stakeholder decision: same philosophy as one-shot alerts — user can come back | Confirmed |

<!-- custom section -->

# Traceability

| Business Goal | Linked Metric | Key Risk |
|---|---|---|
| G1 Reduce tracking abandonment | Tracking retention >40%; data input success rate >85% | RISK1 (friction hypothesis); RISK2 (parse failures) |
| G2 Enable self-insight | Chart adoption >25%; alert accuracy >95% | RISK6 (no export accepted); RISK2 (incorrect immutable entries) |
| G3 User data privacy and trust | Cross-user isolation 100% | RISK5 (cross-user leak); RISK7 (raw_input personal data) |
| G4 Portfolio demonstration | All G1–G3 metrics achieved simultaneously | RISK8 (single operator bus factor) |
