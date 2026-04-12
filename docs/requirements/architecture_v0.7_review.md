# Architecture Review Report

## Reviewed Versions

- **Architecture:** v0.1 (`architecture_v0.7.md`)
- **Business:** v0.5 (`business_analysis_v0.5.md`)
- **Context:** v0.7 (`system_analysis_v0.7.md`)

---

## 1. Executive Assessment

The architecture document is a credible first-draft baseline for a portfolio-scale, single-operator Telegram bot system. The component model is coherent, the six ADRs are appropriately scoped and reasoned, and the NFR mapping is grounded in the System Context v0.7 targets. However, the document has **one internal consistency error** (AD-7 is cited in the traceability matrix but never defined), **three system flows from Context v0.7 that are not modeled architecturally** (Flow 10a account restoration, Flow 3b late categorisation, metric archival/reactivation), and **three underspecified architectural mechanisms** that represent real implementation risk: the two-phase chart async model within the monolith, the ParseAttempt+Prompt atomicity compensation strategy, and the Observability Collector failure behavior. The data backup gap is the most operationally critical omission — D-013 (1-year retention guarantee) is architecturally unsupported without a stated backup approach. The document is **acceptable as a baseline** but requires targeted fixes before serving as a reliable input for an implementation specification.

---

## 2. Strengths

- **Architectural goals are explicitly justified and linked.** AG-1 through AG-7 each cite the business goal, system document section, and measurable metric they serve. This level of traceability at the goal layer is above average.
- **Monolith decision (AD-1) is well-reasoned.** The alternative-considered/rationale/consequences structure is complete and honest about the scale trade-off.
- **Repository-layer isolation (AD-5) is correctly framed as a security boundary, not a convenience.** The "miss-one-call" vulnerability analysis is the right reasoning for enforcing isolation at the query layer.
- **NFR mapping table (§7.1) is thorough.** All performance targets from System v0.7 §8.1 are represented with corresponding architectural tactics and explicit trade-offs.
- **Reliability/failure scenario table (§9) is comprehensive.** Ten distinct failure scenarios are addressed with detection, mitigation, and residual risk — matching the failure surface identified in System v0.7.
- **Observability baseline (§11) is production-grade.** Named metrics, structured log schemas with field-level specificity, trace paths, and dashboard concepts are all present. SLO candidates are meaningful and measurable.
- **Post-commit alert evaluation decision (AD-3)** correctly identifies the entry-rollback anti-pattern and proposes the right decoupling boundary.

---

## 3. Critical Weaknesses

- **AD-7 is cited in the Traceability Matrix (§14) but never defined.** The entry "AD-7 (atomic cascade)" appears under the "User data privacy and trust" goal row. No AD-7 section exists in §12. This is a hard internal consistency error. Cascade deletion atomicity is one of the most critical constraints in the system (R-005, §8.3 System v0.7) — it must have its own ADR.

- **Three system interaction flows have no architecture counterpart.**
  - **Flow 10a (Account Restoration):** System v0.7 defines restoration as a distinct flow with state transitions (PendingDeletion → Active) and a confirmation message. The architecture's Flow C covers account deletion but not restoration. The Account Manager component mentions restoration but no flow models it.
  - **Flow 3b (ParseAttempt Late Categorisation):** System v0.7 specifies user-initiated late categorisation as a full sub-flow: user requests list of Deferred ParseAttempts, selects or discards each. Flow B covers ParseAttempt creation and expiry transition but stops there. The late categorisation path — which requires the ParseAttempt Manager, Data Repository, and Entry Processor to coordinate — has no architecture flow.
  - **Metric Archival/Reactivation:** The component model (§4.1 Metric Manager) states it handles "metric archival" and the Data Strategy (§6) shows the Active ↔ Archived transition, but no interaction flow models the archival or reactivation commands. The metric state model in System v0.7 §6 treats these as explicit user-triggered transitions.

- **Two-phase chart async mechanism is architecturally undefined.** AD-6 decides on a two-phase response but the mechanism inside the monolith is left as "background coroutine or thread." No threading model is specified. No consideration of Data Repository thread-safety is given. No error channel for the second (chart delivery) message is described. Within a single-process monolith (AD-1), the interaction between the synchronous request/response pattern and this asynchronous chart delivery path is a non-trivial design decision that is not made.

- **ParseAttempt + Prompt atomicity has no compensation mechanism.** The NFR mapping (§7.1) states: "If prompt dispatch fails: clean up the ParseAttempt or retry dispatch." Neither cleanup nor retry is architecturally described — no component owns the compensation, no retry boundary is defined, no timeout is specified. System v0.7 §8.3 explicitly marks this as a hard consistency requirement: "a dangling Pending ParseAttempt with no associated user-visible prompt is a consistency failure." The architecture restates the problem without solving it.

- **Data backup strategy is completely absent.** §7.2 correctly flags "Backup frequency for Data Repository" as an NFR Unknown that blocks D-013 compliance. However, unlike other NFR unknowns which have at least a recommended starting point, the backup gap has zero architectural placeholder — no approach, no constraint, not even a "nightly file copy is sufficient at this scale" statement. D-013 (1-year retention guarantee) is architecturally unenforceable without a backup mechanism. This is a deployment blocker.

---

## 4. NFR Coverage Gaps

| NFR Category | Missing / Weak Area | Why It Matters | Required Fix |
|---|---|---|---|
| **Reliability — Observability Collector failure** | §7.1 states event emission "must not fail silently" but defines no failure behavior. Should it block the main flow? Fire-and-forget? Log locally? | If Observability Collector fails silently, all five business success metrics become unmeasurable simultaneously — the same failure mode as it being absent (System v0.7 §7). | Define the failure contract: fire-and-forget with local fallback log vs. blocking. Add this as an explicit architectural tactic, not a warning. |
| **Reliability — Backup / RPO** | No backup strategy, frequency, or restoration procedure described. | D-013 (1-year retention guarantee) cannot be satisfied if the Data Repository is lost without a backup. This is not an NFR Unknown that can remain open post-architecture. | State a minimum approach (e.g., "periodic dump of Data Repository to durable storage at cadence ≤ RTO/2") and define RTO/RPO bounds, even informally for portfolio scope. |
| **Concurrency — Monolith thread model** | AD-6 requires a background thread/coroutine; AD-1 declares single-process. No concurrency model for shared state is described. | Data Repository access, User Session Guard state reads, and ParseAttempt creation are potentially accessed concurrently if chart generation runs in a background thread. Race conditions are possible even at 10-user scale if not addressed. | Add a concurrency model note: which shared resources are thread-safe, what locking strategy (if any) is required, or whether chart generation is post-response (not truly concurrent). |
| **Performance — Scheduled Process worst-case lag** | §13.2 item 7 says "at most less than the grace period duration (3 days)" but no recommended cadence is given. | If the scheduled process runs daily, the worst-case PendingDeletion purge delay is 24 h beyond the 3-day window — potentially misleading users who expect deletion at exactly 72 h. | Recommend a specific cadence (e.g., "at least once every 12 hours") and state the worst-case lag implication for D-013. |
| **Availability — Process supervisor** | §9 and §7.1 mention "process supervisor / container restart-on-failure" and "health check endpoint" but neither is architecturally specified. | Without a defined supervisor mechanism and health check interface, the 95% uptime target (AG-5) has no architectural enforcement. | Specify the health check contract (what the endpoint returns, who calls it) even at a conceptual level. |

---

## 5. Trade-off & ADR Issues

- **AD-7 is missing.** Cascade deletion atomicity is one of four hard atomicity requirements in System v0.7 §8.3. It deserves its own ADR. The decision has real alternatives: (a) database transaction spanning all cascade entities in a single commit; (b) soft-delete with a background vacuum worker; (c) application-level multi-step deletion with compensating writes. None of these are compared. The phantom reference to AD-7 in the traceability matrix makes this omission structurally visible.

- **Structured command fallback (/log) is mentioned as a risk mitigation in §13.1 without any corresponding architectural decision.** The statement "structured command fallback (/log) as escape hatch if latency is persistently above target" implies an alternative input model. If this is a real architectural option, it requires a decision (an ADR noting it as a contingency if NLP latency exceeds the budget). If it is speculative, it should not appear in the architecture document as a stated mitigation — it creates false confidence that a fallback exists when no flow, command, or component supports it.

- **AD-2 (Polling vs. Webhook) is correctly deferred but the health check NFR creates an implicit dependency.** If polling is chosen (no public HTTPS endpoint), the health check endpoint mentioned in §7.1 and §9 cannot be a webhook-compatible HTTP endpoint. The document does not acknowledge this coupling.

- **SU-004 (Alert evaluation on Archived metrics) is resolved implicitly but not as an architectural decision.** §13.2 item 8 states "Logical default: suspend evaluation when Metric.status = Archived." This directly affects Alert Engine behavior (§4.1). A decision with this level of behavioral impact should be an explicit ADR or at minimum a numbered architectural decision, not an inline comment in an open questions list. As written, it is invisible to the Alert Engine implementation.

- **AD-4 (MetricActivityStatus lazy computation) does not address staleness in the context of the success metrics dashboard.** The Observability Collector is supposed to support real-time (or near-real-time) `active_users_count` metric. If MetricActivityStatus is computed lazily on read, and nobody reads it, the active user count in the Observability Collector may be stale indefinitely. The AD-4 rationale covers query-time accuracy but not push-to-observability accuracy. This is an unexamined trade-off.

---

## 6. Reliability & Failure Scenario Issues

| Scenario | What Is Missing | Risk | Priority |
|---|---|---|---|
| **ParseAttempt created, prompt dispatch fails** | §9 mentions this scenario and calls it a consistency failure. The mitigation says "cleanup or retry" but no component owns the compensation, no retry count/timeout is defined, and the failure path through ParseAttempt Manager is not traced. | Dangling Pending ParseAttempt blocks all subsequent user messages (User Session Guard enforces one-active-per-user). User is stuck with no visible prompt. | Critical |
| **Observability Collector unavailable during a flow** | §9 does not include this scenario. If the collector is unavailable, every flow that emits an event will hit an error — the document says this must not fail silently but gives no behavior. | All five business success metrics become unmeasurable; additionally, every flow's error handling must decide whether to fail or continue. | High |
| **Chart generation thread/coroutine crashes after acknowledgment sent** | AD-6 describes two-phase delivery but does not address what happens if the background process crashes before the image is sent. The user has received the "generating..." acknowledgment but will never receive the chart. | Silent failure: user waits indefinitely, no error message delivered. Not covered in §9. | High |
| **Scheduled Process runs twice concurrently (overlap)** | §8 mentions "ensure the process is not re-invoked while still running (idempotency guard)" but no mechanism for preventing overlap is defined. | If two invocations run simultaneously, cascade deletions could race, partial purges could collide, and D-013 audit logs could double-count. | Medium |
| **Re-registration of a Deleted user** | §6 (Data Strategy) notes "Deleted users who re-register must start fresh." Flow 1 (onboarding) idempotency is defined for concurrent first messages from the same user, but the case of a user whose account status = Deleted sending a new message is not covered in any flow or failure scenario. | The Telegram user ID may still exist in the system (as a Deleted InternalUser). The registration logic must explicitly handle this case to avoid re-activating a Deleted record vs. creating a fresh one. | Medium |
| **Alert notification dispatch failure on the retry attempt** | §9 mentions "single retry on notification dispatch" (carried from System v0.7 §5 Flow 5). What happens after the retry fails? The alert is in Triggered state permanently. The user receives no notification. This is accepted as a residual risk but the operator observability for this specific condition is not described — is it a distinct event type in the Observability Collector? | Users miss threshold notifications without knowing it; operator has no automated signal distinguishing "alert evaluated and delivered" from "alert evaluated, delivery failed after retry." | Medium |

---

## 7. Security & Compliance Issues

| Area | Gap | Risk | Priority |
|---|---|---|---|
| **Open bot registration (R-018)** | The architecture document acknowledges the gap but provides no mechanism for adding access control without structural changes — it only states the architecture "must support adding access control." The Message Dispatcher and User Session Guard do not model any allowlist check point, even as a placeholder. | If the bot address becomes known, unintended users register and inflate the user count beyond the 20-user architecture ceiling (§8.2), degrading performance without warning. | High |
| **raw_input in Observability events** | §10 states "raw_input must not appear in Observability events" and says this is "explicitly enforced at design time." But the Observability Collector component description (§4.2) contains no enforcement mechanism or validation gate. The `parse_outcome_event` log schema includes `confidence_score` and `metric_id` but the boundary between "structured reference" and "accidental free-text inclusion" is only a naming convention, not an architectural control. | PII leakage into logs; if logs are forwarded to an external system, raw user message content could escape the deletion lifecycle (raw_input is purged on account/metric deletion, but logs may persist independently). | High |
| **Telegram Bot API token rotation** | §10 and §4.2 (Configuration & Secrets) note that token rotation is the operator's responsibility. No minimum rotation guidance or detection mechanism (e.g., "if the bot fails to authenticate, emit a specific error event to the Observability Collector") is provided. | A compromised token is undetected until the operator notices operational anomalies. At portfolio scale this is accepted, but the architecture should at least define what a token-rotation event looks like operationally (redeploy with new env var, no downtime expected). | Low |
| **Integration test coverage for isolation (AG-3)** | §10 states user isolation "must be covered by integration tests verifying isolation." The architecture document names this requirement but provides no guidance on testability design — e.g., which component layer the tests target, what a cross-user isolation test looks like, or whether the Data Repository interface is designed to be test-injectable. | AG-3 (100% non-negotiable) depends on tests that are not architecturally specified. There is no testability strategy even at the conceptual level. | Medium |

---

## 8. Observability Issues

| Signal | Missing Detail | Operational Risk | Priority |
|---|---|---|---|
| **`active_users_count` freshness** | This metric is listed as an SLO candidate (§11.1) but AD-4 makes MetricActivityStatus lazily computed on read. The mechanism by which `active_users_count` is pushed to the Observability Collector (triggered by what event? on what cadence?) is undefined. | Business success metric "minimum 2 active users" may be uncomputable in real time; Observability Collector could show a stale count that does not reflect current system state. | High |
| **Observability Collector failure event** | The Observability Collector is listed as a component with "must not fail silently" but no signal exists for collector self-health. There is no `observability_collector_health` event, no heartbeat, no failure escalation. | If the collector fails, the operator has no signal — all five business success metrics silently degrade to unmeasurable. | High |
| **Scheduled Process heartbeat contract** | §11.1 does not include a specific `scheduler_heartbeat` event (only `scheduler_run_completed` and `scheduler_run_failed`). The "operator alert if heartbeat absent" mitigation in §9 depends on a heartbeat signal that is not named in the observability baseline. | If the scheduler simply stops running (no failure, just silence), there is no event to trigger the operator alert. | Medium |
| **Chart delivery failure (second phase)** | The `chart_invocation_event` log schema only covers the request. There is no `chart_delivery_failure_event` covering the case where the background chart generation fails after acknowledgment is sent. | Chart failures are invisible to the Observability Collector; `chart_invocation_rate` metric becomes misleading (counts requests, not delivered charts). | Medium |
| **`cross_user_isolation_incidents` detection mechanism** | This is listed as an SLO candidate with target = 0, non-negotiable. But no mechanism is described for how a cross-user isolation incident would be detected and emitted as an event. If repository-layer isolation is the control, a violation would only be detected by a test — not in production. | Zero-target SLO with no production detection mechanism is unenforceable as a live signal. | Medium |

---

## 9. Broken Traceability

| Item | Missing Link | Why Problematic | Fix |
|---|---|---|---|
| **AD-7 (Traceability Matrix §14)** | ADR section §12 defines AD-1 through AD-6 only. AD-7 is cited under "User data privacy and trust" but never authored. | Cascade deletion atomicity — one of the most critical R-005/SD-004 requirements — has no documented decision, no alternatives considered, no consequences. | Define AD-7 covering cascade deletion atomicity: alternatives (single DB transaction vs. soft-delete vacuum vs. compensating writes), rationale, and consequences. |
| **Scheduled Process → "Enable self-insight through history"** | §14 Traceability Matrix maps Scheduled Process only to "Service continuity" and "User data privacy and trust." D-013 (1-year retention guarantee) is also a direct enabler of historical data access — without retention enforcement, entries become unavailable within 1 year of the last interaction. | The business goal "Enable self-insight through history" is partially dependent on retention enforcement that the traceability matrix does not reflect. | Add Scheduled Process to the "Enable self-insight through history" row in §14, linked to D-013. |
| **Account Manager (restoration path)** | Flow C documents the deletion path. The Account Manager component lists restoration as a responsibility but no architecture flow maps to it. | Flow 10a (System v0.7) is a full user-facing interaction with state transitions and a confirmation message. Without an architecture flow, the Account Manager's restoration behavior is unspecified. | Add Flow F: Account Restoration, covering the PendingDeletion → Active transition, the user prompt, and the confirmation message. |
| **ParseAttempt Manager (late categorisation path)** | Flow B covers ParseAttempt creation and expiry. System v0.7 Flow 3b specifies a user-initiated view-and-categorise flow. No architecture flow covers this path. | The late categorisation path involves at least three components (ParseAttempt Manager, Data Repository, Entry Processor) and produces a new Entry with a historical `entry_timestamp`. Without an architecture flow, the implementation has no guidance. | Add Flow G: ParseAttempt Late Categorisation, tracing the user-requested deferred list view through to Entry creation or discard. |
| **Metric Manager (archival/reactivation)** | §4.1 states Metric Manager handles "metric archival" and §6 shows the Active ↔ Archived transition, but no flow models this. | Metric archival changes the alert evaluation scope (SU-004) and potentially the chart eligibility scope. Without an architecture flow, the behavioral contract is undefined. | Add at minimum a flow note covering archival and reactivation triggers, the Metric Manager interactions, and the SU-004 default behavior (suspend alert evaluation on Archived metrics). |
| **SU-004 implicit default** | §13.2 item 8 resolves SU-004 inline ("Logical default: suspend evaluation when Metric.status = Archived") but this is not reflected in the Alert Engine component model (§4.1), Flow A (Standard Data Entry step 5), or any ADR. | The Alert Engine will be implemented without a formal record of this behavioral rule. It could be implemented incorrectly (evaluating alerts on Archived metrics) without violating any documented constraint. | Elevate to an explicit architectural decision (AD-7 or a separate numbered item) or add to the Alert Engine component model as a stated behavioral constraint. |

---

## 10. Scoring

| Dimension | Raw Score (0–5) | Weighted Score | Comment |
|---|---|---|---|
| Alignment to Business Goals | 4 | 8 | AG-1 to AG-7 are well-formed and linked. AD-7 phantom reference and three missing flows prevent a 5. |
| Boundary & Context Consistency | 3 | 3 | System boundaries respected. Three System v0.7 flows (3b, 10a, archival) are absent from the architecture. |
| Component Model Quality | 4 | 8 | Components are named, scoped, and non-overlapping. Async coordination between Chart Generator and Telegram Gateway within the monolith is architecturally vague. |
| Interaction Model Clarity | 3 | 6 | Five flows are present and failure points are identified. Flow D is underspecified. Three complete system flows have no architecture counterpart. |
| NFR Coverage & Tactics | 3 | 6 | Good mapping table. Backup strategy is absent, Observability Collector failure is undefined, concurrency model for the two-phase chart is missing. |
| Trade-off Justification | 4 | 8 | AD-1 through AD-6 are solid with alternatives and consequences. AD-7 missing. /log fallback cited without a decision. SU-004 resolved informally. |
| Reliability & Failure Handling | 3 | 6 | §9 is thorough for the covered scenarios. ParseAttempt+Prompt compensation, chart async crash, and re-registration of Deleted users are not covered. |
| Security & Compliance Baseline | 4 | 4 | Isolation enforcement, token handling, raw_input, and open registration are addressed. Testability strategy and raw_input log-boundary enforcement are absent. |
| Observability Readiness | 4 | 4 | Named signals, log schemas, traces, dashboards are all present. `active_users_count` freshness, collector self-health, and cross-user incident detection are gaps. |
| Risk Identification & Mitigation | 3 | 3 | Five architecture risks in §13.1 are correctly identified. Async model risk, backup-gap D-013 impact, and Observability Collector cascade failure are missing. |

**Total Score: 56 / 70**

---

## 11. Mandatory Revisions

1. **Define AD-7: Cascade Deletion Atomicity.** Author a full ADR covering alternatives (single database transaction vs. soft-delete with vacuum vs. compensating writes), rationale for the chosen approach, consequences including idempotency requirements, and link it to R-005, SD-004, §8.3 System v0.7. Remove the phantom reference in §14 or replace it with the actual decision.

2. **Add Flow F: Account Restoration.** Model the PendingDeletion → Active path through Account Manager, including the user prompt, confirmation message, and state transition. Reference System v0.7 Flow 10a as the source.

3. **Add Flow G: ParseAttempt Late Categorisation.** Model the user-initiated deferred list view → Entry creation (or discard) path through ParseAttempt Manager, Data Repository, and Entry Processor. Reference System v0.7 Flow 3b.

4. **Add a metric archival/reactivation flow or at minimum a behavioral note in §5.2.** Document the trigger, the Metric Manager interaction, and the SU-004 default (alert evaluation suspended on Archived metrics). Elevate the SU-004 inline resolution to a numbered architectural decision.

5. **Define a concrete backup approach for the Data Repository.** Even a minimal statement ("periodic export/dump to durable storage; frequency TBD at deployment; RTO ≤ X hours, RPO ≤ Y hours") is required to make D-013 architecturally supportable. This does not require a technology choice — it requires an architectural intent.

6. **Specify the Observability Collector failure contract.** Define whether event emission is fire-and-forget or blocking, and what the local fallback is (e.g., "if collector unavailable, emit to stderr/local log and continue; metric coverage gap is operator-visible via absent events"). Add a `observability_collector_health` heartbeat to §11.1.

7. **Specify the async chart execution model within the monolith.** Clarify whether chart generation uses a thread, coroutine, or post-response dispatch. Address Data Repository thread-safety for the background execution. Define the error channel for the second-phase failure (chart generation crashes after acknowledgment sent).

8. **Define the ParseAttempt + Prompt atomicity compensation mechanism.** Assign explicit ownership to the ParseAttempt Manager: either (a) transactional — create ParseAttempt and dispatch prompt in a unit with rollback on dispatch failure, or (b) compensating — create ParseAttempt, attempt dispatch, if dispatch fails delete the ParseAttempt and return an error. Define the retry boundary. This is a hard requirement per System v0.7 §8.3.

9. **Add a `scheduler_heartbeat` event to §11.1** distinct from `scheduler_run_completed`. The operator alert for "scheduler not running" depends on the absence of this signal. Without it, a silently stopped scheduler is undetectable.

10. **Add a concurrency note to AD-1.** State explicitly how the two-phase chart background execution interacts with the single-process monolith's shared state (Data Repository, User Session Guard). Even "chart generation is post-response in a fire-and-forget coroutine with no shared mutable state beyond the Data Repository, which is assumed to support concurrent reads" is sufficient to close the gap.

11. **Remove or formalize the /log structured command fallback.** Either add it as a contingency architectural decision ("if NLP latency budget is exceeded in production, a structured `/log` command fallback will be introduced — this flow is not modeled at v0.1 and requires a future ADR") or remove it from §13.1 where it currently implies a mitigation that has no architectural backing.

12. **Add the Scheduled Process to the "Enable self-insight through history" row in the Traceability Matrix (§14)**, linked to D-013 (1-year retention guarantee).

---

## 12. Iteration Recommendation

**Iterate — Targeted Architecture Fixes Required**

The architecture is a credible baseline with sound reasoning at the decision layer. It does not require a structural rework. However, it cannot serve as a reliable input for an implementation specification in its current state due to: the missing AD-7 and its phantom traceability reference; three unmodeled system flows; the backup strategy gap threatening D-013; and the three underspecified mechanisms (async chart, ParseAttempt atomicity, Observability Collector failure). All mandatory revisions in §11 are targeted and do not require new components or changed system boundaries. A v0.2 addressing these items should be achievable without reconsidering the fundamental architecture.
