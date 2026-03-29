# Architecture Review Report

## Reviewed Versions
- Architecture: v0.1
- Business: v0.3
- Context: v0.3

---

## 1. Executive Assessment

Architecture v0.1 is a structurally coherent single-process design that correctly reflects the scope and constraints from Business v0.3 and System Context v0.3. The core decisions — embedded storage, single-process, synchronous per-message processing — are well-justified for the target scale and are consistently applied throughout the document. Traceability to business goals is present and the failure scenario register is substantive. However, three load-bearing architectural mechanisms are underspecified to the point where implementation would stall or diverge: (1) the per-user message serialization mechanism is described as a requirement but has no architectural pattern assigned to it; (2) the Chart Generator timeout enforcement is called "language-level cancellation" without any conceptual pattern — a naive implementation will not satisfy the requirement; (3) the Data Export Agent is listed as the sole disaster recovery mechanism but has no flow, no trigger architecture, and no consistency contract. Additionally, there is a responsibility overlap between the Dispatcher and the Parse Engine on the keyword collision disambiguation rule that, if left unresolved, will produce ambiguous implementation decisions.

---

## 2. Strengths

- **Decision quality is above average.** All six ADRs include alternatives considered, rationale, trade-offs, and consequences. AD-1 is correctly left open rather than arbitrarily resolved.
- **Failure scenario register is comprehensive.** Fifteen scenarios with detection, mitigation, and residual risk. Coverage of chart timeout, cold-start, concurrent message race, and log ephemerality is specific and actionable.
- **Startup Sweep is correctly architecturally separated.** Running the sweep as a pre-gateway startup phase before accepting messages is the right ordering and is consistently applied across Flow D, the component model, and NFR mapping.
- **NFR Unknowns table is honest and complete.** Six blockers are identified. Linking each unknown to the specific decision it blocks is valuable and prevents premature implementation.
- **Data strategy section is explicit about consistency needs.** Calling out atomic state transitions on User, PendingClarification, and OnboardingSession is precise and correct.
- **Traceability matrix covers all seven business goals** with components, decisions, and risks mapped.
- **Security baseline is proportionate.** The treatment of operator data access as a trust-based model requiring onboarding disclosure rather than technical control is appropriate and honest for this scope.

---

## 3. Critical Weaknesses

- **Per-user serialization has no architectural mechanism defined.** The requirement is stated in NFR (concurrency), in AD-4 (synchronous per-message), and in the scalability section ("per-user in-process queue or lock") — but no component owns this mechanism, no conceptual pattern is described, and no flow shows how a second message from the same user is actually held until the first completes. This is load-bearing for the correctness of PendingClarification state transitions and Parameter creation idempotency.

- **Chart Generator timeout enforcement pattern is underspecified.** "Active timeout termination" and "language-level cancellation" are stated as requirements, but no conceptual pattern is defined. Cooperative cancellation (checking a flag) and preemptive cancellation (thread interruption, process signal, goroutine context cancellation) behave very differently. An implementer without guidance may use a naive sleep-and-check approach that does not interrupt a blocking rendering call. Given this is described as the mechanism preventing the bot from becoming unresponsive, it must be specified to at least a pattern level.

- **Data Export Agent is architecturally orphaned.** It is the sole disaster recovery mechanism (RPO = 24 hours) but has no key flow (no Flow F), no description of how it is triggered within the single-process architecture, no consistency contract (should the bot be quiesced during export? can writes happen concurrently?), and no failure scenario (what happens if export fails silently for multiple days?). The description "scheduled or externally triggered" defers all architecture to operations, which is insufficient for a DR mechanism.

- **Dispatcher / Parse Engine responsibility overlap on keyword collision disambiguation.** The Dispatcher component description assigns keyword collision to dispatch step 3. The Parse Engine component description states it "applies the keyword collision disambiguation rule." System Context v0.3 Section 5 places all disambiguation logic in the dispatch model. This is a contradiction: one responsibility owned by two components. An implementer will make an arbitrary choice, likely duplicating or splitting the logic.

- **Onboarding operator disclosure atomicity is stated as a consistency need but has no failure contract.** The Data Strategy section correctly states "operator disclosure delivered flag must be set in the same transaction as the welcome message delivery." However, if the Telegram message send succeeds but the flag write fails, or if the flag write succeeds but the message send fails, there is no defined recovery behavior. This is a compliance-relevant operation (non-optional per System v0.3 Section 10.4) and cannot be left without a failure contract.

- **Keep-alive mechanism is "recommended" but unowned.** It is mentioned in AD-6 consequences and in the cold-start NFR row, but no component owns it, no flow describes it, and it is not in the supporting components table. If no component owns the keep-alive, it will not be implemented. This is the primary mitigation for the cold-start latency risk which is identified as "High probability" in the reliability section.

---

## 4. NFR Coverage Gaps

| NFR Category | Missing/Weak Area | Why it matters | Required Fix |
|---|---|---|---|
| Performance — cold start | Keep-alive mechanism "recommended" with no owner, no trigger, no scheduling pattern | Cold-start is identified as the most probable cause of latency violations in practice; without an owner, the mitigation will not be implemented | Assign keep-alive to a component (e.g., Telegram Gateway or a new Heartbeat component) and describe the trigger pattern conceptually |
| Concurrency | Per-user serialization tactic is "in-process queue or lock" but no component owns it and no pattern is described | Race conditions on PendingClarification and Parameter creation are the primary correctness risks for the system; stating the requirement without a pattern leaves implementation undefined | Define a conceptual pattern (e.g., per-user dispatch lock acquired by the Dispatcher before routing; released after handler completes) and assign ownership to the Dispatcher |
| Data Durability | Export Agent has no consistency contract; no failure scenario for export not running | RPO = 24 hours is the stated target; silent export failure for multiple days degrades RPO without detection | Add a failure scenario for export failure; define whether concurrent writes during export are permitted; describe minimum consistency guarantee |
| Reliability — transaction atomicity | AD-3 states "transaction support must be confirmed" but this is marked Confirmed; if the embedded storage does not support transactions, no compensating pattern is defined | Multi-entity writes (User state change, LogEntry + Parameter creation, PendingClarification state transition) require atomicity; without transactions, partial writes produce inconsistent state | Either confirm transaction support is a hard requirement for storage selection, or define a compensating pattern (e.g., write-then-verify with idempotent retry) for the case where it is unavailable |
| Availability | No architectural description of what "manual daily check" means operationally | > 90% daily availability target has no detection mechanism that can catch a 2–4 hour outage | At minimum, note whether the keep-alive mechanism doubles as a liveness check, or whether a separate external health probe is needed |

---

## 5. Trade-off & ADR Issues

- **AD-2: Serverless alternative is dismissed without addressing the fundamental incompatibility.** The alternative of "serverless / function-per-flow" is listed and dismissed because "free-tier hosting typically provides one container." The more important reason to reject serverless is that stateless function invocations cannot enforce per-user message serialization without external state (a distributed lock or queue), which violates the zero-dependency constraint. The listed rationale misses the stronger architectural argument. This should be corrected to prevent a reviewer from thinking serverless is viable with a different hosting arrangement.

- **AD-3: "Transaction support must be confirmed" is listed as a consequence of a Confirmed decision.** This is contradictory. If a decision is Confirmed but one of its consequences is unverified, it should be marked Open or Conditional, not Confirmed. Either resolve the transaction support question (making embedded relational storage a concrete constraint on implementation) or change the status to Conditional.

- **AD-4: The "async within a message (non-blocking I/O)" alternative is dismissed but deserves more treatment.** For the chart flow specifically, non-blocking I/O is relevant: the chart generation could run in a separate async context while the bot continues processing other users' messages. The current synchronous model means chart generation for User A blocks User B's message processing (under strict single-threaded synchronous execution). At 100 users this is unlikely to matter, but the dismissal should note this explicitly.

- **AD-6: The trade-off table conflates "no external alerting" with "no keep-alive mechanism."** Keep-alive is not an alerting or notification mechanism — it is a reliability mechanism that prevents cold-start latency. Including it in the consequences of AD-6 is architecturally incorrect; it belongs in AD-2 (single-process) or as its own AD.

---

## 6. Reliability & Failure Scenario Issues

| Scenario | What is missing | Risk | Priority |
|---|---|---|---|
| Data Export Agent fails silently for multiple consecutive days | No failure scenario exists for export failure. The RPO degrades without detection. | RPO guarantee collapses without any signal to the developer | High |
| Onboarding message send fails after User record created | No failure contract defined despite the Data Strategy section flagging it as a consistency need. The operator_disclosure_delivered flag state is undefined after a partial failure. | Non-optional compliance control (Section 10.4, System v0.3) may be silently skipped | High |
| Chart Generator timeout mechanism fails to interrupt blocking call | Listed as "Low probability" in risk 13.1, but the mechanism is underspecified. If the timeout is implemented as a flag check rather than preemptive cancellation, a blocking render call will not be interrupted. | Bot process becomes unresponsive; all subsequent messages blocked | High |
| Startup Sweep fails partway through on an uncaught exception | The recovery states "restart triggers a fresh sweep" and "sweep must be idempotent," but there is no failure scenario entry for this. The idempotency requirement is stated without a validation path. | Partially purged User records or stale Open PendingClarifications could remain if the sweep is not truly idempotent | Medium |
| Embedded storage file corrupted (not just absent) | The storage failure scenarios cover "file not found" (hosting eviction) and "write/read failure" (runtime errors), but not storage file corruption. Corruption would make the export artifact also potentially untrustworthy. | Irrecoverable data loss scenario not addressed | Medium |
| Two-step deletion confirmation state lost on restart | Flow 8 (Parameter Deletion) requires a two-step confirmation. If the bot restarts between the first and second step, the pending confirmation state is lost — but this is not modeled as a stateful entity or a PendingClarification-like record. The user's confirmation response after restart will not match any pending state. | User receives an unexpected response; must re-initiate deletion. No data is lost, but the UX break is not handled. | Low |

---

## 7. Security & Compliance Issues

| Area | Gap | Risk | Priority |
|---|---|---|---|
| Storage file access control | The embedded storage file contains all user data. No architectural statement is made about file-level access controls on the hosting environment. If the hosting platform exposes the filesystem to other tenants or the file is world-readable, the entire dataset is exposed. | Full dataset exposure via filesystem rather than query path | Medium |
| Telegram ID reuse by a new person | The security baseline notes "Telegram account compromise exposes bot data." A more specific and plausible risk is: if a user deletes their Telegram account and the numeric ID is eventually reused by a different person, the new person could access the prior user's bot data. This risk is not modeled. | PII / data exposure to a new Telegram account holder with a recycled ID | Medium |
| Per-user abuse (message flood) | No per-user rate limiting is described. Telegram's global rate limits (30 msgs/sec outbound) are mentioned, but a single malicious or malfunctioning user could flood the bot with inbound messages, creating excessive ParseAttempt records and monopolizing the single-process execution queue. | Denial of service against other users; storage bloat from ParseAttempt records | Low |
| Export artifact security | The export artifact contains all user data and is written to a "developer-controlled external location" with no security controls described. If the export destination is a public URL, a shared drive, or an unencrypted email attachment, all user data is exposed. | Full dataset exposure via export artifact | Medium |
| Operator disclosure delivery confirmation | The operator_disclosure_delivered flag is set to track delivery, but there is no described mechanism to verify the Telegram message actually reached the user (Telegram delivery is best-effort). The flag records that the system sent the message, not that the user received it. This is a subtle compliance gap if the disclosure is legally or ethically required. | Operator disclosure considered complete without confirmed delivery | Low |

---

## 8. Observability Issues

| Signal | Missing detail | Operational risk | Priority |
|---|---|---|---|
| How does the developer actually query the metrics? | The observability section states "developer queries storage directly" but provides no description of the query mechanism — ad hoc SQL, a script, a scheduled report. Without tooling defined at even a conceptual level, "observability from day one" is aspirational. | Metrics exist in storage but are never actually measured; success metrics from Business v0.3 go uninspected | High |
| Structured log format not defined | The log schema shows fields ({user_id, flow_name, error_type, timestamp}) but the format is not stated — JSON, key-value pairs, plaintext with delimiters. Without a consistent format, log forwarding tooling cannot parse the records reliably. | Log forwarding may fail or produce unparseable records; retrospective analysis is manual | Medium |
| Export execution is not logged | The Data Export Agent has no observability entry. If the export runs silently with no log record, the developer cannot verify the RPO guarantee is being met. | Daily export failures are invisible until a restore is attempted | High |
| Keep-alive heartbeat not observable | The keep-alive mechanism is not assigned to any component, so no log signal or metric for keep-alive execution exists. If the keep-alive stops working, the developer has no signal until a cold-start is observed by a user. | Cold-start degradation goes undetected; availability target silently missed | Medium |
| No SLO latency signal | The 3-second text response latency target is stated as an NFR, but no metric or trace signal is defined to measure it. The traces section describes end-to-end latency as a trace target but does not describe how it would be captured or reviewed in a single-process system with no tracing framework. | Latency violations are undetectable without a measurement signal | Medium |

---

## 9. Broken Traceability

| Item | Missing Link | Why problematic | Fix |
|---|---|---|---|
| Keep-alive mechanism | Not in any component; not in any flow; not in any ADR | Keep-alive is the primary mitigation for the cold-start risk (identified as High probability) but has no architectural owner or specification | Add as a supporting component or assign to Telegram Gateway; document trigger pattern; add to AD-2 or as AD-7 |
| Per-user serialization mechanism | Stated as a requirement in NFR table and scalability section but owned by no component and described by no pattern | The correctness guarantee for PendingClarification and Parameter creation depends on this mechanism; without an owner, it will be implemented arbitrarily | Assign ownership to the Dispatcher; describe the in-process conceptual pattern (e.g., per-user lock/queue); add to the NFR tactic column |
| Data Export Agent | No key flow; no trigger architecture; no consistency contract; no observability signal | It is the sole DR mechanism and is architecturally underspecified compared to every other component | Add Flow F (Data Export); define trigger mechanism; add consistency contract; add export execution log signal |
| Two-step deletion confirmation state | Described in Flow 8 (Parameter Deletion, System v0.3) as a required interaction step but not modeled as a stateful construct in the architecture | On restart between step 1 and step 2, the confirmation context is lost; behavior is undefined | Either model the pending confirmation as a transient storage record (similar to PendingClarification) or explicitly define the restart recovery behavior as "confirmation context lost; user must re-initiate" |
| Chart Generator (supporting component) | Not in the traceability matrix | The chart flow is one of three core user interactions and the most reliability-critical; its absence from traceability is an oversight | Add Chart Generator to the traceability matrix row for "Personal utility — reduce logging friction" |
| Structured Logger | Not in the traceability matrix | Observability from day one is an explicit architectural goal; the component responsible for it should be traceable | Add Structured Logger to the traceability matrix row for "Developer learning / observability from day one" |

---

## 10. Scoring

| Dimension | Raw Score (0–5) | Weighted Score | Comment |
|---|---|---|---|
| Alignment to Business Goals | 4 | 8 | All seven business goals traced; Chart Generator and Structured Logger absent from traceability matrix; onboarding quality not explicitly linked to user return rate metric |
| Boundary & Context Consistency | 4 | 4 | No new scope introduced; all System v0.3 entities and flows are accounted for; keyword collision disambiguation ownership split is a boundary inconsistency |
| Component Model Quality | 3 | 6 | Core components are well-defined; Data Export Agent orphaned; per-user serialization mechanism unowned; keep-alive unowned; Dispatcher/Parse Engine overlap |
| Interaction Model Clarity | 3 | 6 | Five flows documented step-by-step with failure points; no flow for Data Export Agent; no flow for keep-alive; two-step deletion confirmation restart behavior undefined |
| NFR Coverage & Tactics | 3 | 6 | NFR table is present and linked; concurrency tactic is "queue or lock" without an owner; transaction atomicity is deferred; keep-alive has no owner; export consistency contract absent |
| Trade-off Justification | 4 | 8 | Six ADRs present with alternatives; AD-2 serverless dismissal is weak; AD-3 status is self-contradictory (Confirmed but transaction support unconfirmed); AD-4 async dismissal incomplete for chart flow |
| Reliability & Failure Handling | 3 | 6 | Fifteen scenarios with good coverage; export failure scenario absent; onboarding disclosure partial failure absent; deletion confirmation restart gap absent; timeout enforcement mechanism underspecified |
| Security & Compliance Baseline | 3 | 3 | Good coverage of cross-user isolation, secrets, PII, input injection; storage file access controls absent; Telegram ID reuse risk absent; export artifact security absent |
| Observability Readiness | 3 | 3 | Signal schema defined; query mechanism absent; log format absent; export execution not logged; SLO latency signal absent |
| Risk Identification & Mitigation | 3 | 3 | Comprehensive risk register; export failure risk absent; storage corruption absent; deletion confirmation restart risk absent |

**Total Score: 53 / 70**

---

## 11. Mandatory Revisions

1. **Assign ownership and define a conceptual pattern for per-user message serialization.** The Dispatcher must be updated to describe how it holds the second message from a user until the first is fully processed. Describe the pattern at the conceptual level (e.g., "per-user in-process lock acquired at dispatch entry and released after handler returns, including storage writes"). This is load-bearing for PendingClarification correctness.

2. **Specify the Chart Generator timeout enforcement pattern at the conceptual level.** Replace "language-level cancellation" with a conceptual pattern that distinguishes cooperative cancellation (flag-checking, incompatible with blocking calls) from preemptive cancellation (thread/goroutine/async context cancellation). State which pattern class is required and why, so an implementer cannot choose a naive approach.

3. **Add Flow F: Data Export.** Document the trigger mechanism (how the export is initiated within or alongside the single-process bot), a consistency contract (are concurrent writes permitted during export?), and a failure behavior (what happens if the export fails, how does the developer know). Update the supporting component entry for Data Export Agent accordingly.

4. **Resolve the Dispatcher / Parse Engine keyword collision disambiguation overlap.** The keyword collision disambiguation rule belongs to the Dispatcher (dispatch step 3). Remove it from the Parse Engine component description. Parse Engine is responsible for extracting (name, value, unit) from messages that have already been routed to it as log intent.

5. **Define the failure contract for the onboarding operator disclosure.** The Data Strategy section correctly identifies this as a consistency-critical operation. Add a failure contract: what happens if the Telegram send succeeds but the flag write fails (or vice versa)? Options include: (a) transactional write before send, (b) flag defaults to false and re-delivery attempted on next message, (c) send-then-write with retry on flag failure. State the chosen approach.

6. **Add a failure scenario for Data Export Agent failure.** Define: how does the developer detect that the daily export has not run? What is the detection signal? What action is required? The current document has no signal for export failure, which means RPO degradation is invisible.

7. **Add keep-alive as an owned architectural component or assign it to the Telegram Gateway.** Document the trigger pattern (e.g., "periodic self-ping or no-op API call on a timer within the Telegram Gateway process loop"), add it to the supporting components table, and include an observability signal for its execution. Remove it from the consequences of AD-6 and place it in AD-2 or a new AD-7.

8. **Clarify the status of AD-3.** If embedded relational storage with transaction support is a hard requirement, state it explicitly and change the status from "Confirmed with unconfirmed consequence" to "Confirmed: transaction support is a mandatory selection criterion for the storage mechanism." If transaction support is not guaranteed, define a compensating write pattern (e.g., idempotent multi-step write with verification) and add it to the component model.

9. **Address the two-step deletion confirmation restart gap.** Define whether the pending confirmation context survives a restart (requires a storage record) or is lost on restart with "user must re-initiate" as the defined behavior. Add this as a failure scenario entry.

10. **Add Chart Generator and Structured Logger to the traceability matrix.** Both components are architecturally significant and linked to business goals (personal utility and observability/learning outcome respectively). Their absence creates an incomplete trace.

---

## 12. Iteration Recommendation

**Iterate — Targeted Architecture Fixes Required**

Score 53/70 falls in the 42–55 range. The architecture is structurally sound and its core decisions are well-reasoned. It is not a rework candidate. However, three mechanisms (per-user serialization, chart timeout enforcement, data export) are underspecified in ways that will produce implementation ambiguity or incorrect behavior if not resolved. These are targeted, bounded fixes that do not require restructuring the architecture. Once addressed, the document is a sound baseline for the implementation specification stage.

---

## Governance Block

### Version
v0.1

### Based On
Architecture v0.1

### Scoring Summary
53 / 70 — Iterate (targeted fixes required)

### Mandatory Revision Count
10

### Top 3 Blockers for Advancement
1. Per-user serialization mechanism unowned and unpatternized (correctness risk for PendingClarification and Parameter creation)
2. Data Export Agent has no flow, no trigger architecture, and no failure scenario (sole DR mechanism is architecturally orphaned)
3. Chart Generator timeout enforcement pattern is underspecified (process-blocking risk under naive implementation)
