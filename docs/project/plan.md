---
doc: PLAN
project: checkpoint_recorder
version: 0.1
status: draft
owner: project-manager
reviewed_by: null
score: null
activities: []
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: arch, version: 0.1}
updated: 2026-04-26
tags: [project-docs, plan]
---

# Summary

4-stage delivery plan covering 21 FRs and 17 NFRs across 13 WBS tasks, organized as 4 milestones. Critical path runs T1 → T3 → T5 → T8 → T11 → T12 → T13 (~295k tokens total). All stages have been delivered as of 2026-04-15.

Sizing: **T-shirt + tokens** (both required per task).

T-shirt scale: XS < 1 day · S 1–3 days · M 3–10 days · L 10–30 days · XL > 30 days

Token ranges: XS < 5k · S 5k–20k · M 20k–80k · L 80k–300k · XL > 300k

# Milestones

- M1 Stage 1 — Core Registration and Auto-Parsed Entry — tasks: T1, T2, T3, T4
  Working bot: user can register, log entries end-to-end, create metrics, see /help.
- M2 Stage 2 — Ambiguous Entry, Metric Management, Deferred Categorization — tasks: T5, T6, T7
  Full metric catalog management and ambiguity resolution via ParseAttempt lifecycle.
- M3 Stage 3 — Alerting and Account Lifecycle — tasks: T8, T9, T10
  Threshold alerts with notifications; account deletion with 72h grace period and restoration.
- M4 Stage 4 — Charts, Scheduled Purge, and Observability Completion — tasks: T11, T12, T13
  Complete production system: charts, purge scheduler, load verification, all NFRs measurable.

# Work Breakdown Structure

## T1 Infrastructure and project scaffold
- size: XS
- tokens: ~8k
- confidence: high
- owner: Operator
- depends_on: []
- done: Alembic migration 001 applied to local DB; Railway project created; env vars set; `python -m checkpoint_recorder` starts without errors; aiogram webhook registered.
- traces: DM1–DM8 schema, [[adr-012-technology-stack|ADR-012]]

## T2 User registration and account status gate <- FR1, FR2, FR3 (Idle + PendingPeriodicity)
- size: S
- tokens: ~15k
- confidence: high
- owner: Operator
- depends_on: [T1]
- done: First-time user message creates exactly one InternalUser record (idempotent); onboarding message dispatched covering all 4 required points (BR11); `registration_event` observable in ObservabilityEvent table; PendingDeletion messages routed to restoration prompt.

## T3 Auto-parsed data entry and metric auto-creation <- FR4, FR6, NFR5, NFR9
- size: M
- tokens: ~35k
- confidence: high
- owner: Operator
- depends_on: [T2]
- done: Free-text message with recognized metric creates immutable Entry within 5s p95; compound entry stores `dimension_assignments`; unrecognized metric triggers periodicity prompt (PendingPeriodicity state); no UPDATE on Entry table verifiable from DB query log; `parse_outcome_event`(success) observable for every parsed entry.

## T4 Explicit metric creation and /help <- FR7, FR19, NFR17, NFR18
- size: S
- tokens: ~10k
- confidence: high
- owner: Operator
- depends_on: [T2]
- done: `/metric_create` with valid params creates Metric; duplicate name returns error (DB UniqueConstraint verified); `/help` returns complete command list to any user including unregistered; no state side-effects from /help.

## T5 ParseAttempt lifecycle and late categorization <- FR5, FR15, NFR16
- size: M
- tokens: ~40k
- confidence: high
- owner: Operator
- depends_on: [T3]
- done: Ambiguous message creates ParseAttempt within 5s p95; user selection creates Entry with original `entry_timestamp`; deferred ParseAttempt retained; compensating delete verified: disambiguation prompt failure leaves zero Pending ParseAttempts; `/deferred_list` and `/deferred_categorize` produce Entry from Deferred ParseAttempt.

## T6 Metric catalog management <- FR8, FR9, FR10, FR20, FR21
- size: M
- tokens: ~30k
- confidence: high
- owner: Operator
- depends_on: [T4, T5]
- done: `/metric_list` returns all Active/Archived metrics with correct MetricActivityStatus; `/metric_archive` suspends alert evaluation (verified by AC-FR9-1); `/metric_delete` cascade is atomic — zero orphaned records after deletion; `/alert_list` and `/alert_delete` operational.

## T7 Conversation state routing completion (disambiguation + deletion branches) <- FR3 (PendingDisambiguation, PendingMetricDeletionConfirmation)
- size: S
- tokens: ~10k
- confidence: high
- owner: Operator
- depends_on: [T5, T6]
- done: Non-disambiguation message while PendingDisambiguation receives blocking response; non-confirmation cancels metric deletion and returns to Idle; two non-Idle states cannot coexist for the same user.

## T8 Alert Engine — configuration, evaluation, re-arming, list, delete <- FR11, FR12, FR13, FR20, FR21, NFR10
- size: M
- tokens: ~35k
- confidence: high
- owner: Operator
- depends_on: [T6, T7]
- done: `/alert_set` creates Active alert; next Entry meeting threshold transitions alert to Triggered and dispatches notification within 60s; Entry not rolled back on alert evaluation failure (AC-FR12-1); `alert_evaluation_event` observable for every evaluation; `/alert_rearm` returns alert to Active; `/alert_delete` with confirmation permanently deletes.

## T9 Account deletion with grace period and restoration <- FR16, FR17
- size: S
- tokens: ~20k
- confidence: high
- owner: Operator
- depends_on: [T8]
- done: `/account_delete` + confirmation sets account_status = PendingDeletion with deletion_scheduled_timestamp = now() + 72h; any subsequent message routes to restoration prompt; restoration confirmation returns account to Active with all data preserved.

## T10 Conversation state routing — restoration branch <- FR3 (PendingRestorationConfirmation)
- size: XS
- tokens: ~5k
- confidence: high
- owner: Operator
- depends_on: [T9]
- done: PendingDeletion user's message routes exclusively to Account Manager regardless of message content; non-confirmation leaves account in PendingDeletion; ConversationState returns to Idle after any resolution.

## T11 Chart generation and delivery <- FR14, NFR3
- size: M
- tokens: ~40k
- confidence: medium
- owner: Operator
- depends_on: [T9, T10]
- notes: matplotlib rendering latency is unknown until tested; two-phase pattern (ADR-006) mitigates timeout risk; executor thread model requires testing
- done: `/chart` returns acknowledgment within 5s p95; chart image delivered within 30s p95; zero-entry metric returns error not empty chart; chart coroutine failure sends second error message; `chart_delivery_event` observable for both success and failure.

## T12 Scheduled Process — purge, retention, cleanup, heartbeat <- FR18, NFR11, NFR12, NFR13, NFR15
- size: M
- tokens: ~35k
- confidence: high
- owner: Operator
- depends_on: [T10]
- done: APScheduler job runs at ≤12h cadence; `scheduler_heartbeat` observable per run; PendingDeletion account with elapsed timestamp purged atomically (zero residual records including raw_input); 1-year idle account emits `retention_review_event` without deletion; stale PendingPeriodicity states cleared; `scheduler_overlap_event` emitted if concurrent run attempted.

## T13 Observability completion and load verification <- NFR1, NFR2, NFR4, NFR14
- size: S
- tokens: ~15k
- confidence: medium
- owner: Operator
- done: All 5 business success metrics computable from ObservabilityEvent queries; 20-concurrent-user load test passes NFR1 (≤5s) and NFR2 (≤5s) with no data corruption or duplicate records; monthly uptime measurement baseline established.

# Critical Path

T1 → T2 → T3 → T5 → T8 → T11 → T12 → T13

Critical path total: ~220k tokens (L). Parallelizable from T2 onward: T4 runs in parallel with T3.

# RACI

This is a solo project — all functional roles are performed by the same person (Operator), with AI agents assisting in implementation and documentation. The RACI reflects accountability boundaries, not separate individuals.

| Deliverable | Operator | AI Agent |
|---|---|---|
| Requirements (BRD, SRS) | A/R | C |
| Architecture and ADRs | A/R | C |
| Implementation (T1–T13) | A | R (primary implementation) |
| Testing and acceptance | A/R | C |
| Observability setup | A/R | C |
| Production deployment | A/R | C |
| Documentation (this plan) | A/R | R (drafting) |

A = Accountable. R = Responsible. C = Consulted.

**Bus-factor risk:** single operator for all A/R roles. AI agent assistance reduces per-task burden but cannot act autonomously without the operator. Accepted per BRD D-005, RISK8.

# Dependencies on external parties

- **Telegram Platform (SH5)** — stable Bot API and webhook delivery for all FR delivery. Criticality: critical. No mitigation for policy changes. Tracked as [[risks#RISK4|RISK4 Telegram API change]].
- **Railway PaaS** — HTTPS endpoint, process supervisor, env var injection for T1 and M4. Criticality: high. Always-on configuration must be verified before M4 completion.
- **Supabase** — managed PostgreSQL availability and backup (RPO ≤24h) for T1 onwards. Criticality: critical. Confirm backup active before M4 completion.

# Open Questions

- Q1 NLP confidence threshold (SU-002, architecture Q1) — start at 0.7; tune from production `parse_outcome_event` data. Blocks: T3 integration testing acceptance criteria.
- Q2 Deferred ParseAttempt cleanup window (SU-006, SRS Q1) — proposed 30 days; pending stakeholder confirmation. Blocks: T12 scheduled cleanup job implementation.
- Q3 Chart default time range and image format (SRS Q4) — proposed 30 days / PNG. Blocks: T11 acceptance criteria validation.

Resolved (from planning assumptions):
- ~~OI-2~~ NLP library resolved: rapidfuzz + pint + regex ([[adr-012-technology-stack|ADR-012]])
- ~~OI-3~~ Data Repository resolved: Supabase PostgreSQL ([[adr-012-technology-stack|ADR-012]])
- ~~PA-1~~ SQLite (proposed in planning assumption 1) superseded by Supabase PostgreSQL per technology.md

# Change log reference

See `/docs/_meta/changelog.md` for plan-level changes.

<!-- custom section -->

# Planning Assumptions

From source `project_plan.md` §6. These were the assumptions that governed delivery planning.

1. **NLP library is in-process rule-based (OI-2 resolved as rapidfuzz + pint).** Required because FR4 and FR5 branch on NLP confidence scores. If an external NLP service had been chosen, Stages 1–2 would have gained an external dependency and privacy constraints on raw_input transmission.

2. **Data Repository is Supabase PostgreSQL (OI-3 resolved).** Required because every atomic operation (FR1 idempotent create, FR6 Metric+Entry atomicity, FR10 cascade delete, FR18 purge) depends on ACID transactions and unique constraints. SQLite (originally proposed) was superseded by Supabase per technology.md.

3. **ConversationState is persisted in the database, not in process memory.** FR3 requires state to survive process restarts. This is achieved via DM6 (ConversationState table). If state were in-memory only, FR3 would be violated on any Railway restart.

4. **"Single retry" in FR12 (alert notification) means one immediate additional attempt with no backoff queue.** Simplest interpretation consistent with the monolith architecture and ≤20-user target. A durable retry queue would require a separate infrastructure component.

5. **SchedulerLock (FR18 run-lock) is implemented as an atomic check-and-set on DM8 in PostgreSQL.** Consistent with the monolith and single-process deployment. If the system were horizontally scaled, this lock mechanism would be insufficient and would require a distributed lock.

6. **MetricActivityStatus is computed on read (lazy), not stored as a persistent materialized record.** FR8 describes a derived computation over Entry history. Treating it as a computed view avoids an update trigger mechanism that no requirement describes.
