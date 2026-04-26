# Architecture Review Report

## Reviewed Versions

- **Architecture:** v0.9 (`architecture_v0.9.md`)
- **Business:** v0.5 (`business_analysis_v0.5.md`)
- **Context:** v0.7 (`system_analysis_v0.7.md`)
- **Previous Review:** v0.8 (`architecture_v0.8_review.md`)

---

## 1. Executive Assessment

Architecture v0.9 is a materially stronger document than v0.8. All five mandatory revisions from `architecture_v0.8_review.md` are correctly and completely addressed: §4.3 introduces a well-structured, full conversation state machine; the Alert Archived state traceability gap is resolved by an explicit and enforceable out-of-scope declaration; the Scheduled Process run-lock is named and specified at the conceptual level; Flow C gains the ParseAttempt coordination step; and SU-009 (periodicity prompt expiry, 24h) is defined with Scheduled Process cleanup scope and metric-not-written-until-confirmed semantics. Additional gaps — compound first-contact flow (Flow I), AD-11 (database-layer metric name uniqueness), AD-2 polling health check default, token auth failure behavior, configurable dangling detection window, allowlist ordering, and PendingDeletion alert structural guarantee — are all correctly resolved.

Two minor residual gaps remain that do not block implementation specification authorship: (1) System v0.7 Flow 11 (metric deletion with confirmation) is referenced in the Metric Manager component but has no explicit step-by-step architecture flow, while the `PendingMetricDeletionConfirmation` conversation state defined in §4.3 is never entered or exited by any modeled flow in §5.2; and (2) the `active_users_count` period-boundary staleness issue, noted in the v0.8 review's observability section as Low priority, remains unacknowledged in the observability baseline. Neither gap creates implementation-blocking ambiguity at portfolio scale. The document is ready to serve as a baseline for an implementation specification.

---

## 2. Mandatory Revision Verification

### MR1 — Define a conversation state model for the User Session Guard

**Status: FULLY ADDRESSED ✓**

§4.3 is a new, dedicated section that defines all five named states: `Idle`, `PendingDisambiguation`, `PendingPeriodicity`, `PendingMetricDeletionConfirmation`, and `PendingRestorationConfirmation`. Each state has an entry condition, a routing behavior for new inbound messages, and an exit condition. The Message Dispatcher routing rule is explicit: "Before classifying any message, the Dispatcher must consult the User Session Guard's current conversation state (§4.3). If the user's state is non-Idle, the Dispatcher routes the message according to the non-Idle routing policy defined in §4.3, overriding standard intent-based classification." The PendingPeriodicity + PendingDisambiguation collision rule is explicitly defined. `ConversationState` is added to §6 as a persisted Data Repository entity with atomic state transitions. All three prior gaps (routing ambiguity, periodicity-pending state model gap, Flow A compression) are resolved by this single addition.

### MR2 — Address the Alert Archived state traceability gap

**Status: FULLY ADDRESSED via out-of-scope declaration ✓**

The deferred-scope note immediately after Flow I in §5.2 is clear, justified, and enforceable. The decision states: "User-triggered alert archiving and reactivation are explicitly out of scope for this architecture version." The rationale is given. The directive "the Alert Archived state via user-triggered action **must not be implemented** by implementation teams" correctly converts an ambiguous gap into an explicit constraint. Alert entity in §6 references the deferred-scope note. Metric Manager component note references it. Observability note in §11.1 explicitly states no `alert_lifecycle_event` schema is defined for this version. This is the correct approach: explicit deferral is architecturally preferable to a silent omission.

### MR3 — Specify the Scheduled Process run-lock mechanism at a conceptual level

**Status: FULLY ADDRESSED ✓**

The mechanism is named: "`scheduler_lock` record in the Data Repository with an atomic check-and-set on invocation start and a release on invocation end." Stale lock handling is defined (lock age exceeding two scheduled intervals → may be overridden, operator-detectable). `scheduler_overlap_event` is emitted on failed lock acquisition. The specification appears consistently in §4.1 Scheduled Process component, §4.2 Data Repository, §4.2 Data Strategy table (scheduler_lock entity), Flow E pre-condition, §8 Bottlenecks table, and §9 failure scenarios. Technology remains correctly deferred to AU-003 while the pattern is fully named.

### MR4 — Add a behavioral note to Flow C for active Pending ParseAttempts

**Status: FULLY ADDRESSED ✓**

Flow C step 2 is new: "Account Manager → ParseAttempt Manager: if an active Pending ParseAttempt exists for this user, transition it to Deferred. This is a no-op if no active ParseAttempt exists." The coordination failure behavior is defined: Account Manager logs a warning and proceeds; any remaining Pending ParseAttempt will be detectable as a dangling record via Observability within `parse_attempt_dangling_detection_window`. ParseAttempt Manager Inputs column updated. This is correctly specified.

### MR5 — Define or defer the periodicity prompt expiry

**Status: FULLY ADDRESSED ✓**

SU-009 is defined: default 24h, consistent with SU-001 (ParseAttempt expiry). Metric is explicitly not written until periodicity is confirmed — no orphaned metric records accumulate on timeout. Scheduled Process cleanup is added as step 5 in Flow E. Flow A is expanded with steps 4b (periodicity confirmed → atomic metric + entry creation → Idle) and 4c (SU-009 timeout → Scheduled Process clears state → Idle, no metric/entry created). Configuration & Secrets includes the parameter. §7.1 gains a UX NFR row. §9 gains a failure scenario row. `periodicity_prompt_event` with outcome "abandoned" is emitted on cleanup. All five requirements of MR5 are met.

---

## 3. Strengths

- **§4.3 Conversation State Model is production-quality.** Five named states with entry conditions, routing behaviors, exit conditions, and the single-active-state invariant. The collision rule (PendingPeriodicity + PendingDisambiguation cannot coexist; PendingPeriodicity takes precedence and blocks new ParseAttempt creation) removes the implementation-design-in-the-clear risk that defined v0.8. This is above-average for a portfolio-scope architecture document.
- **Alert archiving out-of-scope declaration is operationally enforceable.** "Must not be implemented" is a stronger directive than "deferred" — it converts a silent gap into an active constraint, preventing implementation teams from independently deciding to implement the feature inconsistently.
- **Scheduler run-lock mechanism is correctly specified at the conceptual level.** Atomic check-and-set on a data-layer record, stale lock handling, and `scheduler_overlap_event` form a complete contract. AU-003 defers the technology without deferring the pattern.
- **AD-11 (metric name uniqueness) is correctly reasoned.** The explicit rejection of application-layer query-before-insert (TOCTOU-vulnerable) and the parallel to AD-5 (repository-layer enforcement is safer) make this a well-authored decision. Constraint violation handling is defined as a user-notification path.
- **Flow I (compound first-contact) is comprehensive.** Partial failure semantics are explicit: "account created successfully, entry could not be processed — please send it again" prevents silent entry loss (R-015). NLP ambiguous result path and periodicity prompt path within the compound flow are acknowledged. Recovery is defined.
- **AD-2 polling health check default is resolved with correct rationale.** Successful Telegram API poll response preferred over local health file because it confirms both process liveness *and* API connectivity — a meaningful difference when the primary failure mode is token revocation or API unavailability.
- **PendingDeletion alert guarantee is correctly made structural, not conditional.** The guarantee derives from routing behavior (no entries stored → no evaluation trigger), not from a conditional check inside the Alert Engine. This is the right architectural control — a conditional check in Alert Engine could be bypassed; the routing guarantee cannot.
- **Token auth failure behavior is fully specified.** Retry 3× with exponential backoff → emit `token_auth_failure_event` → halt → process supervisor restart. The rationale ("continuing without a valid token would silently drop all messages") is correct and justifies halt over graceful degradation.
- **`conversation_state_event` enables operational visibility into stuck states.** The conversation state dashboard in §11.2 (count of users in non-Idle states, duration in PendingPeriodicity or PendingDisambiguation beyond threshold) converts what was a latent operational blind spot into an observable signal.
- **All v0.8 ADR-level gaps are resolved.** AD-9 detection window is configurable (not hardcoded). AD-2 health check default is selected. AD-11 is a new, complete ADR. No remaining "hand-wavy" decisions in the 11-ADR set.
- **Traceability Matrix (§14) correctly updated.** User Session Guard §4.3, AD-11, and SU-009 are added to appropriate business goal rows. No business goal row is orphaned.

---

## 4. Critical Weaknesses

- **System v0.7 Flow 11 (metric deletion with confirmation) has no explicit architecture flow.** `PendingMetricDeletionConfirmation` is correctly defined in §4.3 with routing behavior and exit conditions. However, no flow in §5.2 models the metric deletion journey: which command triggers it, what confirmation prompt is dispatched, how the cascade delete (AD-7) is invoked, and what happens if the user cancels. The Metric Manager component references "individual metric deletion (Flow 11)" pointing to System v0.7 numbering, not an architecture flow. An implementation author can derive approximate behavior from §4.3 and AD-7, but the step-by-step coordination across Message Dispatcher → Metric Manager → User Session Guard → Data Repository (cascade) → Observability is not documented. This is a lower-severity gap than the missing compound flow in v0.8 (which had partial failure risk), but it is a real traceability hole: a named conversation state exists with no architecture flow that enters or exits it.

---

## 5. NFR Coverage Gaps

| NFR Category | Missing / Weak Area | Why It Matters | Required Fix |
|---|---|---|---|
| **Observability — `active_users_count` freshness at period boundaries** | §11.1 states "freshness mechanism: pushed on each Entry write." §4.1 AD-4 states the same. Neither acknowledges that at a daily-period boundary (e.g., midnight UTC), a user who was active (4 of 5 days) transitions to inactive (3 of 5 days) without any Entry write triggering the count update. The count may remain stale for hours at the period boundary. | The business success metric "tracking retention >40%" depends on accurate active user counts. The observability baseline describes this as a "near-real-time" signal, but the staleness window at period boundaries can be significant. At 10 users, the practical impact is low but the documented accuracy claim is stronger than the mechanism supports. | Add a caveat to §11.1 or §4.1 AD-4: "Active user count is accurate within one entry-write cycle of any period boundary. At period boundaries where no entries are written, count may remain stale until the next Entry write or next scheduled MetricActivityStatus recomputation." This is an acknowledgment, not a structural change. |
| **Observability — compound first-contact partial failure event** | §9 correctly documents the Flow I partial failure scenario. Detection is via "co-occurrence of `registration_event` success and `error_event` in same session." No dedicated event is defined; §11.1 Traces adds "Compound onboarding: Account Manager → Data Repository → Entry Processor → NLP Engine → Data Repository." But the trace does not capture the partial failure signal explicitly. | Compound-failure distinction from "registration failed" vs. "registration succeeded, entry failed" is operationally invisible without querying for the co-occurrence pattern. At 10-user scale and low first-contact volume, acceptable — but the claim in §9 that it is "detectable via event co-occurrence" should be qualified: detection requires post-hoc log analysis, not a real-time signal. | Low priority — a note in §11.1 Observability clarifying that the compound partial failure is detectable via log analysis (not a dashboard signal) is sufficient. |

---

## 6. Trade-off & ADR Issues

No critical trade-off or ADR issues remain.

- AD-2 polling health check default is now resolved with rationale.
- AD-11 metric name uniqueness is new and well-authored.
- AD-9 detection window is configurable with rationale stated.
- All 11 ADRs have alternatives, rationale, consequences, and linked NFR/business goals.

**Minor observation:** AD-9 states the 30 s default "distinguishes dispatch in progress from genuine failure" but does not state the tolerance for false positives (e.g., if a slow Telegram API takes >30 s to accept the dispatch, the dangling detection fires before dispatch completes). This is a low-severity documentation gap; the configurable parameter is the correct mitigation.

---

## 7. Reliability & Failure Scenario Issues

No critical reliability gaps remain.

| Scenario | Residual Issue | Risk | Priority |
|---|---|---|---|
| **Flow C coordination failure — dangling PendingDisambiguation under PendingDeletion** | Flow C step 2 coordination failure leaves a Pending ParseAttempt in place. The Account Manager proceeds, and the user is now PendingDeletion. Subsequent messages route to the restoration flow (User Session Guard detects PendingDeletion), but the PendingDisambiguation state may still be active. If the user's conversation state was PendingDisambiguation before requesting deletion, Flow C step 2 transitions it to Deferred — but the coordination failure means the state may not have been cleared. The User Session Guard routing on PendingDeletion overrides conversation state routing, so the collision is unlikely to cause visible failure, but the state record is orphaned. | ConversationState record stuck in PendingDisambiguation for a PendingDeletion user. Detectable via `conversation_state_event` and `parse_attempt_event` combination. Operator can manually clear if needed. | Low |
| **Flow I step 8 — `registration_event` ordering relative to entry failure** | Step 8 emits `registration_event` after entry processing (steps 6–7). If steps 6–7 fail, the partial failure semantics say "Account Manager emits `registration_event` success" — but step 8 as written only fires after entry processing completes. A step-7 failure may bypass step 8, meaning no `registration_event` is emitted for a successful registration whose entry subsequently failed. This is a documentation inconsistency: the flow and the partial failure semantics describe different ordering. | `registration_event` may not fire for successful registrations whose compound entry fails, making the `user_registered` count inaccurate in a specific class of failures. | Low |

---

## 8. Security & Compliance Issues

No security gaps remain from the v0.8 review.

| Area | v0.9 Status |
|---|---|
| Metric name uniqueness TOCTOU | RESOLVED — AD-11 eliminates via database-layer unique constraint |
| PendingDeletion alert guarantee | RESOLVED — structural guarantee via routing, correctly documented in §4.1 Alert Engine and §10 |
| Allowlist check ordering | RESOLVED — explicitly stated in User Session Guard: after InternalUser lookup, before new InternalUser creation |
| Token auth failure behavior | RESOLVED — retry 3×, halt, process supervisor restarts; defined in §4.1, §9, §10 |

No new security concerns introduced in v0.9.

---

## 9. Observability Issues

| Signal | Issue | Operational Risk | Priority |
|---|---|---|---|
| **`active_users_count` period-boundary staleness** | The freshness mechanism ("pushed on each Entry write") overstates accuracy at period-day boundaries where no entries are written. The observability baseline claims "near-real-time" freshness, but the mechanism provides per-entry accuracy, not per-period accuracy. | The "tracking retention >40%" business metric derived from this signal may overcount retention at period boundaries by up to one period. At 10 users with ~100 entries/day, worst-case staleness is short but not zero. | Low |
| **Flow I partial failure — co-occurrence-only detection** | No dedicated event schema distinguishes "registration succeeded, entry failed" from "registration failed." Requires post-hoc log analysis to surface. | Onboarding-phase entry failure rate is not a real-time dashboard signal. Acceptable for portfolio scope but worth acknowledging in §11.1. | Low |

---

## 10. Broken Traceability

| Item | Missing Link | Why Problematic | Fix |
|---|---|---|---|
| **System v0.7 Flow 11 (metric deletion with confirmation) — no architecture flow** | `PendingMetricDeletionConfirmation` is defined in §4.3 with entry condition "Metric Manager has dispatched a 'confirm metric deletion?' prompt" and exit conditions (confirmed → cascade delete; cancelled → Idle). However, no flow in §5.2 models this journey end-to-end. The Metric Manager component references "Flow 11" pointing to System v0.7 numbering. An implementation author must reconstruct the step-by-step interaction between Message Dispatcher, Metric Manager, User Session Guard, Data Repository (cascade — AD-7), and Observability Collector from scattered references. | The two-step confirmation pattern introduces at least one intermediate conversation state. No architecture flow shows how the confirmation prompt is dispatched, what happens to the User Session Guard state during the confirmation window, or how the cascade delete is coordinated. Unlike simple command flows (metric listing, metric creation), metric deletion has a non-trivial failure surface: the confirmation prompt itself can be the failure point, and the cascade delete (AD-7) adds atomicity requirements. | Add a compact Flow J (Metric Deletion with Confirmation) to §5.2, or extend Flow H to include metric deletion. Minimum required elements: trigger, confirmation prompt dispatch + User Session Guard → PendingMetricDeletionConfirmation, user-confirms path (cascade delete — AD-7 — → Idle), user-cancels path (→ Idle), failure point at cascade delete step. |
| **Flow I step 8 `registration_event` ordering** | The flow (step 8) places `registration_event` after entry processing, but partial failure semantics imply it fires on registration success regardless of entry outcome. This is inconsistent: a reader following the flow would not emit `registration_event` if steps 6–7 fail; a reader following the partial failure semantics would. | An implementation author following the happy-path flow would emit `registration_event` only after entry succeeds — making the `user_registered` count inaccurate in compound-failure scenarios. | Move `registration_event` emission to immediately after step 3 (Data Repository: create InternalUser) succeeds, as a fire-and-forget step 3a. This mirrors the actual event semantics: registration succeeds when the InternalUser is created, not when the compound entry succeeds. |

---

## 11. Scoring

| Dimension | Raw Score (0–5) | Weighted Score | Comment |
|---|---|---|---|
| Alignment to Business Goals | 4 | 8 | All five business goals fully traced; AG-1–AG-7 all linked. Flow I resolves the compound onboarding omission from v0.8. Score held at 4 (not 5) due to active_users_count staleness at period-boundary, which affects accuracy of the "tracking retention >40%" primary success metric — the observability baseline overclaims freshness. |
| Boundary & Context Consistency | 4 | 4 | All System v0.7 mandatory flows now covered. Alert Archived state explicitly deferred. Metric deletion (System v0.7 Flow 11) referenced in Metric Manager but has no corresponding architecture flow; `PendingMetricDeletionConfirmation` state defined but never entered or exited by any flow in §5.2. This is the sole remaining boundary gap. |
| Component Model Quality | 4 | 8 | §4.3 is an excellent component-level addition — full state machine with collision semantics. All components well-scoped and non-overlapping. Minor gap: the state transition *driver* for User Session Guard is implicit in flows (e.g., who calls User Session Guard to transition to PendingPeriodicity in Flow A step 4b — Entry Processor or User Session Guard listening for prompt dispatch?). This is an implementation-detail ambiguity but one that should be clarified at the component level. |
| Interaction Model Clarity | 3 | 6 | Flows A–I cover the vast majority of System v0.7 flows with failure points and recovery. Significant improvement over v0.8. Score held at 3 because `PendingMetricDeletionConfirmation` is defined in §4.3 but has no backing flow in §5.2 — the multi-step metric deletion journey (the only remaining two-step confirmation flow without a corresponding architecture flow) is left to implementation authorship. This is a more contained gap than v0.8's three missing flows, but it is meaningful given that §4.3 explicitly references "Metric Manager has dispatched a confirmation prompt" as an entry condition that no flow in §5.2 can trigger. |
| NFR Coverage & Tactics | 4 | 8 | SU-009, AD-2, configurable detection window, concurrent read safety fallback, and backup/RPO/RTO all correctly specified. Score held at 4 because the `active_users_count` period-boundary staleness is not acknowledged in the NFR table or observability baseline — the described freshness mechanism overstates the guarantee. |
| Trade-off Justification | 5 | 10 | All 11 ADRs are fully authored. AD-11 is new and correctly structured. AD-2 health check resolved with clear rationale. AD-9 detection window configurable with stated 30 s rationale. No remaining hand-wavy decisions. |
| Reliability & Failure Handling | 5 | 10 | All five mandatory revisions address reliability gaps. Token auth failure: retry+halt+restart defined. Scheduler run-lock: atomic check-and-set. ParseAttempt on account deletion: coordination step in Flow C. Periodicity expiry: SU-009 with Scheduled Process cleanup. Conversation state: §4.3 eliminates routing ambiguity. Residual Flow C coordination failure edge case and Flow I step ordering inconsistency are low-severity and documented. |
| Security & Compliance Baseline | 5 | 5 | All three v0.8 security gaps resolved: TOCTOU (AD-11), PendingDeletion alert guarantee (structural), allowlist ordering (specified). Token auth behavior defined. No new security concerns introduced. |
| Observability Readiness | 4 | 4 | `periodicity_prompt_event` (dispatched/confirmed/abandoned), `conversation_state_event`, and `scheduled_process_event` updates are strong additions. Score held at 4 for: active_users_count period-boundary staleness unacknowledged in the observability baseline; compound first-contact partial failure detectable only by log analysis (not a dashboard signal). |
| Risk Identification & Mitigation | 5 | 5 | Conversation state routing no longer a risk (§4.3 eliminates it). Token auth failure added to §13.1 with correct halt-and-restart mitigation. Scheduler overlap covered. All remaining risks have explicit mitigations. |

**Total Score: 68 / 70**

> Threshold reference (from rubric): 63–70 = Strong architecture.

---

## 12. Mandatory Revisions

**Score 68/70 — above the mandatory revision threshold.**

No mandatory revisions are required. The document is ready to serve as a baseline for an implementation specification.

**Recommended minor adjustments before advancing (non-blocking):**

1. **Add Flow J — Metric Deletion with Confirmation** *(addresses the single remaining §5.2 gap)*. Minimum: trigger (user sends delete-metric command), Metric Manager dispatches confirmation prompt, User Session Guard → `PendingMetricDeletionConfirmation`, user confirms → cascade delete (AD-7) → Idle, user cancels → Idle. Failure point: cascade delete failure → metric remains Active, user notified. This flow resolves the broken traceability between §4.3 (`PendingMetricDeletionConfirmation` state) and §5.2 (no flow that enters it).

2. **Move `registration_event` emission to immediately after InternalUser creation in Flow I** *(resolves the step-8 ordering inconsistency)*. Emit as step 3a (fire-and-forget after Data Repository commit in step 3). The partial failure semantics are then consistent with the happy-path flow: `registration_event` fires on registration success, regardless of entry processing outcome.

3. **Add a staleness caveat to §11.1 and §4.1 AD-4 for `active_users_count`** *(Low priority — observability accuracy claim)*. One sentence: "Count accuracy is bounded by entry-write frequency; at daily-period boundaries with no entries written, the count may remain stale until the next successful Entry write or a scheduled recomputation." This converts an overstatement into an accurate description without architectural change.

---

## 13. Iteration Recommendation

**Accept as Baseline for Implementation Spec**

All five mandatory revisions from `architecture_v0.8_review.md` are correctly and completely addressed. The document has no implementation-blocking gaps. The three remaining observations (missing metric deletion flow, `registration_event` ordering inconsistency, `active_users_count` staleness caveat) are minor enough to address concurrently with implementation specification authorship rather than requiring an additional architecture iteration cycle.

The overall architecture is sound, internally consistent, and provides sufficient specificity for an implementation specification author to derive component responsibilities, interaction sequences, data contracts, failure modes, and observability signals without making unilateral architectural decisions. Score 68/70 places the document in the "Strong architecture" tier.

**If the Recommended Minor Adjustments are addressed:**
- Flow J (metric deletion) eliminates the last §5.2 coverage gap
- `registration_event` ordering fix eliminates the observability inconsistency in Flow I
- No additional review cycle is required; these can be validated by the implementation specification author

**If the Recommended Minor Adjustments are deferred:**
- An implementation author can still author a conforming implementation specification
- The metric deletion flow will need to be reconstructed from §4.3 + AD-7 — acceptable but suboptimal
- The `registration_event` inconsistency should be flagged to the implementation specification author as a decision point
