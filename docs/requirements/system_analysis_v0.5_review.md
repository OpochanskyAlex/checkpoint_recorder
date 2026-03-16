# System Review Report

## Reviewed Document
`docs/requirements/system_analysis_v0.5.md`

> **Internal Version Declared:** v0.1
> **File Name Version:** v0.5
> **Based On:** Business Analysis v0.5
> **Review Date:** 2026-03-16

---

## 1. Executive Assessment

The system context document demonstrates a thoughtful and well-structured first attempt at capturing system scope, entities, and flows from the business baseline. The boundary definition, assumption register, and risk inheritance from business analysis are all handled with appropriate discipline. However, the document carries a critical internal version inconsistency (file claims v0.5; body claims v0.1), which undermines traceability integrity from the outset. More structurally significant, three user-facing flows that are explicitly listed as in-scope capabilities are absent from the flow model — specifically Alert Configuration, standalone Metric Creation, and Metric Management. The state model contains a referenced-but-undefined state ("Abandoned" in the Metric model), a missing state model for the ParseAttempt entity, and a logical contradiction between Entry immutability and cascade deletion upon Metric deletion. The external dependency table omits the system's own persistence layer and chart rendering component entirely, which constitutes a boundary incompleteness that will create untracked risks at architecture stage.

---

## 2. Structural Strengths

- **Boundary scope is explicitly enumerated.** Twelve in-scope capabilities and nine out-of-scope items are named and justified, providing a clean baseline for architecture.
- **Actor table includes risk-if-misaligned column.** This proactively surfaces actor-level coupling risks rather than treating actors as passive labels.
- **Assumptions register is well-formed.** Each of the six assumptions carries a `why-it-exists`, `risk-if-false`, and `validation idea` — a model that should be continued through architecture.
- **Inherited risk traceability is maintained.** All eight business risks are carried forward with mitigation status updated at system context level.
- **Decision log and uncertainty register are populated and cross-referenced.** SD-001 through SD-004 and SU-001 through SU-005 are internally consistent with the body of the document.
- **Entity relationships include lifecycle descriptions.** Each entity's ownership and lifecycle section acknowledges deletion and retention obligations.
- **Traceability section maps business goals to system constructs.** The mapping in §11 is present and non-trivial.
- **§10 Logical Consistency Check is a valuable self-audit mechanism.** The author's own acknowledgement of known gaps is honest and structurally appropriate.

---

## 3. Structural Weaknesses

- **Internal version (v0.1) does not match file name (v0.5).** The document footer, header, and change log all reference v0.1. This breaks version traceability against the business baseline.
- **Three in-scope capabilities have no corresponding interaction flow:** Alert Configuration/Management, standalone Metric Creation, and Metric Listing — all named in §3 (Inside the System) — are absent from §5.
- **The Metric state model references a state ("Abandoned") that is never defined** in the state table.
- **The ParseAttempt entity has no state model.** It is described as a stateful entity with a lifecycle but is excluded from §6.
- **Entry immutability contradicts cascade deletion.** The Entry entity is declared immutable after creation, yet Metric deletion is stated to delete all associated Entries. The Entry state model has no "Deleted" state.
- **Metric `status` attribute on the Metric entity conflicts with MetricActivityStatus as a derived entity.** Whether `status` is stored or computed is ambiguous and these two constructs may produce divergent values.
- **Entry and Alert entities carry a redundant `internal_user_id` attribute** that is already reachable via the Metric relationship. This introduces a potential referential inconsistency.
- **The persistence/storage layer is entirely absent from the external dependencies table.** The system stores structured data across multiple entity types but declares no dependency on any storage mechanism.
- **Chart rendering has no identified dependency.** Chart generation is an in-scope capability (Flow 4) but the rendering component or library is absent from §7.
- **The metric creation sub-flow (Assumption 3) is acknowledged but never modeled.** The document identifies it as a compound flow requirement but provides no flow definition for it.

---

## 4. Boundary Violations

### Items Inside the System Boundary That Expose External Dependencies Not Declared in §7

| Capability | Implied Dependency | Status in §7 |
|---|---|---|
| Data entry storage, metric storage, alert storage, user storage | Persistence / storage layer (database or equivalent) | **Absent** |
| Chart generation (Flow 4, step 3) | Chart rendering library, image generation component, or external service | **Absent** |
| Free-text parsing (Flow 2, step 1; Flow 3, step 1) | NLP parsing library or rule engine | **Absent** |

### Conflation Within §7

The document lists **Telegram Messaging Platform** and **Telegram Bot API** as two separate external dependencies. The Bot API is the programmatic interface *to* the Telegram Platform — they are one dependency with two aspects, not two independent external systems. Splitting them inflates the dependency table without adding analytical value and may cause duplicate risk tracking.

### Boundary Statement Inconsistency

§3 states "User authentication (delegated entirely to Telegram)" is outside the system. §3 also states "User registration on first contact, assigning an opaque internal user identifier" is inside. These two statements together create a boundary ambiguity: the system participates in identity provisioning (assigning an internal ID) but disclaims authentication entirely. The boundary between *identity mapping* (in-scope) and *identity authentication* (out-of-scope) is not explicitly articulated and may be misread by an architect as a gap to fill or a constraint to override.

---

## 5. State Model Issues

### Gaps

| Entity | Gap |
|---|---|
| **Metric** | The state "Abandoned" is listed as a valid transition target from "Pending Periodicity" (transition table, row 1) but does not appear as a defined state with an entry condition, exit trigger, or risk row. The Metric state model is incomplete. |
| **ParseAttempt** | This entity is described as stateful with lifecycle events (created, resolved, expired/abandoned) but has **no state model** in §6. Its lifecycle is inlined into Flow 3 and the Entry state model, which is not equivalent to a dedicated state model. |
| **Entry** | Cascade deletion via parent Metric deletion is described in the Metric "Deleted" state row but the Entry state model has no "Deleted" state. The terminal states for Entry are "Stored" and "Discarded" only. Stored entries are declared immutable — this is contradicted by cascade deletion. |

### Overlaps / Conflicts

| Issue | Location |
|---|---|
| Metric `status` attribute (active/inactive) stored on the Metric entity vs. MetricActivityStatus as a computed/derived element | §4 Metric entity row vs. §4 MetricActivityStatus entity row |
| The Alert "Configured" state transitions to "Monitoring" on the first entry evaluation. An alert that has been configured but never evaluated is functionally indistinguishable from one in Monitoring. The "Configured" state adds no modeled behavior distinct from "Monitoring" and its existence is not justified. | §6 Alert States |

### Dead-End States

| Entity | State | Finding |
|---|---|---|
| Metric | Pending Periodicity → **Abandoned** | Referenced as a terminal transition but not defined. Behavior of an "Abandoned" metric (e.g., is the name available again? are partial records cleaned up?) is undefined. |

### Unreachable / Undefined Transition Conditions

| Entity | Transition | Issue |
|---|---|---|
| InternalUser | Registered — Active → Registered — Inactive | Trigger is "User ceases all interaction (inactivity)" — no quantitative boundary defined. Acknowledged as SU-005 but the state model presents this as a defined transition without a measurable condition. |
| Alert | Configured → Monitoring | Trigger is "First Entry evaluated against this alert." An alert on a metric with no future entries would remain in "Configured" indefinitely — this is a potential perpetual non-terminal state. |

---

## 6. Flow Integrity Issues

### Missing Flows for In-Scope Capabilities

The following capabilities are explicitly named in §3 (Inside the System) but have no corresponding flow in §5:

| Missing Flow | Declared In-Scope Capability |
|---|---|
| Alert Configuration | "Threshold alert configuration: recording user-defined alert conditions against a metric" |
| Alert Management (pause / delete) | Alert state model includes Paused and Deleted states — no flow models how these are reached |
| Standalone Metric Creation | "Metric creation: recording a new metric with its name and user-defined periodicity" |
| Metric Management / Listing | "Metric management: listing a user's metrics, supporting future deduplication or aliasing resolution" |

### Trigger Ambiguity

| Flow | Issue |
|---|---|
| **Flow 1 (Onboarding), Step 4** | "System then processes the original inbound message as per the appropriate flow." If the triggering message is a data entry for a non-existent metric, this creates a simultaneous three-way compound flow: Onboarding + Entry (Flow 2) + Metric Creation sub-flow (unmodeled). This compound entry point is not modeled and the failure modes (partial success in any leg) are undefined. |
| **Flow 2 (Successful Auto Parse), Step 2** | "the system initiates a metric creation sub-flow requesting periodicity" is asserted as behavior but no sub-flow or embedded flow segment is defined anywhere in the document. Assumption 3 acknowledges it but it is not modeled. |
| **Flow 5 (Alert Evaluation), Step 2** | "evaluates whether the entry's value satisfies the alert condition" — for multi-value entries (e.g., `80kg 5reps`), the target value dimension for alert evaluation is unresolved. The risk is noted but not resolved in the flow definition itself. |

### Responsibility Confusion

| Flow | Issue |
|---|---|
| **Flow 3, Step 6** | "Raw input is not silently discarded (confirmed — D-012)" — this states user acknowledgement on abandonment, but no step in the flow dispatches an acknowledgement message to the user. The flow describes the system discarding the ParseAttempt without a dispatch step for the "abandoned" path, contradicting the user acknowledgement claim. |

### Structural Circularity

- No problematic circular flows detected. The Alert Triggered → Monitoring cycle is intentional and appropriate as noted in §10.

---

## 7. Entity Modeling Issues

### Redundant Attributes Creating Potential Referential Inconsistency

| Entity | Redundant Attribute | Risk |
|---|---|---|
| **Entry** | `internal_user_id` (also reachable via Entry → Metric → InternalUser) | An Entry could theoretically carry an `internal_user_id` that differs from the owning Metric's `internal_user_id`. No constraint is stated to prevent this. |
| **Alert** | `internal_user_id` (also reachable via Alert → Metric → InternalUser) | Same inconsistency risk as above. |

### Conflicting Definitions

| Issue | Detail |
|---|---|
| **Metric `status` vs. MetricActivityStatus** | Metric entity defines a stored `status` attribute with values active/inactive. MetricActivityStatus is separately modeled as a derived/computed element. Both purport to represent the same semantic concept (is this metric active?). If they are separate constructs, the distinction must be explicitly defined. If they are the same, one must be removed. |
| **Entry immutability vs. cascade deletion** | Entry is declared "Immutable after creation. Never modified — a correction would be a new entry." Metric deletion is described as deleting "all historical Entries for this metric." These two statements are in direct logical contradiction. The Entry state model does not accommodate deletion. |

### Missing Entity State Model

| Entity | Status |
|---|---|
| **ParseAttempt** | Described as a stateful transient entity in §4 with created, resolved, and expiry transitions. No state model in §6. |

### Incomplete Entity

| Entity | Missing Attribute |
|---|---|
| **Alert** | The condition for a multi-value entry (which dimension to evaluate) is identified as a risk (R-011 risk block in Flow 5) but is absent from the Alert entity's attribute set. If multi-value entries are in scope, `target_value_dimension` or equivalent belongs on the Alert entity. |
| **ParseAttempt** | `expiry_timestamp` or equivalent timeout attribute is absent despite Assumption 4 stating that expiry behaviour must be defined. The entity cannot enforce the expiry assumption without this attribute. |

---

## 8. Dependency Risks

| External System | Purpose | Risk | Severity |
|---|---|---|---|
| Telegram Messaging Platform + Bot API (conflated) | All user I/O; user identity context | API policy change, rate limiting, or bot suspension renders the entire system non-functional with no fallback channel | **High** |
| **Persistence / Storage Layer [UNDECLARED]** | Stores InternalUser, Metric, Entry, Alert, ParseAttempt records across all flows | No storage dependency is declared; storage failure modes, data durability requirements, and isolation enforcement mechanism are entirely unaddressed at context level | **Critical** — absent from model |
| **Chart Rendering Component [UNDECLARED]** | Generates chart images for Flow 4 | Rendering failures, format incompatibilities with Telegram image display, and absence of a rendering dependency make chart delivery risk untracked | **Medium** — absent from model |
| **NLP / Parsing Engine [UNDECLARED]** | Free-text metric extraction in Flow 2 and Flow 3 | Parsing accuracy directly drives the >85% data input success metric; no dependency declared means its failure modes and update risks are untracked | **Medium** — absent from model |

---

## 9. Scoring

| Dimension | Weight | Raw Score (0–5) | Weighted Score | Comment |
|---|---|---|---|---|
| Boundary Clarity | x2 | 3 | 6 | In-scope capability list is strong. Three implied technical dependencies (storage, chart rendering, NLP) are entirely absent from §7. Bot API / Platform conflation reduces precision. |
| Actor Definition Quality | x1 | 4 | 4 | Four actors well-defined with responsibilities and misalignment risks. Operational Owner in-system interactions are appropriately minimal. No interaction flows for Bot Owner actor are expected at this stage. |
| Entity Modeling Integrity | x1 | 2 | 2 | Redundant `internal_user_id` on Entry and Alert. Metric `status` conflicts with MetricActivityStatus. Entry immutability contradicts cascade deletion. ParseAttempt lacks expiry attribute and has no state model. Alert missing multi-value dimension attribute. |
| Flow Completeness | x2 | 2 | 4 | Six flows modeled. Four in-scope capabilities (Alert Configuration, Alert Management, Metric Creation standalone, Metric Listing) have no flow. Metric creation sub-flow declared but not modeled. Flow 3 abandonment path missing acknowledgement dispatch step. |
| State Model Consistency | x2 | 2 | 4 | Metric "Abandoned" state referenced but undefined. ParseAttempt has no state model. Entry has no Deleted state despite cascade deletion. InternalUser Active/Inactive threshold undefined. Alert "Configured" state is functionally redundant with Monitoring. |
| Assumption Transparency | x1 | 4 | 4 | Six well-structured assumptions with risk and validation approach. Assumption 3 is an honest gap flag. Slight deduction because Assumption 3 flags a sub-flow that is never modeled. |
| Risk Coverage | x1 | 3 | 3 | Twelve risks well-documented. Three undeclared dependencies (storage, rendering, NLP) introduce untracked systemic failure risks that are absent from the register. |
| Business Traceability | x1 | 3 | 3 | §11 traceability table is present and non-trivial. "Data input success rate >85%" is not traced to a measurement mechanism. Alert accuracy target (>95%) is traced but the measurement method within the system is undefined. |

**Total Score: 30 / 50**

> **Threshold:** 30–39 → Significant refinement required.

---

## 10. High-Risk Structural Issues

| Issue | Impact | Probability of Causing Downstream Failure | Severity |
|---|---|---|---|
| Internal version (v0.1) conflicts with filename (v0.5) | Traceability to business baseline breaks; architecture phase may reference wrong version | Certain | **High** |
| Persistence / storage layer undeclared as external dependency | Storage architecture decisions made without context-layer risk framing; data isolation (R-005) has no modeled enforcement point | Certain at architecture stage | **Critical** |
| Entry immutability assertion contradicts cascade deletion on Metric delete | Architectural contradiction; Entry lifecycle is undefined under Metric deletion; data retention obligations may be silently violated | High | **High** |
| Alert Configuration and Alert Management flows absent | Alert feature cannot be designed without a modeled creation and management flow; Alert state model is orphaned from any triggering user interaction | Certain | **High** |
| Metric "Abandoned" state is undefined | Metric lifecycle after failed creation is unspecified; orphaned partial records and re-use of metric names are unaddressed design risks | High | **Medium–High** |
| ParseAttempt has no state model | Conversation-state management (R-010) cannot be evaluated without a formal lifecycle for the entity that represents that state | High | **Medium–High** |
| Metric `status` attribute conflicts with MetricActivityStatus derived entity | Active-user measurement may produce inconsistent results depending on which construct is used; success metric reporting is unreliable | Medium | **Medium** |

---

## 11. Mandatory Revisions

1. **Resolve the internal version conflict.** The document body, header, footer, and change log must all consistently reflect the correct version number. If the file is v0.5, all internal references must be updated to v0.5. This must be corrected before architecture review begins.

2. **Declare the persistence / storage layer as an external dependency in §7.** Even at context level, the system stores data — the storage mechanism must be named as a dependency with risk level, regardless of the specific technology choice. The absence creates a blind spot for R-005 (cross-user isolation) enforcement.

3. **Declare the chart rendering component as an external dependency in §7.** Chart generation is an in-scope capability with a Telegram delivery constraint; the rendering component must be identified as a dependency.

4. **Model the missing flows in §5:**
   - Alert Configuration flow (how a user creates an alert with a condition and threshold)
   - Alert Management flow (how a user pauses, re-activates, or deletes an alert)
   - Standalone Metric Creation flow (explicit metric creation as a user-initiated command, separate from implicit creation during entry)
   - Metric Listing / Management flow (listing metrics; this also provides the path for future deduplication/aliasing)

5. **Define and add the Metric "Abandoned" state to the Metric state model in §6.** The state must include entry condition, exit trigger, risk, and clarification of whether abandoned metric names become available again.

6. **Add a ParseAttempt state model to §6.** ParseAttempt is described as a stateful entity. Its lifecycle — at minimum: Created, Awaiting Selection, Resolved, Expired — must be explicitly modeled in the state model section.

7. **Resolve the Entry immutability vs. cascade deletion contradiction.** Either: (a) declare that Entries ARE deleted when their parent Metric is deleted, add a "Deleted" state to the Entry state model, and remove or qualify the immutability claim; or (b) declare that Entries persist beyond Metric deletion (orphaned entries), define their lifecycle in that scenario, and update the Metric deletion flow accordingly.

8. **Resolve the Metric `status` attribute vs. MetricActivityStatus conflict.** Explicitly state whether `status` on Metric is a cached/denormalized form of the computed MetricActivityStatus, or a distinct construct with a different semantic meaning. If they are the same, remove one. If different, define the difference.

9. **Add `expiry_timestamp` (or equivalent) to the ParseAttempt entity attribute set.** Assumption 4 and SU-001 state that expiry behaviour must be defined. The entity cannot model that behaviour without an attribute representing the timeout.

10. **Add `target_value_dimension` (or equivalent) to the Alert entity attribute set.** Multi-value entries are in scope; the Alert entity must be capable of specifying which dimension of a multi-value entry triggers the alert condition.

11. **Fix the Flow 3 abandonment path.** If D-012 confirms that input is not silently discarded, the abandoned path in Flow 3 must include a dispatch step that sends an acknowledgement to the user. Currently Step 6 describes the ParseAttempt as expiring without a corresponding outbound message.

12. **Define the InternalUser Active/Inactive boundary condition quantitatively.** SU-005 flags this as undefined. The state transition from Registered — Active to Registered — Inactive must have a measurable trigger condition stated in the state model row, even if deferred to architecture for final definition.

13. **Consolidate the Telegram Platform and Telegram Bot API into a single dependency entry.** The Bot API is the programmatic interface to the Platform, not an independent external system. Conflating them as two separate dependencies inflates perceived dependency count without adding risk granularity.

---

## 12. Iteration Recommendation

**Iterate (Model Refinement Needed)**

The document is a credible and honest starting point. The assumption register, risk inheritance, and traceability mechanisms are working correctly. However, the version inconsistency, four missing flows, three absent dependencies, and the Entry immutability / cascade deletion contradiction are structural issues that must be resolved before this document is safe to hand to an architecture designer. Passing it forward in its current state risks the architect making decisions that contradict an incomplete or internally inconsistent context model.

The mandatory revisions above are concrete and bounded. A single focused revision pass should be sufficient to bring this document to the **Accept as Baseline for Architecture** threshold.
