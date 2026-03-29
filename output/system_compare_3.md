# System Context Document — Comparative Review Report

> **Reviewed Documents:**
> - Document A: `old/system_analysis_v0.7.md` — System Context Document v0.7 (Based on Business v0.5)
> - Document B: `output/system/system_v0.3.md` — System Context Document v0.3 (Based on Business v0.3)
> - Business Reference Used: `output/business/business_v0.3.md`
> - Review Date: 2026-03-29

---

## Preface: Context of This Review

Both documents describe the same underlying Telegram-native personal metric tracking bot but come from different lineages and iteration depths:

- **v0.7** is a mature, seventh-iteration document from the `old/` pipeline. It references Business v0.5, which is absent from this repository. It introduces alerts, multi-value compound entries, a dimension naming convention, and MetricActivityStatus as a formal entity.
- **v0.3** is the third iteration from the current active pipeline. It is fully traceable to Business v0.3 (available and verified). It builds on v0.2 by resolving ten mandatory revisions from the v0.2 review cycle — addressing PendingClarification state contradictions, storage model definition, keyword collision handling, operator disclosure integration, account deletion enforcement, and more.

Because v0.7 references Business v0.5 — absent from this repository — traceability claims specific to that version cannot be verified. All such gaps are flagged explicitly.

---
---

# DOCUMENT A — System Review Report: v0.7

## Reviewed Version
v0.7 (Based on Business Analysis v0.5 — **not available in this repository for cross-reference**)

## 1. Executive Assessment

System Context Document v0.7 is the most mature and technically thorough document in this comparison. It provides exceptional flow coverage, complete and internally consistent state lifecycle models for all entities, a 19-item numbered risk register, and a structured uncertainty register (SU-001 to SU-008) that explicitly defers unresolved design questions to the architecture stage. The privacy note for `raw_input` and the cascade atomicity requirements are highlights of rigorous modeling discipline. The document's principal structural flaw is a boundary violation: five internal subsystem components (NLP Parsing, Alert Evaluation, Chart Rendering, Logging/Observability, Data Persistence) are modeled as actors in §2, conflating the context perimeter with internal architectural decomposition. Additionally, the document cannot be fully audited because its business baseline (v0.5) is unavailable, and two scope changes — alert inclusion and user-count reduction — cannot be traced to confirmed business decisions.

## 2. Structural Strengths

- **Exceptional flow completeness.** Eleven primary flows and four sub-flows (3a, 3b, 6a, 10a) are defined with triggers, step-by-step processing, outputs, and per-step risk points. Transactional semantics are explicitly defined per scenario in §8.3.
- **Complete, unambiguous state lifecycle models.** InternalUser, Metric, Entry, Alert, and ParseAttempt state models are internally consistent, with mutually exclusive states, defined entry/exit conditions, and no unreachable or dead-end states (with one exception noted below).
- **Structured risk register.** Nineteen numbered risks (R-001 to R-019) with ID, type, impact, probability, and mitigation — the most complete risk register of either document.
- **Uncertainty register (SU-001 to SU-008).** Explicitly defers unresolved questions (ParseAttempt expiry timeout, NLP confidence threshold, Metric auto-creation eligibility, Archived Metric alert behavior, MetricActivityStatus computation strategy, Deferred ParseAttempt cleanup, timezone handling, and `raw_input` GDPR classification) to the architecture stage with validation plans.
- **`raw_input` Privacy Note (§4).** Identifies the residual personal data risk in free-text message storage, scopes it relative to D-007 (which covers identity fields only), and prescribes a retention and purge policy. Exemplary documentation of a known limitation.
- **Cascade atomicity requirements** for both account deletion (Flow 10, step 5) and metric deletion (Flow 11, step 6) are explicitly stated, preventing partial-delete inconsistencies.
- **Alert one-shot lifecycle (SD-003 Resolved).** The ParseAttempt Deferred state (SD-007 Resolved) is correctly modeled as a resting non-terminal state, preserving user intent for late categorisation.
- **Decision Log** is rich: 15+ decisions with version-stamped resolution status.
- **Traceability table** links each business goal to specific entities, flows, states, and risk IDs.

## 3. Structural Weaknesses

- **Internal subsystems listed as Actors — architectural leakage.** NLP Parsing Component, Alert Evaluation Component, Chart Rendering Component, Logging / Observability Component, and Data Persistence Layer are classified as "Internal" actors in §2. At the context layer, actors are external agents and human roles. Internal components are inside the system box — not on its perimeter. This inflates the actor table, blurs the system boundary, and constitutes premature architectural decomposition.
- **Scale discrepancy with available business documentation.** Business v0.3 targets approximately 100 users; this document specifies approximately 10. The reduction is not explained in the Changes Introduced section and cannot be verified without Business v0.5.
- **Alerts in scope — unverifiable traceability.** Business v0.3 (D-05) explicitly confirms "Threshold alerts are out of scope." This document includes alerts as a core feature. While Business v0.5 presumably reversed D-05, that document is absent and the scope change cannot be audited.
- **Free Hosting Infrastructure absent from External Dependencies (§7).** The Telegram Bot API and Telegram Infrastructure are listed, but Free Hosting Infrastructure — a critical runtime dependency and data durability risk — is missing from the dependency table. This omission makes the dependency section incomplete for architecture handoff.
- **MetricActivityStatus as a formal entity.** A computed derived aggregate is elevated to a first-class entity in the data model at context level. It is more appropriate as a view or derived projection at the design layer; its presence adds modeling complexity without a user-facing interaction that requires it to be independently addressable.
- **Metric Archived state alert behavior undefined (SU-004).** The Alert State Model permits Active alerts on Archived Metrics. Whether alert evaluation is suspended for Archived metrics is deferred to system design — but this is a behavioral contract, not an implementation detail, and must be defined at context level.

## 4. Boundary Violations

| Violation | Location | Severity |
|---|---|---|
| Internal subsystems (NLP, Alert Eval, Chart Rendering, Logging, Data Persistence) listed as Actors | §2 Actors table | **High** — violates context-layer modeling; these are inside the system box per §3 |
| MetricActivityStatus as a context-level entity | §4 Core Entities | **Low-Medium** — computed state; belongs at design layer |
| Periodicity boundary arithmetic and "last 5 periods" computation | §12 | **Low** — implementation rules at context level; acceptable as a pre-architecture constraint but constitutes mild leakage |
| Free Hosting Infrastructure absent from dependency table | §7 | **Medium** — a hard dependency is invisible to architects reviewing §7 |

## 5. State Model Issues

### Gaps
- **Alert evaluation on Archived Metrics** is undefined (SU-004). The Metric state model shows Active alerts can exist on Archived metrics, but no behavioral rule governs whether those alerts continue to be evaluated. This is a behavioral gap — not an implementation detail.

### Overlaps
- None. All states across all models are mutually exclusive.

### Dead-ends
- None. All terminal states (Deleted, Expired, Resolved) have explicit cascade or purge semantics.

### Unreachable States
- **Alert Archived state.** The Alert State Model lists Archived as a valid state (entry condition: "User archives alert"). However, no flow in §5 defines an "archive alert" user action. Flow 9 handles Alert Deletion; Flow 6a handles Alert Re-arming. No "archive alert" flow exists. The Archived state is logically unreachable in the described system.

## 6. Flow Integrity Issues

### Trigger Ambiguity
- **Flow 4 (Chart Request):** Handles "insufficient data" explicitly but does not define the response when the metric name provided does not match any existing metric for the user. The no-match case has no defined response.
- **Flow 2 vs. Flow 3 dispatch boundary:** The confidence threshold separating "auto-parse" from "ambiguous" is deferred to SU-002. The dispatch decision between these two flows has no deterministic definition at context level — acceptable as a deferral but noted.

### Responsibility Confusion
- **Internal actors narrate internal steps.** Because NLP Parsing Component, Alert Evaluation Component, etc. are listed as actors, flow steps assign work to them as if they were external agents. This blurs the boundary between what the system does and which internal mechanism does it — a context vs. design layer concern.

### Circularity
- None. Flow 2 → Flow 5 (alert evaluation post-entry) is linear. ParseAttempt Deferred → Late Categorisation (Flow 3b) is a bounded user-driven loop. Alert re-arming (Flow 6a) is user-initiated, not automatic.

## 7. Entity Modeling Issues

### Duplication
- None identified.

### Missing Attributes
- **Alert entity:** No `created_timestamp` attribute is defined, despite this being necessary for alert history or audit tracing.
- **MetricActivityStatus:** `computation_timestamp` is present but no `last_entry_timestamp_at_computation` is included — stale status detection requires joining to the Entry table.

### Weak Relationships
- **ParseAttempt → Metric:** `candidate_metrics` is a ranked list of metric_ids, but the relationship between a Deferred ParseAttempt and a specific Metric is not formalized as an entity-level association. Cascade behavior in Flow 11 addresses this operationally but it is not expressed in the entity model.

## 8. Dependency Risks

| External System | Risk | Severity |
|---|---|---|
| Telegram Bot API | Complete channel failure; API policy change; bot suspension | Critical |
| Telegram Infrastructure | Image delivery failure; rate-limit enforcement | High |
| Free Hosting Infrastructure | **Not in §7** — Runtime failure, storage eviction, data loss | High (omission) |
| Scheduled Process (Retention/Deletion) | If absent, PendingDeletion accounts never purged; D-013 obligation unmet | Medium |

## 9. Scoring

| Dimension | Weight | Raw Score | Weighted Score | Comment |
|---|---|---|---|---|
| Boundary Clarity | x2 | 3 | 6 | Internal subsystems as actors; scale discrepancy; Free Hosting absent from §7 |
| Actor Definition Quality | x1 | 2 | 2 | Five of eight actors are internal components — fundamental context-layer violation |
| Entity Modeling Integrity | x1 | 4 | 4 | Rich entity definitions; Alert missing created_timestamp; MetricActivityStatus architectural |
| Flow Completeness | x2 | 5 | 10 | Exceptional — 11 primary + 4 sub-flows; transactional semantics; per-step risks |
| State Model Consistency | x2 | 4 | 8 | Complete and mutually exclusive; Alert Archived unreachable; Archived-Metric alert gap |
| Assumption Transparency | x1 | 4 | 4 | 10 assumptions + 8 uncertainties; risk and validation plans throughout |
| Risk Coverage | x1 | 5 | 5 | 19 numbered risks — comprehensive and typed |
| Business Traceability | x1 | 3 | 3 | Alert scope reversal and scale reduction unverifiable without Business v0.5 |

**Total Score: 42 / 50**

## 10. High-Risk Structural Issues

| Issue | Impact | Probability | Severity |
|---|---|---|---|
| Internal components modeled as Actors | Architects produce an incorrect C4 context diagram; internal components treated as external dependencies | Certain — already present | High |
| Alert scope reversal unverifiable (Business v0.5 absent) | Incorrect scope baseline propagates to architecture if v0.5 does not actually reverse D-05 | Low (reversal likely, but unverifiable) | High |
| Free Hosting absent from External Dependencies | Critical operational and data durability risk invisible in architecture review | Certain — omission confirmed | Medium |
| Alert Archived state unreachable | Dead code risk; archive-alert functionality implemented with no user-facing flow trigger | Medium | Medium |
| Alert evaluation on Archived Metrics undefined | Users with Active alerts on Archived metrics receive unexpected notifications or silent misfires | Medium | Medium |

## 11. Mandatory Revisions

1. **Remove internal subsystem components from the Actors table.** Replace with a brief "Key Internal Components" note in §3 if needed. Do not model NLP Parsing, Alert Evaluation, Chart Rendering, Logging/Observability, or Data Persistence as actors at context level.
2. **Add Free Hosting Infrastructure to External Dependencies (§7)** with the same rigor applied to Telegram entries — purpose, dependency type, risk level, and failure consequence.
3. **Resolve the Alert Archived state.** Either define an "archive alert" flow or remove Archived from the Alert State Model entirely and collapse it into Deleted.
4. **Define the behavioral contract for alert evaluation on Archived Metrics (SU-004).** This is a context-level behavioral rule, not a system design detail.
5. **Add a cross-reference note** explaining the scope changes from Business v0.3 (alerts out of scope, ~100 users) to this document, pointing explicitly to Business v0.5 as the authoritative source of those changes.
6. **Add `created_timestamp` to the Alert entity attributes.**

## 12. Iteration Recommendation

**Accept with Minor Adjustments**

The document is structurally sound in flow coverage, state modeling, risk awareness, and decision traceability. The actor-boundary violation and dependency table omission are real structural defects but require targeted corrections, not a full rework. The business baseline traceability gap (Business v0.5 absent) is a repository management concern, not a modeling failure.

---
---

# DOCUMENT B — System Review Report: v0.3

## Reviewed Version
v0.3 (Based on Business Analysis v0.3 — **available and verified**)

## 1. Executive Assessment

System Context Document v0.3 represents a significant and disciplined advance over v0.2. It resolves all ten mandatory revisions from the v0.2 review: the PendingClarification state contradiction is corrected, a storage model is defined, the account deletion enforcement mechanism is specified, keyword collision is handled, a parameter name matching strategy is introduced, non-text input is explicitly rejected, input sanitization is mandated, operator disclosure is integrated into onboarding, and a Help flow for Active users is added. The result is a document with strong boundary clarity, correct business scope alignment, and a meaningfully richer failure behavior contract. However, two structural defects undermine its quality: a duplicate actor has been introduced — "Bot Operator / System Owner" appears alongside "Developer / Bot Owner" as a separate internal actor, describing the same person — and the Logical Consistency Check (§15) incorrectly reports "three actors" while the table contains four. Additionally, the `is_synthetic` entity inconsistency and the demo parameter storage contradiction from v0.2 remain unresolved.

## 2. Structural Strengths

- **Full traceability to Business v0.3.** All decisions, constraints, and out-of-scope items map directly to the available business document. Alerts are correctly excluded (D-05). Scale is consistent (~100 users). Traceability section (§ last) links each business goal to entities, flows, states, and risk items.
- **PendingClarification state contradiction resolved.** The Resolved state is now reachable via the successful-parse branch of dispatch step 1. The Abandoned state is set on failed-parse or startup sweep. The two states are mutually exclusive and cover all exit paths from Open. The observability formula in §11.1 is confirmed as valid under the corrected model.
- **Account deletion enforcement mechanism defined (§9.5).** The 3-day window is enforced by a startup sweep that checks all PendingDeletion records against current time and executes atomic purge for expired records. Offline window behavior is explicitly described (purge deferred to next startup). Purge audit observability signal added (§11.7).
- **Keyword collision disambiguation rule (§5).** A named rule prevents log-intent messages from being misrouted as commands: keyword match requires the keyword as sole leading token in command structure context; numeric token adjacent to keyword defaults to Log Intent; reserved keyword protection prevents parameters from using reserved names.
- **Parameter name matching strategy (§5).** Case-insensitive exact match with whitespace normalization, explicit ambiguity handling for multiple matches, and a defined no-match message. This closes the silent-mismatch risk from v0.2.
- **Non-text input rejection (§5 pre-dispatch gate, §10.6).** Voice notes, images, stickers, and other non-text Telegram inputs are rejected before the dispatch pipeline and do not create ParseAttempt records or interact with PendingClarification state.
- **Input sanitization made mandatory (§8.7, §10.5).** All user-supplied input must be sanitized or parameterized before storage operations; raw input must never be interpolated directly into storage queries. Technology-class agnostic.
- **Operator disclosure mandatory in Flow 9.** The developer's unrestricted access to stored data is disclosed in the onboarding welcome message. The OnboardingSession entity adds `operator_disclosure_delivered` flag. §10.4 references Flow 9 as the enforcement mechanism. This is non-optional and tracked.
- **Flow 12 (Help / Start — Active User)** is explicitly defined, resolving the undefined `help`/`start` behavior for returning users from v0.2.
- **Failure behavior contract extended.** §9.7 (Storage Read Failure) and §9.6 (Concurrent Messages) added; §8.8 Concurrency NFR defined. Error response latency target added to §8.1. Cold-start latency bounded at 60 seconds.
- **16 risks** (up from 12 in v0.2) — four new risks added: concurrent message race conditions, chart timeout blocking, ephemeral system logs, keyword collision misrouting.
- **Storage model stated explicitly.** Embedded relational storage co-located with the bot process eliminates a network dependency and simplifies the free-tier model. This is an implementation-level decision but is appropriate to constrain at pre-architecture stage.

## 3. Structural Weaknesses

- **Duplicate internal actor introduced (new defect in v0.3).** The Actors table in §2 now contains both "Developer / Bot Owner" (carried from v0.2) and "Bot Operator / System Owner" (imported from v0.7's actor model). These two entries describe the same person performing overlapping operational roles. The duplicate actor was not present in v0.2 — it is a regression specific to v0.3.
- **Logical Consistency Check is factually wrong.** §15 explicitly states: "No. All three actors (Developer / Bot Owner, End User, Telegram Platform) are represented." The actual Actors table in §2 has four actors. The self-audit section has failed to detect its own subject matter. This undermines the credibility of the consistency check.
- **`is_synthetic` flag absent from Parameter entity attributes.** The Parameter entity definition in §4 lists: "Parameter ID, name, owning User ID, creation_at timestamp, last_entry_at timestamp, active/deleted status." The `is_synthetic` flag is not present. Yet §10.3 (Demo Data Isolation) mandates: "Demo parameters and their synthetic data created during onboarding are tagged with a `is_synthetic` flag." A security/isolation control requires an attribute that the entity model does not carry. This defect was present in v0.2 and has not been corrected in v0.3.
- **Contradiction in demo parameter modeling.** §4 Ownership notes states: "Demo parameters presented during onboarding are tagged as synthetic and **are not stored as real Parameter records**." §10.3 states they "are tagged with a `is_synthetic` flag." §13 Assumption A-03 states: "the `is_synthetic` tagging mechanism is applied at creation time." These three claims cannot simultaneously be true: if demo parameters are not real Parameter records, they cannot carry a `is_synthetic` flag on the Parameter entity. The nature of demo parameter storage is fundamentally undefined — are they stored as `is_synthetic = true` Parameter records, or as a different entity, or not stored at all?
- **MVP scope boundary remains unstable.** §1 explicitly states: "If the MVP scope is subsequently constrained, this system context document will require a targeted revision." Business Open Question 1 (minimum viable scope) is still unresolved at the business layer. A context document must define a stable boundary; conditional boundaries create downstream rework risk.
- **Storage model introduction is architectural leakage.** "Embedded relational storage co-located with the bot process" in §1, §3, §4, and Assumption A-10 specifies a technology class (embedded relational = a specific storage product family). While this is an appropriate constraint to define pre-architecture, embedding it in the system context document makes it a boundary assumption rather than an architecture decision — limiting the architect's freedom to consider alternatives.
- **ParseAttempt entity still has no lifecycle states.** ParseAttempt is modeled as an immutable audit record with a single terminal state. Yet ParseAttempts play an active role in the routing model (every inbound message creates one). The relationship between ParseAttempt (audit) and PendingClarification (state) entities is not formally associated at the entity level.
- **Period boundary definition absent from Flow 6 (Period Comparison).** The flow specifies "week or month" comparison periods but does not define what constitutes a "week" (e.g., Monday–Sunday) or a "month" (calendar month boundaries). Given the explicit protection against misleading comparisons, the period arithmetic must be defined at context level.

## 4. Boundary Violations

| Violation | Location | Severity |
|---|---|---|
| Duplicate internal actor ("Developer / Bot Owner" + "Bot Operator / System Owner") | §2 Actors table | **High** — two entries for the same person; Logical Consistency Check self-audit fails to detect this |
| `is_synthetic` attribute referenced in §10.3 but absent from Parameter entity in §4 | §4 vs. §10.3 | **High** — isolation control cannot be enforced at data model level |
| Demo parameter storage contradiction | §4 Ownership notes vs. §10.3 vs. A-03 | **High** — fundamental ambiguity about whether demo parameters exist as records, as tagged Parameter records, or not at all |
| Storage technology class specified in context document | §1, §3, §4, A-10 | **Low** — "embedded relational" constrains storage type; mild architectural leakage |
| Command keyword vocabulary in §5 | §5 | **Low** — specific reserved words are implementation constants; acceptable at pre-architecture stage |

## 5. State Model Issues

### Gaps
- **Parameter has no Archived state.** The Parameter lifecycle (Non-existent → Active → Deleted) has no intermediate "inactive but preserved" state. A user who wants to pause tracking without losing history must delete the parameter — a destructive-only option. v0.7 defines an Archived state for this purpose.
- **OnboardingSession "In Progress" has no forced terminal path.** Acknowledged in §15 as acceptable at portfolio scale but leaves a persistent incomplete record if the user never adds a real parameter.

### Overlaps
- **PendingClarification Abandoned state has two distinct entry paths** that produce the same state via different mechanisms: (a) user's clarification response fails to parse; (b) startup sweep marks all Open records Abandoned. The behavioral difference (case a: the new failed message is re-processed as a fresh input; case b: no further processing) is described in the flow but not distinguished in the state model entry conditions. An implementer reading only the state table cannot determine whether to re-process the message or not.

### Dead-ends
- None in the strict sense. All terminal states have explicit cascade or purge semantics.

### Unreachable States
- None identified.

## 6. Flow Integrity Issues

### Trigger Ambiguity
- **Flow 9 (First-Time Onboarding) vs. Command Dispatch (§5).** Flow 9 is triggered by "unrecognized Telegram ID." However, the dispatch priority order in §5 has no explicit step for "Is this user registered? If not, route to onboarding." The first-time user check is implicit — it must precede all dispatch steps but is not shown as a step in §5. A developer implementing the dispatch chain from §5 alone would not insert the registration check.
- **Flow 6 (Period Comparison) period arithmetic undefined.** "Week or month" comparison periods have no boundary definition. Monday–Sunday vs. any 7-day window; calendar month vs. rolling 30 days — these ambiguities could produce inconsistent comparison results across implementations.

### Responsibility Confusion
- **Flow 3 re-entry into §5 dispatch.** When a clarification response fails to parse, "the new message is then processed as fresh input through the dispatch model starting at step 2." This re-entrant dispatch is correct but creates a recursive reference between §5 and Flow 3. It is explicitly documented and bounded, but architects should treat the re-entry as a defined contract, not an implicit assumption.

### Circularity
- **Flow 2 → Flow 3 loop is bounded.** One-shot clarification with a fresh dispatch on failure; the loop terminates in a new PendingClarification if the response also fails to parse. No infinite recursion — each iteration produces a new ParseAttempt record.
- No other circular flows identified.

## 7. Entity Modeling Issues

### Duplication
- **ParseAttempt and PendingClarification cover overlapping territory.** Every PendingClarification is preceded by a ParseAttempt with outcome = failure, but no explicit foreign key or reference links the two. The relationship is described in narrative ("a failed ParseAttempt may produce a PendingClarification") but is not modeled as an entity-level association. This gap is carried forward from v0.2.

### Missing Attributes
- **Parameter entity:** `is_synthetic` flag is absent despite being required by §10.3, A-03, and the onboarding flow logic.
- **LogEntry entity:** `unit` attribute is listed in v0.3 (corrected from v0.2) ✓
- **User entity:** `onboarding_status` listed as an attribute but its value vocabulary is undefined; the OnboardingSession entity carries the same state — the authoritative source is ambiguous.

### Weak Relationships
- **LogEntry → ParseAttempt:** No foreign key or association attribute exists to trace a stored LogEntry back to the ParseAttempt that produced it. The audit trail from entry to origin is broken.
- **PendingClarification → LogEntry (on Resolved):** When a PendingClarification is marked Resolved, a LogEntry is created, but no relationship attribute on PendingClarification references the resulting LogEntry.
- **Demo parameters:** What entity stores them is undefined (see §3 boundary violation above). If they are not real Parameter records, they constitute an undocumented entity type.

## 8. Dependency Risks

| External System | Risk | Severity |
|---|---|---|
| Telegram Platform | Complete delivery channel failure; API policy change; rate-limit enforcement | Critical |
| Free Hosting Infrastructure | Runtime failure; storage eviction; data loss on tier eviction | High |

**Note:** The dependency table in §12 correctly includes Free Hosting Infrastructure — unlike v0.7 which omits it. The Telegram update delivery model (polling vs. webhook) is flagged as open decision SD-10 with appropriate hosting implications noted.

## 9. Scoring

| Dimension | Weight | Raw Score | Weighted Score | Comment |
|---|---|---|---|---|
| Boundary Clarity | x2 | 4 | 8 | Clean scope section; MVP instability caveat; storage technology leakage is mild |
| Actor Definition Quality | x1 | 2 | 2 | Duplicate internal actor ("Developer / Bot Owner" + "Bot Operator / System Owner"); Logical Consistency Check says 3 actors while table has 4 — regression from v0.2 |
| Entity Modeling Integrity | x1 | 3 | 3 | `is_synthetic` still missing on Parameter; demo parameter storage contradiction unresolved; ParseAttempt-PendingClarification relationship undefined |
| Flow Completeness | x2 | 4 | 8 | 12 flows; keyword collision rule; parameter matching; non-text rejection; first-time user check still implicit in dispatch |
| State Model Consistency | x2 | 4 | 8 | PendingClarification contradiction resolved; Abandoned has dual entry-path semantics not distinguished; Parameter no Archived state |
| Assumption Transparency | x1 | 4 | 4 | 11 assumptions (A-01 to A-11); A-10, A-11 newly added; validation plans present |
| Risk Coverage | x1 | 4 | 4 | 16 risks; 4 new risks added; unnumbered (unlike v0.7's numbered register) |
| Business Traceability | x1 | 4 | 4 | Fully verifiable against Business v0.3; all out-of-scope items correctly excluded; comprehensive traceability section |

**Total Score: 41 / 50**

## 10. High-Risk Structural Issues

| Issue | Impact | Probability | Severity |
|---|---|---|---|
| Duplicate internal actor ("Developer / Bot Owner" and "Bot Operator / System Owner") | Context diagram will show two actors for one person; architect cannot determine which role governs which decision | Certain — both are in the table | High |
| Logical Consistency Check says 3 actors while table has 4 | Self-audit produces wrong output; undermines trust in §15 as a quality gate | Certain — inconsistency confirmed | High |
| `is_synthetic` absent from Parameter entity; demo parameter storage undefined | Demo data isolation control cannot be enforced; synthetic data may contaminate real analytics | Certain — attribute is missing; storage model is contradictory | High |
| First-time user routing step implicit in dispatch model | New users may bypass onboarding if a command keyword is their first message | Medium — keyword-first routing could skip registration check | Medium |
| Period arithmetic undefined in Flow 6 | Week/month comparison boundaries are implementation-defined; results will vary across implementations | Medium — ambiguity is real but contained to one flow | Medium |

## 11. Mandatory Revisions

1. **Remove "Bot Operator / System Owner" from the Actors table.** Merge its responsibilities into the existing "Developer / Bot Owner" actor row, which already covers deployment, operation, and maintenance. Update §15 Logical Consistency Check to accurately reflect that the document has three actors.
2. **Add `is_synthetic` attribute to the Parameter entity definition in §4** — or explicitly define that demo parameters are NOT stored as Parameter records and clarify what entity type (if any) stores them. The contradiction between "not stored as real Parameter records" and "tagged with `is_synthetic` flag" must be resolved definitively.
3. **Add a first-time user routing step as Step 0 in the Command Dispatch priority order (§5).** The check "Is this Telegram ID registered? If not, route to Flow 9 (First-Time Onboarding)" must appear explicitly before all other dispatch steps — not as an implicit assumption in the flow description.
4. **Define period boundary definitions for Flow 6 (Period Comparison).** State what constitutes a "week" (e.g., Monday 00:00 UTC – Sunday 23:59 UTC) and a "month" (e.g., calendar month start/end UTC). The comparison logic must be deterministic.
5. **Resolve Business Open Question 1 (minimum viable scope)** before treating this document as final. Until the business scope boundary is stable, the system context document is conditionally defined.
6. **Define the formal association between ParseAttempt and PendingClarification** in the entity table — add a reference attribute or note making the relationship explicit at entity level.
7. **Distinguish the two entry conditions of PendingClarification Abandoned state** in the state model table. The behavioral consequence differs: a failed-parse abandonment re-processes the new message; a startup-sweep abandonment does not. Implementers must know which applies.

## 12. Iteration Recommendation

**Accept with Minor Adjustments**

System v0.3 has resolved all ten mandatory revisions from its review cycle and introduces meaningful additions (keyword collision rule, parameter name matching, non-text rejection, input sanitization, operator disclosure, account deletion enforcement, Flow 12). The document is substantially improved over v0.2. However, the duplicate actor introduction is a regression that must be corrected before architecture handoff — it will produce an incorrect context diagram. The `is_synthetic` gap and demo parameter contradiction are correctness defects, not style issues. A targeted revision addressing the 7 mandatory items above would complete this document to a strong baseline.

---
---

# Comparative Summary

## Side-by-Side Scoring

| Dimension | Weight | v0.7 Raw | v0.7 Weighted | v0.3 Raw | v0.3 Weighted |
|---|---|---|---|---|---|
| Boundary Clarity | x2 | 3 | 6 | 4 | 8 |
| Actor Definition Quality | x1 | 2 | 2 | 2 | 2 |
| Entity Modeling Integrity | x1 | 4 | 4 | 3 | 3 |
| Flow Completeness | x2 | 5 | 10 | 4 | 8 |
| State Model Consistency | x2 | 4 | 8 | 4 | 8 |
| Assumption Transparency | x1 | 4 | 4 | 4 | 4 |
| Risk Coverage | x1 | 5 | 5 | 4 | 4 |
| Business Traceability | x1 | 3 | 3 | 4 | 4 |
| **TOTAL** | | | **42 / 50** | | **41 / 50** |

Both documents fall in the **40–44 range: Acceptable baseline — Accept with Minor Adjustments.**

---

## Structural Profile Comparison

| Property | v0.7 | v0.3 |
|---|---|---|
| Business baseline | v0.5 (unavailable — unverifiable) | v0.3 (available — verified) |
| Alerts in scope | Yes (scope reversal unverifiable) | No (per D-05 — correct) |
| Target user scale | ~10 users | ~100 users |
| Actor count | 8 (5 internal components — leakage) | 4 (1 duplicate — regression) |
| Actors conforming to context model | 3 (Bot Operator, End User, Telegram) | 3 (Developer, End User, Telegram) |
| Entity count | 6 (incl. MetricActivityStatus) | 6 (incl. OnboardingSession) |
| `is_synthetic` on Parameter | Present on Entry | **Missing** |
| Demo parameter storage model | Implicit | **Contradictory** (§4 vs §10.3) |
| ParseAttempt lifecycle | 4 states (Pending/Resolved/Deferred/Expired) | 1 state (Recorded — immutable) |
| PendingClarification lifecycle | Described via ParseAttempt resolution | Full 3-state model (Open/Resolved/Abandoned) |
| Flow count | 11 primary + 4 sub-flows | 12 flows (no sub-flows) |
| Compound entries / dimension naming | Yes (§13) | No (out of scope) |
| Metric Archived state | Yes | No |
| Alert state model | Yes (4 states) | No (alerts out of scope) |
| Alert Archived state reachable | **No — unreachable** | N/A |
| Keyword collision disambiguation | Implicit in flow triggers | **Explicit named rule (§5)** |
| Parameter name matching strategy | Implicit | **Explicit named strategy (§5)** |
| Non-text input rejection | Not defined | **Explicit pre-dispatch gate (§5, §10.6)** |
| Input sanitization | Not defined | **Mandatory NFR (§8.7, §10.5)** |
| Operator disclosure in onboarding | Not defined | **Mandatory, tracked by entity flag** |
| Help flow for Active users | Not defined | **Flow 12** |
| Concurrency NFR | Not addressed | **§8.8, §9.6** |
| Storage type specified | Not specified | **Embedded relational (§1, §3, A-10)** |
| Account deletion enforcement | Scheduled process (mechanism unspecified) | **Startup sweep (§9.5) fully defined** |
| Storage read failure contract | Not defined | **§9.7** |
| Update delivery model (polling/webhook) | Not mentioned | **SD-10 (open decision tracked)** |
| Risk count | 19 (numbered) | 16 (unnumbered) |
| Uncertainty register | 8 items (SU-001 to SU-008) | Implicit only |
| Free Hosting in dependencies | **Missing** | Present |
| Logical Consistency Check | Accurate | **Self-audit count wrong (3 vs. 4 actors)** |

---

## Key Divergences

### 1. Actor Model — Both Documents Have Actor Problems, Different Causes

Both documents score 2/5 on Actor Definition Quality but for different reasons:

- **v0.7** lists five internal subsystems as actors, violating the context modeling principle that actors must be external to the system boundary. This is an architectural philosophy problem — internal components do not belong in the context perimeter.
- **v0.3** introduces a duplicate actor by carrying forward "Developer / Bot Owner" from v0.2 while importing "Bot Operator / System Owner" from v0.7, creating two entries for the same person. Worse, the Logical Consistency Check in §15 performs a self-audit and reaches the wrong conclusion (three actors vs. four in the table). This is a quality control failure.

**Net assessment:** v0.7's actor problem is structural and systematic (five violations). v0.3's actor problem is a single copy-paste error — easier to fix but more embarrassing given the self-audit failure.

### 2. Flow Completeness — v0.7 Is Deeper; v0.3 Is More Operational

v0.7 provides sub-flows for ParseAttempt disambiguation (3a), deferral and late categorisation (3b), alert reconfiguration (6a), and account restoration (10a) — a higher level of precision for the architect. v0.3 adds flows absent from v0.7's scope: Flow 12 (Help for Active Users), non-text input rejection, and keyword collision disambiguation. Neither document is strictly superior — they address different scope and operational concerns.

### 3. Entity Modeling — `is_synthetic` Gap Persists Across Pipeline

The `is_synthetic` attribute on the Parameter entity is absent in both v0.2 and v0.3 — a defect that has now survived two full iteration cycles without correction. v0.3 actually introduces a worse form of the problem: the ownership note says demo parameters "are not stored as real Parameter records" while §10.3 and A-03 say they ARE tagged with `is_synthetic`. v0.7 does not share this contradiction. This is the most persistent entity modeling failure in the v0.3 pipeline.

### 4. Operational Specificity — v0.3 Leads

v0.3 defines significantly more operational behavior that v0.7 does not address at all: startup sweep enforcement for account deletion, storage read failure contracts, per-user message serialization, chart timeout enforcement, non-text rejection, input sanitization, operator disclosure tracking, keyword collision rules, and parameter name matching strategy. These additions make v0.3 operationally more complete for a developer building the system from the context document alone.

### 5. Business Traceability — v0.3 Leads

v0.3 is fully auditable against an available business document. Every scope decision, out-of-scope item, and success metric traces back to Business v0.3. v0.7's scope changes (alert reversal, user count reduction) cannot be verified without Business v0.5. For a review board, unverifiable traceability is a meaningful quality gap.

### 6. Depth vs. Correctness

v0.7 is deeper (more flows, sub-flows, a complete alert lifecycle, a dimension naming convention, a numbered risk register, an uncertainty register). v0.3 is more operationally correct for its defined scope, more tightly traced to a verified business baseline, and more complete in failure behavior, security controls, and observability. The two documents represent different maturity axes: **v0.7 achieves greater architectural depth; v0.3 achieves greater operational correctness and traceability**.

---

## Recommendations

| Document | Score | Recommendation |
|---|---|---|
| system_analysis_v0.7.md | **42 / 50** | **Accept with Minor Adjustments** — Correct internal actor boundary violations; add Free Hosting to dependency table; resolve Alert Archived reachability; define alert evaluation on Archived Metrics; supply cross-reference to Business v0.5 |
| system_v0.3.md | **41 / 50** | **Accept with Minor Adjustments** — Remove duplicate actor; correct Logical Consistency Check; resolve `is_synthetic` entity contradiction; add first-time user step to dispatch model; define period boundary arithmetic; formalize ParseAttempt→PendingClarification relationship |

> **Forward path recommendation:** v0.3 is the correct document to carry forward in the active pipeline — its business traceability is verified, its scope is correct, and its operational specificity is high. Apply the 7 mandatory revisions above, then selectively incorporate v0.7's architectural depth elements that are appropriate for this scope: a numbered risk register with IDs, a structured uncertainty register, and richer sub-flow detail for the ParseAttempt and account deletion flows. Do not import v0.7's alert scope, actor model, or MetricActivityStatus entity without first confirming these against an updated and approved business document.
