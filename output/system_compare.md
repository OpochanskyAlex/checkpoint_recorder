# System Context Document — Comparative Review Report

> **Reviewed Documents:**
> - Document A: `old/system_analysis_v0.7.md` — System Context Document v0.7 (Based on Business v0.5)
> - Document B: `output/system/system_v0.2.md` — System Context Document v0.2 (Based on Business v0.3)
> - Business Reference Used: `output/business/business_v0.3.md`
> - Review Date: 2026-03-29

---

## Preface: Scope of This Review

Both documents describe the same underlying system — a Telegram-native personal metric tracking bot — but represent **distinct pipeline lineages**:

- **v0.7** is the result of a longer, multi-cycle iteration chain through Business v0.5 (not available in this repository). It introduces alerts, multi-value compound entries, dimension naming conventions, and MetricActivityStatus as a formal entity.
- **v0.2** is the output of the current pipeline, traced directly to Business v0.3 (available and verified). It excludes alerts (per D-05), uses a simpler entity model, and adds a Command Dispatch Model and Failure Behavior Contract.

Because the v0.7 document references Business v0.5 — which is not present in this repository — some traceability claims cannot be fully verified. All such gaps are explicitly flagged.

---

---

# DOCUMENT A — System Review Report: v0.7

## Reviewed Version
v0.7 (Based on Business Analysis v0.5 — **not available for cross-reference**)

## 1. Executive Assessment

System Context Document v0.7 is a mature, dense, and highly detailed specification with excellent flow coverage, complete state lifecycle modeling, and a comprehensive risk register. It demonstrates strong engineering discipline: transactional semantics, cascade atomicity requirements, a privacy note for `raw_input`, and a Logical Consistency Check all appear explicitly. However, the document contains a structurally significant problem: **internal subsystem components are modeled as actors**, which leaks architectural decomposition decisions into the context layer — a boundary violation that contaminates actor definitions and creates premature dependency assertions. Additionally, the scale ceiling has been reduced from approximately 100 users (Business v0.3) to approximately 10 users, and alerts — explicitly confirmed as out of scope in Business v0.3 — appear as core functionality, suggesting a scope change that cannot be verified without Business v0.5.

## 2. Structural Strengths

- **Flow completeness is exceptional.** Eleven primary flows plus four sub-flows (3a, 3b, 6a, 10a) are defined with triggers, inputs, step-by-step processing, outputs, and per-step risk points. Transactional semantics are explicitly defined per scenario in §8.3.
- **State models are complete and unambiguous.** All six entity state models (InternalUser, Metric, Entry, Alert, ParseAttempt, and an implicit Expired terminal) have mutually exclusive states, defined entry/exit conditions, and no unreachable or dead-end states.
- **Risk register is comprehensive.** Nineteen numbered risks with ID, type, impact, probability, and mitigation — the most complete risk coverage of either document.
- **Uncertainty register (SU-001 through SU-008)** explicitly defers unresolved system design questions to the architecture stage with validation plans, preventing premature resolution.
- **`raw_input` Privacy Note** in §4 is a structurally honest disclosure — it identifies the residual privacy risk, defines its scope relative to D-007, and prescribes a retention/purge policy. This is exemplary for a portfolio-scope document.
- **Decision Log** is rich (15+ decisions) with version-stamped status and clear resolution states for SD-003, SD-004, and SD-007.
- **ParseAttempt Deferred state (SD-007)** is correctly modeled as a resting non-terminal state, not a failure terminal — preserving user intent and audit integrity.
- **Cascade atomicity requirements** are explicitly stated for both account deletion (Flow 10) and metric deletion (Flow 11).

## 3. Structural Weaknesses

- **Internal subsystems listed as Actors (§2) — architectural leakage.** NLP Parsing Component, Alert Evaluation Component, Chart Rendering Component, Logging / Observability Component, and Data Persistence Layer are classified as "Internal" actors in the Actors table. At the context layer, actors are external agents and human roles that interact with the system boundary. Internal subsystems are implementation constructs that belong inside the system box — not at the context perimeter. This creates confusion about what is inside vs. outside the system, contradicts the system boundary definition in §3, and constitutes premature architectural decomposition.
- **Scale discrepancy with available business documentation.** Business v0.3 states the system targets "maximum approximately 100 users." This document specifies approximately 10 users. The change is not explained in the Changes Introduced section. Without Business v0.5 for verification, this represents an unverifiable scope reduction.
- **Alerts in scope — cannot be verified against available business docs.** Business v0.3 (D-05) explicitly confirms "Threshold alerts are out of scope." This document includes alerts as a core feature across entities (Alert), flows (5, 6, 6a, 9), and state models. While this may have been reversed in Business v0.5, that document is unavailable for review — making this a **traceability gap of high severity**.
- **MetricActivityStatus as a formal entity** introduces a computed aggregate into the entity model at the context level. This is more appropriate as a view or derived projection at the design/data model layer. Its presence as a first-class entity adds modeling complexity without a corresponding user-facing interaction that requires it to be independently addressable.
- **Metric Archived state alert evaluation behavior is deferred (SU-004)** — but the Alert State Model shows Archived Metrics can still have Active alerts. Whether evaluation continues is left undefined, creating a behavioral gap that could produce silent alert failures or unexpected notifications.

## 4. Boundary Violations

| Violation | Location | Assessment |
|---|---|---|
| Internal components modeled as Actors | §2 Actors table | **High severity.** NLP Parsing, Alert Evaluation, Chart Rendering, Logging/Observability, and Data Persistence are inside the system boundary per §3. Listing them as actors violates the C4 context modeling principle that actors are external entities. |
| MetricActivityStatus as a context-level entity | §4 Core Entities | **Low-medium severity.** Derived computational state belongs at the design layer, not the context entity model. It is not an independently addressable data record from the user's perspective. |
| Periodicity boundary and period arithmetic definitions (§12) | §12 | **Low severity.** UTC boundary definitions and "last 5 periods" computation rules are implementation details. Acceptable in a pre-architecture document but constitute mild architectural leakage. |

## 5. State Model Issues

### Gaps
- **Alert on Archived Metric:** The Metric state model shows Archived metrics can still have associated Alerts in Active state. The Alert State Model does not define whether alert evaluation is suspended for Archived metrics (SU-004). This is a behavioral gap — an alert may fire on a metric the user considers inactive.

### Overlaps
- None identified. States across all models are mutually exclusive.

### Dead-ends
- None. All terminal states (Deleted, Expired, Resolved) are explicitly terminal with cascade semantics defined.

### Unreachable States
- **Alert Archived state:** The Alert State Model lists Archived as a valid state (entry condition: "User archives alert"). However, no flow in §5 defines a "user archives an alert" command. Flow 9 handles Alert Deletion. Flow 6a handles re-arming. There is no "archive alert" flow. Archived is effectively unreachable as modeled.

## 6. Flow Integrity Issues

### Trigger Ambiguity
- **Flow 4 (Chart Request):** The trigger references "a metric name" but does not define the behavior when the metric name provided does not match any existing metric. Only the "insufficient data" case is explicitly handled. The "metric not found" case has no defined response.
- **Flow 3 (Ambiguous Entry) vs. Flow 2 (Standard Entry):** The confidence threshold that separates "sufficient confidence" (Flow 2) from "ambiguous" (Flow 3) is deferred to SU-002. This is an acceptable deferral but means the dispatch decision between Flows 2 and 3 has no deterministic definition at context level.

### Responsibility Confusion
- **Internal actors in flows:** Because internal components are listed as actors, flows assign steps to "NLP Parsing Component does X" and "Alert Evaluation Component does Y" — this is internal process narration, not context-level flow description. The boundary between context-level behavior and internal mechanism narration is blurred throughout.

### Circularity
- None. Flow 2 → Flow 5 (alert evaluation post-entry) is linear. ParseAttempt Deferred → Late Categorisation is a bounded loop (Flow 3b). Alert re-arming (Flow 6a) is a user-initiated action, not an automatic loop.

## 7. Entity Modeling Issues

### Duplication
- None identified.

### Missing Attributes
- **Alert entity:** No `created_timestamp` attribute is defined, even though alert history or audit tracing would require it.
- **MetricActivityStatus:** The `computation_timestamp` attribute is defined, but no `last_entry_timestamp_at_computation` is included — making it impossible to determine whether a stored MetricActivityStatus is stale without joining to the Entry table.

### Weak Relationships
- **ParseAttempt → Metric:** The relationship lists `candidate_metrics` as a ranked list of metric_ids, but the relationship between a Deferred ParseAttempt and a specific Metric is not formalized. If the user later deletes the candidate metric before categorising the ParseAttempt, the cascade behavior in Flow 11 handles this — but the relationship cardinality at entity level is not explicit.

## 8. Dependency Risks

| External System | Risk | Severity |
|---|---|---|
| Telegram Bot API | Complete delivery channel failure; API policy change invalidates bot behavior | Critical |
| Telegram Infrastructure | Image delivery failure for charts; rate-limit enforcement | High |
| NLP Parsing Component (internal — listed as actor) | Parse accuracy below 85% degrades core value proposition | High (internal, not a true external dependency) |
| Scheduled Process (Retention/Deletion) | If absent, PendingDeletion accounts are never purged; D-013 retention obligation unmet | Medium |
| Free Hosting Infrastructure | Not explicitly listed in §7 External Dependencies — **omission noted** | Medium |

**Notable omission:** Free hosting infrastructure is not listed in the External Dependencies table (§7) despite being a critical runtime dependency, a data durability risk (R-013), and a cost constraint (Business v0.3). This is the same level of risk as Telegram but is absent from §7.

## 9. Scoring

| Dimension | Weight | Raw Score | Weighted Score | Comment |
|---|---|---|---|---|
| Boundary Clarity | x2 | 3 | 6 | Internal subsystems as actors violates context-layer boundary; scale discrepancy unverifiable |
| Actor Definition Quality | x1 | 2 | 2 | Five of eight actors are internal components — architectural leakage |
| Entity Modeling Integrity | x1 | 4 | 4 | Rich entity definitions; minor gaps (Alert created_timestamp; MetricActivityStatus as entity) |
| Flow Completeness | x2 | 5 | 10 | Exceptional coverage — 11 primary + 4 sub-flows; transactional semantics; per-step risks |
| State Model Consistency | x2 | 4 | 8 | Complete and mutually exclusive; Alert Archived unreachable; Archived-Metric alert behavior gap |
| Assumption Transparency | x1 | 4 | 4 | 10 explicit assumptions with risk and validation plans |
| Risk Coverage | x1 | 5 | 5 | 19 numbered risks — the most comprehensive risk register of both documents |
| Business Traceability | x1 | 3 | 3 | Alerts scope reversal and scale reduction unverifiable without Business v0.5 |

**Total Score: 42 / 50**

## 10. High-Risk Structural Issues

| Issue | Impact | Probability | Severity |
|---|---|---|---|
| Internal components listed as Actors | Architects treating internal components as external dependencies; boundary confusion in downstream design | Certain — already present | High |
| Alerts scope reversal unverifiable | Incorrect scope baseline reaches architecture if Business v0.5 does not actually reverse D-05 | Low (v0.5 likely reversed it, but unverifiable) | High |
| Free hosting infrastructure absent from dependency table | Operational and data durability risk invisible to architects reviewing §7 | Certain — omission is present | Medium |
| Alert Archived state unreachable | Architects may implement archive-alert functionality with no user-facing flow; dead code risk | Medium | Medium |
| Alert behavior on Archived Metrics undefined (SU-004) | Users with active alerts on archived metrics may receive unexpected notifications or silent misfires | Medium | Medium |

## 11. Mandatory Revisions

1. **Remove internal subsystem components from the Actors table.** NLP Parsing Component, Alert Evaluation Component, Chart Rendering Component, Logging / Observability Component, and Data Persistence Layer belong inside the system boundary, not in the actor registry. Replace with a "Key Internal Components" note in §3 if needed, but do not model them as actors at context level.
2. **Add Free Hosting Infrastructure to External Dependencies (§7)** with the same rigor as the Telegram entries — purpose, dependency type, risk level, and failure consequence.
3. **Resolve the Alert Archived state.** Either define an "archive alert" flow in §5, or remove Archived from the Alert State Model and collapse it into Deleted.
4. **Clarify SU-004 (Alert evaluation on Archived Metrics).** This is not a deferred system design decision — it is a behavioral contract that must be defined at context level so architects know what rule to implement.
5. **Add a cross-reference note** explaining the scope changes from Business v0.3 (alerts out of scope, ~100 users) to this document (~10 users, alerts in scope), pointing to Business v0.5 as the authoritative source. Without this, readers of both documents will encounter unresolved contradictions.
6. **Add `created_timestamp` to the Alert entity attributes.**

## 12. Iteration Recommendation

**Accept with Minor Adjustments**

The document is structurally sound in flow coverage, state modeling, risk awareness, and decision traceability. The actor-boundary violation and dependency table omission are real structural defects but do not require a full rework — they require targeted corrections. The traceability gap (Business v0.5 unavailable) is a process concern, not a structural modeling failure.

---

---

# DOCUMENT B — System Review Report: v0.2

## Reviewed Version
v0.2 (Based on Business Analysis v0.3 — **available and verified**)

## 1. Executive Assessment

System Context Document v0.2 is a well-structured, scope-appropriate specification fully traceable to Business v0.3. It correctly excludes alerts (per D-05), maintains the 100-user scale, and introduces two structurally valuable additions not present in v0.7: a Command Dispatch Model (§5) that eliminates ambiguity about intent routing, and a Failure Behavior Contract (§9) that makes failure semantics explicit. However, several modeling deficiencies undermine its structural integrity: the ParseAttempt entity has no lifecycle states despite being a routing decision-maker; the `is_synthetic` flag referenced in §10.3 is absent from the Parameter entity definition; the Command Dispatch Model contains no first-time-user routing step; and the MVP scope caveat in §1 creates an explicit boundary instability that the document itself acknowledges but does not resolve.

## 2. Structural Strengths

- **Full traceability to available business documentation.** All decisions, constraints, and out-of-scope items map directly to Business v0.3. Alerts correctly excluded. Scale consistent. Decision log entries traceable.
- **Command Dispatch Model (§5)** is a structurally valuable addition that makes intent routing explicit, defines dispatch priority order, and eliminates ambiguity about which flow handles which message type.
- **Failure Behavior Contract (§9)** explicitly specifies behavior for storage write failure, chart failure, bot restart with open clarifications, and sparse comparison data — closing a common gap in system context documents.
- **Security and Data Controls (§10)** cover data isolation enforcement, secrets handling, demo data isolation, and operator data access transparency — all appropriate at context level.
- **Observability Model (§11)** traces each business success metric to a specific signal and measurement method, making measurement accountability explicit.
- **Logical Consistency Check (§15)** is an honest self-audit — it identifies the OnboardingSession "In Progress" lifecycle gap and the PendingClarification race condition resolution, and explicitly notes residual ambiguities.
- **Actor model is clean and context-appropriate.** Three actors only (Developer/Bot Owner, End User, Telegram Platform) — no architectural leakage.
- **Entity lifecycle notes** are included below the entity table and are clear about immutability, purge semantics, and transient states.

## 3. Structural Weaknesses

- **ParseAttempt entity has no lifecycle states.** ParseAttempt is described as "a record of every attempted parse... created for all inbound messages regardless of outcome" and its state model shows only one terminal state (Recorded → immutable). Yet the Command Dispatch Model (§5, Step 1) routes incoming messages through a "Pending Clarification Check" — which is actually the PendingClarification entity, not the ParseAttempt. The relationship between ParseAttempt (audit record) and PendingClarification (transient state) is architecturally correct but creates naming and conceptual confusion: two entities track partially overlapping concerns with no explicit relationship defined between them.
- **`is_synthetic` flag is absent from the Parameter entity definition (§4)** despite being required by §10.3 (Demo Data Isolation): "Demo parameters and their synthetic data created during onboarding are tagged with a `is_synthetic` flag." The Parameter entity in §4 has no such attribute. This is an entity inconsistency — a control required in §10.3 has no model-level support in §4.
- **The Command Dispatch Model (§5) has no first-time-user routing step.** The dispatch order is: (1) PendingClarification check, (2) Pending Deletion check, (3) keyword match, (4) log intent. There is no step that checks "is this user registered? If not, route to onboarding." Flow 9 (First-Time Onboarding) is triggered by an "unrecognized Telegram ID" but the mechanism by which this is detected and routed is not represented in the dispatch model. The onboarding trigger is implicit and disconnected from the defined dispatch chain.
- **MVP scope caveat creates boundary instability (§1).** The note "if the MVP scope is subsequently constrained, this system context document will require a targeted revision" is honest but structural: it means the system boundary is conditionally defined. A context document must define a stable boundary even if the full boundary is later narrowed. The MVP scope question (Business Open Question 1) should be resolved before finalizing the context document.
- **`help`/`start` command routing is undefined.** The dispatch table routes `help` and `start` to "Onboarding or help text" — but no Help flow exists in §6. The onboarding content and help content are not distinguished. If a returning Active user sends `/help`, the behavior is unspecified.
- **Period Comparison (Flow 6) lacks precision on period definition.** The flow does not specify what constitutes a "comparable period" (week vs. month) in terms of calendar boundaries. The only boundary definition in the document is the informal "(week or month)" in the trigger. For a flow explicitly guarding against misleading comparisons, the period arithmetic must be defined.

## 4. Boundary Violations

| Violation | Location | Assessment |
|---|---|---|
| Command keyword vocabulary in §5 | §5 Command Dispatch Model | **Low severity.** Specific keywords (`list`, `history`, `chart`, etc.) are implementation constants. Acceptable in a pre-architecture document but constitute mild leakage of implementation detail into the context layer. |
| `is_synthetic` control referenced but not modeled | §10.3 vs. §4 | **Medium severity.** A security/isolation control (demo data tagging) references an attribute that does not exist in the entity definition. The control cannot be enforced if the data model does not support it. |

## 5. State Model Issues

### Gaps
- **Parameter has no Archived state.** Parameter lifecycle is: Non-existent → Active → Deleted. There is no intermediate "inactive but preserved" state. This means a user who wants to pause tracking without losing history must delete the parameter. This is a missing lifecycle state compared to the full spectrum of user intent.
- **OnboardingSession "In Progress" has no forced exit.** Acknowledged in §15 as a "non-blocking incomplete state." Structural observation: a session that can persist indefinitely without completing creates an orphaned record type. At portfolio scale this is acceptable, but the data model has no cleanup trigger for In-Progress sessions.
- **ParseAttempt has no mutable lifecycle.** The state model shows ParseAttempt as a single terminal state (Recorded). But PendingClarification, which is a related transient state, has a full lifecycle (Open → Resolved | Abandoned). The two entities cover overlapping territory — every ParseAttempt that results in a clarification creates a PendingClarification, but the relationship between the two is not modeled as an explicit association.

### Overlaps
- **PendingClarification Abandoned state has two entry conditions** that produce the same state via different triggers: (a) user sends any new message while clarification is Open, and (b) user's clarification response itself fails to parse. Both map to Abandoned, but the behavioral consequence differs slightly — in case (b), the new message also triggers a new ParseAttempt. The state model does not distinguish these entry paths, which may confuse implementers.

### Dead-ends
- None in the strict sense. All terminal states have defined cascade or purge semantics.

### Unreachable States
- None identified.

## 6. Flow Integrity Issues

### Trigger Ambiguity
- **Flow 9 (Onboarding) vs. Command Dispatch (§5):** Flow 9 is triggered by "unrecognized Telegram ID" but this check does not appear in the Command Dispatch priority chain. There is no defined step in §5 that routes an unregistered user to Flow 9 before any other processing. The implicit assumption is that onboarding precedes dispatch — but this assumption is not stated.
- **Flow 4 (Parameter History Query):** The trigger is "message matched to history/log keyword(s)." But `log` appears in both the keyword match list (routing to history) and implicitly in log-intent messages (default routing). A message like "log weight 82" could be interpreted as either a `log` keyword match (routing to history) or a log-intent (routing to Flow 1). The disambiguation is not defined.
- **`help`/`start` routing:** No flow is defined for these keywords. The dispatch table references "Onboarding or help text" but the target behavior differs for a new user vs. a returning user. A registered Active user sending `help` has no defined response.

### Responsibility Confusion
- **Flow 3 (Clarification Resolution) delegates to §5 Dispatch for re-processing.** The flow states "the incoming message is sent to the clarification resolution handler; the Open PendingClarification is marked Abandoned; the new message is then processed as a fresh input through the dispatch model (steps 2–4)." This is correct but creates a recursive reference between §5 (Dispatch) and Flow 3 — acceptable but should be explicitly noted as re-entry into the dispatch chain, not a new flow.

### Circularity
- **Flow 2 → Flow 3 loop is bounded** (one-shot clarification; second failure creates a new ParseAttempt). No true circular dependency.
- No other circular flows identified.

## 7. Entity Modeling Issues

### Duplication
- **ParseAttempt and PendingClarification cover overlapping concerns.** ParseAttempt records every parse attempt (audit); PendingClarification tracks the transient follow-up state for failed parses. There is no explicit relationship (foreign key or reference) between the two entities. A developer implementing this model must infer the link. The entity table does not define this relationship.

### Missing Attributes
- **Parameter entity:** Missing `is_synthetic` flag (required by §10.3).
- **User entity:** The `onboarding_status` attribute is listed but its vocabulary (values/states) is not defined in the entity table. The OnboardingSession entity carries similar state — the two are redundant without explicit delineation of which is the authoritative source.
- **LogEntry entity:** No `unit` attribute is listed in Key Attributes, despite being referenced in Flow 1 processing ("captures unit if present") and in the parse engine description.

### Weak Relationships
- **LogEntry → ParseAttempt:** The entity table states "a successful ParseAttempt produces a LogEntry" but there is no foreign key or association attribute on either entity to represent this. Audit tracing from a LogEntry back to its originating ParseAttempt is structurally undefined.
- **PendingClarification → LogEntry:** The state model states "Resolved → produces a LogEntry" but no relationship attribute exists on PendingClarification to reference the resulting LogEntry.

## 8. Dependency Risks

| External System | Risk | Severity |
|---|---|---|
| Telegram Platform | Complete delivery channel failure; API policy change; rate-limit enforcement | Critical |
| Free Hosting Infrastructure | Runtime failure; storage eviction; data loss on tier expiry | High |

**Note:** The dependency table in §12 is accurate and appropriately scoped. Free Hosting Infrastructure is correctly included, unlike in v0.7.

## 9. Scoring

| Dimension | Weight | Raw Score | Weighted Score | Comment |
|---|---|---|---|---|
| Boundary Clarity | x2 | 4 | 8 | Clean actor model; `is_synthetic` inconsistency; MVP caveat creates instability |
| Actor Definition Quality | x1 | 4 | 4 | Appropriate 3-actor context model; no architectural leakage |
| Entity Modeling Integrity | x1 | 3 | 3 | Missing `is_synthetic` on Parameter; LogEntry missing `unit`; undefined ParseAttempt-PendingClarification relationship |
| Flow Completeness | x2 | 3 | 6 | Good coverage but dispatch-onboarding gap; `log` keyword ambiguity; undefined help flow |
| State Model Consistency | x2 | 3 | 6 | No Parameter Archived state; ParseAttempt has no lifecycle; PendingClarification entry-condition overlap |
| Assumption Transparency | x1 | 4 | 4 | 9 assumptions with risk and validation; honest about gaps |
| Risk Coverage | x1 | 4 | 4 | 12 risks; appropriate for scope; cold-start risk correctly identified |
| Business Traceability | x1 | 4 | 4 | Fully verifiable against Business v0.3; all out-of-scope items correctly excluded |

**Total Score: 39 / 50**

## 10. High-Risk Structural Issues

| Issue | Impact | Probability | Severity |
|---|---|---|---|
| `is_synthetic` flag absent from Parameter entity | Demo data isolation control in §10.3 cannot be enforced at data model level; synthetic data may contaminate real analytics | Certain — the attribute is missing | High |
| Dispatch model has no first-time-user routing step | Onboarding may be silently bypassed if a new user sends a keyword command as their first message | Medium — keyword-first dispatch could route new users past onboarding | High |
| `log` keyword ambiguity in dispatch table | "log weight 82" may be ambiguously routed to History Query instead of Log Intent | Medium — "log" as a keyword conflicts with log-intent default routing | Medium |
| ParseAttempt-PendingClarification relationship undefined | Implementers cannot trace a LogEntry back to its originating ParseAttempt; audit chain is broken | Certain — association is absent from entity model | Medium |
| MVP scope boundary unstable | System boundary may change after context document is finalized, invalidating architecture work downstream | Medium — Open Question 1 remains unresolved at business layer | Medium |

## 11. Mandatory Revisions

1. **Add `is_synthetic` attribute to the Parameter entity definition (§4).** This attribute is required by the isolation control in §10.3 and must be formally modeled.
2. **Add a "first-time user" routing step to the Command Dispatch Model (§5)** as Step 0 (or Step 1, highest priority): check if the Telegram ID maps to an existing User record; if not, route to Flow 9 (Onboarding) before any other dispatch. This step must precede all other checks.
3. **Remove or rename `log` from the keyword vocabulary in §5.** The keyword `log` conflicts with log-intent default routing. If `log` is intended as a history query keyword, it must be clearly distinguished from log-intent messages (e.g., "log 82 weight"). If it is not a history keyword, remove it from the keyword table.
4. **Define a `help` flow (or explicitly reference the onboarding message as the help content)** for returning Active users who send `help` or `start`. The dispatch table must map to a defined flow, not an undefined handler.
5. **Add `unit` to the LogEntry entity attributes** to match the processing logic in Flow 1 and the parse engine description.
6. **Define the explicit relationship between ParseAttempt and PendingClarification** in the entity table — either as a foreign key attribute or a relationship note. Add a similar relationship from PendingClarification to the resulting LogEntry (when Resolved).
7. **Add a period boundary definition to Flow 6 (Period Comparison)** — specify what constitutes a "week" and a "month" boundary (e.g., Monday–Sunday for week; calendar month start/end) for comparison purposes.
8. **Resolve or close the MVP Scope Open Question (Business Open Question 1) before finalizing this document.** The system boundary must be stable before architecture begins.

## 12. Iteration Recommendation

**Iterate (Model Refinement Needed)**

The document has strong structural bones — appropriate actor model, full business traceability, valuable additions in Dispatch Model, Failure Behavior Contract, and Observability Model. However, the entity inconsistency (`is_synthetic`), dispatch model gap (first-time user routing), and keyword ambiguity (`log`) are correctness defects, not style issues. These must be addressed before the document is handed to an architect. A targeted revision addressing the 8 mandatory items above would likely elevate this to an acceptable baseline.

---

---

# Comparative Summary

## Side-by-Side Scoring

| Dimension | Weight | v0.7 Raw | v0.7 Weighted | v0.2 Raw | v0.2 Weighted |
|---|---|---|---|---|---|
| Boundary Clarity | x2 | 3 | 6 | 4 | 8 |
| Actor Definition Quality | x1 | 2 | 2 | 4 | 4 |
| Entity Modeling Integrity | x1 | 4 | 4 | 3 | 3 |
| Flow Completeness | x2 | 5 | 10 | 3 | 6 |
| State Model Consistency | x2 | 4 | 8 | 3 | 6 |
| Assumption Transparency | x1 | 4 | 4 | 4 | 4 |
| Risk Coverage | x1 | 5 | 5 | 4 | 4 |
| Business Traceability | x1 | 3 | 3 | 4 | 4 |
| **TOTAL** | | | **42 / 50** | | **39 / 50** |

## Structural Profile Comparison

| Property | v0.7 | v0.2 |
|---|---|---|
| Business baseline | v0.5 (unavailable — unverifiable) | v0.3 (available — verified) |
| Alerts in scope | Yes (scope reversal unverifiable) | No (per D-05 — correct) |
| Target scale | ~10 users | ~100 users |
| Actor model | 8 actors (5 internal components — leakage) | 3 actors (clean context model) |
| Entities | 6 (incl. MetricActivityStatus — architectural) | 6 (incl. OnboardingSession) |
| Flow count | 11 primary + 4 sub-flows | 11 flows (no sub-flows) |
| State models | 5 complete models; Archived alert unreachable | 5 models; ParseAttempt has no lifecycle |
| Risk count | 19 (numbered, typed) | 12 (unnumbered) |
| Uncertainty register | 8 items (SU-001 to SU-008) | Implicit only |
| Free hosting in dependencies | **Missing** | Present |
| Command Dispatch Model | Implicit (via flow triggers) | Explicit (§5) — unique value |
| Failure Behavior Contract | Defined in §8.3 (atomicity) | Explicit separate section (§9) |
| MVP scope stability | Stable | Explicitly unstable (Open Question 1) |
| `is_synthetic` entity attribute | Present on Entry | **Missing on Parameter** |
| Decision log | 15 decisions (versioned, resolved) | 10 decisions |
| Iteration cycle | v0.7 (7th iteration — mature) | v0.2 (2nd iteration — early) |

## Key Divergences

### 1. Depth vs. Correctness Trade-off

v0.7 is deeper, more complete, and more mature at the flow and state model level. v0.2 is more traceable, correctly scoped to its business baseline, and structurally cleaner at the actor level. Neither document is defect-free.

### 2. Actor Model Philosophy

v0.7 violates context-layer modeling principles by listing internal subsystems as actors. v0.2 correctly limits actors to external roles. In a context diagram, this difference is fundamental — v0.7's actor model would produce an incorrect C4 context diagram.

### 3. Scope Verifiability

v0.2's scope claims can be audited against available documents. v0.7's scope changes (alert inclusion, user count reduction) rely on Business v0.5, which is absent from this repository. This is a pipeline documentation gap, not a modeling failure per se — but it means v0.7 cannot be fully reviewed without retrieving its business baseline.

### 4. Different Missing Entities

v0.7 is missing: `Alert.created_timestamp`; Free Hosting in dependency table.
v0.2 is missing: `Parameter.is_synthetic`; `LogEntry.unit`; ParseAttempt→PendingClarification relationship.

### 5. Command Dispatch Model

v0.2's explicit Command Dispatch Model (§5) is a genuine structural contribution absent from v0.7. It eliminates routing ambiguity and makes the system's intent-classification logic explicit at context level. v0.7 buries routing behavior inside individual flow triggers, requiring the reader to infer the dispatch priority themselves.

### 6. Alert Lifecycle vs. Clarification Lifecycle

v0.7 has the more complete alert state model (Active → Triggered → Active via re-arm | Archived | Deleted) but the Archived state is unreachable without a defined flow. v0.2 correctly omits alerts but has a richer PendingClarification lifecycle model than v0.7's ParseAttempt model, which is structurally equivalent to a log record.

## Recommendation

| Document | Score | Recommendation |
|---|---|---|
| system_analysis_v0.7.md | 42 / 50 | **Accept with Minor Adjustments** — Address actor boundary violations, add free hosting dependency, resolve Archived alert reachability, and provide a cross-reference to Business v0.5 |
| system_v0.2.md | 39 / 50 | **Iterate (Model Refinement Needed)** — Address `is_synthetic` attribute gap, dispatch model first-time-user step, `log` keyword ambiguity, and LogEntry/PendingClarification missing relationships |

> **If a single document must be selected as the forward baseline:**
> v0.7 scores higher in flow completeness, state modeling, and risk coverage — the dimensions most critical for architecture handoff. However, its actor model must be corrected before it can serve as a valid context diagram input. v0.2 is closer to correct context-level modeling principles and has a fully verifiable business baseline, but its entity inconsistencies and dispatch gaps require targeted revision. **The recommended path is to carry forward v0.2 as the live pipeline document (given its traceable business baseline), apply the 8 mandatory revisions, and selectively incorporate v0.7's stronger elements: richer flow sub-flows, numbered risk register, uncertainty register, and cascade atomicity specifications.**
