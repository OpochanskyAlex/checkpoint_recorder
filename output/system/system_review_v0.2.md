
# Architecture Review Report

## Reviewed Versions
- System Context Document: v0.2
- Business Analysis: v0.3
- Previous System Review: v0.1 (reference)

---

## 1. Executive Assessment

System Context Document v0.2 is a materially improved revision that addresses the most structurally critical gaps from the v0.1 review: a command dispatch model is now present, NFR targets are specified, failure behavior contracts are defined, a security section exists, and an observability model maps all three primary business success metrics to concrete signals and measurement formulas. These additions represent a meaningful jump in document fitness. However, several consequential gaps that were not flagged in the v0.1 review have now become visible as structural clarity has improved. The most significant outstanding issues are: the persistent absence of any storage model (mechanism, technology class, schema constraints), an internal logical inconsistency between the dispatch model in Section 5 and the PendingClarification state model in Section 7 (the `Resolved` state is defined but the dispatch model always routes to `Abandoned`), an unspecified enforcement mechanism for the 3-day account deletion window (a background process or scheduler is implied but never described), and a keyword collision risk that could silently misroute legitimate log commands as command keywords. The document is approaching a level where architecture design could begin, but the storage model absence and the PendingClarification state contradiction are blocking issues that must be resolved before handoff. Score: 51 / 70 — **Iterate (Targeted Architecture Fixes Required).**

---

## 2. Strengths

- Section 5 (Command Dispatch Model) directly addresses the most critical v0.1 gap. The priority order (Pending Clarification → Account State → Keyword Match → Log Intent Default) is unambiguous and well-reasoned.
- Section 8 (NFRs) provides numeric targets: 3-second text response, 15-second chart delivery, >90% daily availability target, 24-hour RPO — all of which are traceable to architectural decisions and hosting realities.
- Section 9 (Failure Behavior Contract) defines expected system behavior for four concrete failure scenarios (storage write, chart generation, startup with open clarifications, sparse period comparison). The rationale for each is explicit.
- Section 10 (Security and Data Controls) correctly identifies data isolation enforcement as the highest-impact failure mode and states the mandatory query-scoping control. Operator access transparency (Section 10.4) is an unusually honest and appropriate disclosure for a personal-scope system.
- Section 11 (Observability Model) maps all three primary business success metrics to named entities, measurement formulas, and quantitative targets. This is directly traceable to Business v0.3.
- The ParseAttempt entity is now integrated into Flows 1 and 2 with explicit creation triggers, addressing the orphaned-entity gap from v0.1.
- User state lifecycle is now complete: New → Onboarding → Active → Pending Deletion → Deleted. All transitions, entry conditions, and terminal states are defined.
- The Traceability section (Section after Decision Log) maps every business goal to a specific entity, flow, or state — not just to sections. This is a high-quality traceability standard.
- Risk register (Section 14) has been extended with 5 new risks. The cold-start, data isolation defect, one-shot clarification data loss, and account deletion misunderstanding risks are all valid and non-obvious additions.
- The Logical Consistency Check (Section 15) is retained and updated, including an explicit acknowledgement of the one residual ambiguity (rejection message vocabulary during Pending Deletion). This discipline is commendable.
- The MVP scope acknowledgement note in Section 1 correctly flags that the open business question (B-OQ-1) has not been resolved and that this document assumes full functional scope pending that decision. This is appropriate scoping hygiene.

---

## 3. Critical Weaknesses

- **Storage model is still entirely absent.** The v0.1 review identified this as a critical gap. v0.2 does not address it. The document describes six persisted entities with relational lookup and timestamp-sorted retrieval requirements (Section 8.4) but never names a storage mechanism, technology class (relational, embedded, file-based), or schema constraints. An architect cannot design the persistence layer, validate free-tier fitness, or plan the daily export mechanism without this. This is the single most consequential unresolved gap.

- **PendingClarification state contradiction between Section 5 and Section 7.** Section 5 states: "The open PendingClarification is marked Abandoned. The new message is then processed as a fresh input." This means the dispatch model always sets the state to `Abandoned` on any incoming message, regardless of outcome. However, Section 7 defines a `Resolved` state: "Resolved: User's clarification response is successfully processed as a new ParseAttempt and LogEntry." Flow 3 (Section 6) also references the clarification being marked Abandoned before the new message is processed. If all clarification responses are first marked Abandoned, the `Resolved` state is unreachable by the described mechanism. This is an internal logical inconsistency that will produce incorrect state tracking, incorrect observability measurements (parse failure resolution rate in Section 11.1 depends on `PendingClarification.state = resolved`), and confusing audit records.

- **3-day account deletion enforcement mechanism is undefined.** Flow 10 places a User in Pending Deletion state and sets `deletion_requested_at`. The 3-day window expiry triggers permanent data purge. But no mechanism is described for executing this purge: there is no mention of a background job, scheduled task, cron trigger, or bot-startup sweep analogous to the `Open PendingClarification` cleanup defined in Section 9.3. Without an enforcement mechanism, the 3-day window is a contract the system cannot honor.

- **Keyword collision risk is unaddressed.** The dispatch model performs keyword matching on the leading token(s) of any message. A user whose parameter name begins with a reserved keyword (e.g., "history of my runs", "chart progress", "list 5kg", "delete junk food") will have their log-intent message misrouted as a command keyword match. The document does not acknowledge this risk or define a disambiguation rule (e.g., "keyword match only if the leading token is followed by a known parameter name OR stands alone"). This affects the correctness of Flows 1, 2, 4, 5, 6, 7, and 8.

- **Parameter name matching strategy is undefined across multiple flows.** Flow 4 states "Parameter name must match exactly or approximately to what the user typed." Flows 5, 6, and 8 all retrieve a parameter by name from user input. The matching rule (exact, case-insensitive, prefix, fuzzy) is never specified. This is not a minor detail — it directly affects: whether `Weight` matches `weight`, whether `body weight` matches `bodyweight`, and what happens if two parameters have similar names. Without a defined matching strategy, each flow that retrieves a parameter by name has an undefined behavior path.

- **Telegram update delivery model (polling vs. webhook) is unspecified.** This is a relevant system-level decision. Long-polling and webhook delivery have different implications for hosting requirements (webhook requires a public HTTPS endpoint), cold-start behavior (polling survives cold-start restarts more gracefully), and message ordering guarantees. The choice affects the NFR targets in Section 8 and the cold-start risk in Section 14. It should be identified as either a decision or an open question, not silently omitted.

---

## 4. NFR Coverage Gaps

| NFR Category | Missing/Weak Area | Why it matters | Required Fix |
|---|---|---|---|
| Durability / Backup | Section 8.3 defines RPO (24 hours) and says "a periodic export must be available" but specifies no export format, no storage location, no trigger mechanism, and no recovery procedure. The developer is named as responsible with no further specification. | The export is the sole mitigation against the High-impact free-tier data loss risk. A target without a mechanism is not a control. | Define at minimum: export format (e.g., JSON or SQL dump), where the export is stored (external to the hosting environment), trigger mechanism (scheduled job, manual script, or CI artifact), and what the recovery procedure looks like conceptually. |
| Concurrency / Race Conditions | No NFR or architectural constraint addresses concurrent message handling. Telegram can deliver two messages from the same user within milliseconds (e.g., a user typing quickly). Two simultaneous messages could both pass the "no open PendingClarification" check and both reach the parse engine, creating duplicate parameter creation or duplicate LogEntry writes. | At 100 users with free-text input, concurrent writes from the same user are a realistic scenario. Without a serialization or idempotency NFR, the developer has no guidance. | State a concurrency handling posture: at minimum, acknowledge that the bot process handles one message at a time per user (if true), or state that concurrent writes from the same user are accepted as a risk at this scale. |
| Cold Start Latency | Section 8.1 excludes cold-start latency from the 3-second response target with "first-message latency after idle is not bounded by this target." The cold-start risk is listed in Section 14 as High probability. No mitigation is mandated. | A user whose first message takes 30+ seconds to receive a response will assume the bot is broken and may not retry. This directly threatens User Return Rate. | Define a maximum acceptable cold-start latency (e.g., informally "targeted at <30 seconds") or mandate a keep-alive mechanism as a deployment requirement, not merely a suggestion. |
| Input Validation / Injection | Section 8.7 defines parameter name length bounds and mentions character set sanitization, but there is no NFR addressing injection resilience. If the chosen storage mechanism is relational, unsanitized parameter names or log values could produce storage errors or data corruption. | The storage mechanism is unspecified, but any relational or query-based mechanism is at risk without explicit input sanitization requirements. | Add a minimum input sanitization NFR: parameter names and log values must be sanitized or parameterized before any storage operation; raw user input must never be interpolated directly into storage queries. |
| Error Message SLA | Section 8.6 requires a human-readable error message for every failure path. No timing constraint exists: "the system must return a message" — but when? An error message returned after 30 seconds is not useful. | Without a time bound, a retry loop or timeout at the infrastructure layer could delay error messages to the point of user confusion. | Add a timing constraint to Section 8.6: error messages must be returned within the same latency target as success responses (3 seconds for text operations). |

---

## 5. Trade-off & ADR Issues

- **No alternative storage technology is considered.** The decision to persist data is implied throughout but no ADR exists for the storage mechanism. The options — SQLite (embedded, file-based, no network dependency), PostgreSQL/MySQL on free-tier cloud (network-dependent, separate service), or a simple JSON file store — each have different implications for free-tier hosting, backup strategy, query capability, and failure modes. No rationale is documented for any choice because no choice has been made. This must appear as either a confirmed decision or an explicit open question.

- **SD-04 (keyword-first routing)** does not discuss the alternative: intent classification via NLP or pattern matching before keyword matching. The document dismisses complexity without naming it. Even a sentence noting "intent-first classification was considered and rejected due to complexity at this scale" would satisfy the trade-off requirement.

- **SD-05 (charts on demand, not persisted)** correctly notes that "chart data is always derivable from LogEntries." However, the consequence — that every chart request requires a full LogEntry retrieval and rendering pass — is not discussed in the context of the 15-second latency target. If a user has 500+ log entries for a parameter, chart generation time may vary. The trade-off between caching and on-demand generation is not acknowledged.

- **The one-shot clarification model (SD-03 / SD-001)** states the rationale ("reduces state complexity") but does not discuss the consequence on the parse failure resolution rate metric. If users ignore clarification prompts at a rate of 30%+, the >80% resolution target in Section 11.1 cannot be met by design. The metric and the architectural decision are in tension, and this tension is not acknowledged.

- **Hard-delete semantics for Parameter deletion (SD-02)** are confirmed without considering the alternative: soft-delete with a purge schedule. The consequence — permanent irreversible data loss on user confirmation — is noted, but the alternative of soft-delete (which would allow a restoration window similar to the account deletion model) is not evaluated. Given the account deletion model uses a soft-delete with a 3-day window, the inconsistency in semantics between account deletion (reversible) and parameter deletion (irreversible) is not justified.

---

## 6. Reliability & Failure Scenario Issues

| Scenario | What is missing | Risk | Priority |
|---|---|---|---|
| 3-day account deletion window expiry | No mechanism is defined to execute the purge when the window expires. No background job, scheduler, or startup sweep is described. | Users believe data will be purged at day 3, but without an enforcement mechanism, the purge never occurs — or occurs non-deterministically. Trust violation. | **P1 — Blocking** |
| Concurrent messages from the same user | No serialization or ordering guarantee is defined. Two messages arriving within milliseconds could race on PendingClarification state, Parameter creation, or User state. | Duplicate LogEntries, duplicate Parameters, or inconsistent PendingClarification state. Direct metric quality impact. | **P1 — Blocking** |
| Bot cold start during a 3-day deletion window | Section 9.3 handles open PendingClarifications on restart. No equivalent behavior is described for the deletion window sweep on restart: does the bot check for expired Pending Deletion accounts on startup? | Expired accounts may not be purged if the bot was down when the expiry occurred. Deletion contract is violated. | **P2 — High** |
| Storage read failure on command dispatch | Section 9.1 handles write failures. No failure behavior is defined for read failures (e.g., history query, chart data retrieval, parameter list fetch). | A storage read failure during a query would produce an unhandled error path with no defined user-facing response. | **P2 — High** |
| Telegram API rate limit hit | Section 8.5 estimates the system operates well within Telegram rate limits. No failure behavior is defined if the rate limit IS exceeded (e.g., developer testing, burst scenario). | An outbound message could be silently dropped if the rate limit is hit with no retry or user notification. | **P3 — Medium** |
| Chart generation timeout (exceeds 15s) | Section 9.2 defines the behavior correctly for the chart exceeding 15s. However, no timeout enforcement mechanism is described — how does the system detect that 15 seconds have elapsed and return the error rather than continuing to wait? | Without timeout enforcement, the chart generation could block the bot process indefinitely, silently blocking all subsequent messages. | **P2 — High** |

---

## 7. Security & Compliance Issues

| Area | Gap | Risk | Priority |
|---|---|---|---|
| Input sanitization for storage | Section 8.7 defines length and character bounds but makes no reference to parameterized queries, escaping, or injection defense. With no named storage technology, this is unverifiable. | If the storage mechanism uses query interpolation, parameter names or log values constructed from user input create injection risk. | **P2 — High** |
| Token exposure in logs | Section 10.2 correctly prohibits the token in source code and config. It does not explicitly prohibit the token appearing in log output (e.g., error stack traces that dump environment variables). | Log output is often less controlled than source code. A stack trace or debug dump could expose the token. Section 10.2 should explicitly include log output in the prohibition. | **P2 — High** |
| Operator data access disclosure | Section 10.4 acknowledges unrestricted operator access and recommends informing users at onboarding. No mechanism for this disclosure is defined in the onboarding flow (Flow 9) or the onboarding session entity. | Users may not receive the disclosure if it is not mandated in the onboarding flow. The control is stated in Section 10 but not enforced in Flow 9. | **P3 — Medium** |
| Non-text input handling | A-02 assumes users only send text. No rejection behavior is defined for non-text inputs (images, voice notes, stickers, forwarded messages). Telegram delivers these as different message types. | Non-text inputs reaching the parse engine could produce undefined behavior, unhandled exceptions, or incorrect parse failure tracking. | **P3 — Medium** |

---

## 8. Observability Issues

| Signal | Missing detail | Operational risk | Priority |
|---|---|---|---|
| Parse failure resolution rate (Section 11.1) | The formula depends on `PendingClarification.state = resolved`. Given the state contradiction identified in Section 3 (the dispatch model always sets `Abandoned`, making `Resolved` unreachable), the numerator of this formula may always be 0 for the PendingClarification component. The formula's correctness depends on resolving the state contradiction. | The primary success metric (>80% resolution rate) would be systematically underreported if `Resolved` is never set. | **P1 — Blocking** |
| Log retention / system log durability | Section 11.6 instructs the developer to "inspect system logs" for error rates. No definition of what the system log is, where it is written, how long it is retained, or whether free-tier hosting preserves logs across restarts. | If logs are ephemeral (written to stdout and discarded on process restart, which is common on free-tier platforms), the developer cannot perform retrospective error analysis. | **P2 — High** |
| Bot availability monitoring | Section 11.4 relies on "periodic direct interaction" by the developer. No minimum check frequency is mandated beyond a parenthetical suggestion. | A multi-hour outage may go undetected. Given the >90% daily availability target (Section 8.2), a 2.4-hour daily outage threshold requires detection within a time window that informal manual checking cannot reliably satisfy. | **P3 — Medium** |
| Deletion window expiry events | No observability signal is defined for account deletion purges. The developer cannot audit whether the 3-day purge executed correctly or at all. | Silent deletion failures (or non-executions) are undetectable without an audit record of purge events. | **P3 — Medium** |

---

## 9. Broken Traceability

| Item (Component/Decision) | Missing Link | Why problematic | Fix |
|---|---|---|---|
| PendingClarification `Resolved` state | Defined in Section 7 but unreachable per Section 5 dispatch model. Section 11.1 observability formula depends on this state being populated. | The state exists in the model, appears in the observability formula, but cannot be set by the described dispatch logic. Three sections are mutually inconsistent. | Reconcile dispatch model and state model: either (a) the clarification resolution handler sets state to `Resolved` before the new message is processed fresh, or (b) the `Resolved` state is removed and the formula in 11.1 is updated accordingly. |
| 3-day deletion enforcement | `deletion_requested_at` timestamp exists on User entity. Flow 10 sets it. No flow, background process, or startup check is described to evaluate and execute the expiry. | The deletion contract cannot be honored by any component described in the document. | Add a description of the enforcement mechanism (startup sweep, scheduled job, or check-on-interaction) to either Section 9 (Failure Behavior Contract) or a new operational process section. |
| Backup / export mechanism | RPO of 24 hours defined in Section 8.3. No export process, format, trigger, or storage destination is described. | The 24-hour RPO is a system requirement with no corresponding system component to implement it. The traceability from risk (data loss) to control (backup) is declared but not closed. | Define the export as a named operational component with at minimum: trigger (scheduled or manual), format, and destination outside the primary hosting environment. |
| "help" / "start" dispatch behavior for Active users | Dispatch table maps `help`, `start` to "Onboarding or help text." No Flow is defined for the case where an Active user sends "start" or "help." | An Active user sending "help" hits an undefined flow. The dispatch table references no Flow ID and Section 6 contains no Flow for this case. | Either add a Help/Start Flow for Active users (returning a command reference message), or explicitly state in the dispatch table what behavior "Onboarding or help text" produces for Active vs. New users. |
| Operator disclosure at onboarding | Section 10.4 requires users be informed of operator data access at onboarding. Flow 9 (First-Time Onboarding) does not include this disclosure as a step. | The control is defined in Section 10 but has no corresponding step in the onboarding flow, making it unenforceable by the system design. | Add an explicit step to Flow 9: "The onboarding welcome message must include a disclosure that the developer/operator has access to all stored data." |

---

## 10. Scoring

| Dimension | Raw Score (0–5) | Weighted Score | Comment |
|---|---|---|---|
| Alignment to Business Goals | 4 | 8 | Traceability section is comprehensive and directly linked to Business v0.3 metrics. Minor gap: MVP scope boundary still open at business layer, which this document correctly flags but cannot resolve. |
| Boundary & Context Consistency | 4 | 4 | Inside/Outside boundary is clean and consistent. No scope drift from Business v0.3. Telegram webhook vs. polling is an unacknowledged boundary-relevant decision. |
| Component Model Quality | 3 | 6 | Six entities are well-specified with attributes and lifecycle. Critical gap: no storage model component is defined, which is the primary implementation-blocking gap. |
| Interaction Model Clarity | 3 | 6 | Eleven flows are described with consistent trigger/processing/output/risk structure. Keyword collision risk unaddressed. Parameter name matching strategy undefined across all query/deletion flows. |
| NFR Coverage & Tactics | 3 | 6 | Quantitative targets for latency, availability, and RPO are a material improvement over v0.1. Backup mechanism specification, cold-start latency bound, and concurrency NFR are missing. |
| Trade-off Justification | 2 | 4 | Decision log entries state rationale but alternatives are rarely considered. No storage technology ADR. One-shot clarification metric tension unacknowledged. Parameter vs. account deletion semantic inconsistency unjustified. |
| Reliability & Failure Handling | 3 | 6 | Four failure scenarios are explicitly contracted in Section 9. 3-day deletion enforcement mechanism absent. Concurrent message handling undefined. Storage read failures not contracted. Chart timeout enforcement unspecified. |
| Security & Compliance Baseline | 3 | 3 | Isolation enforcement, secrets handling, demo data tagging, and operator access disclosure are all addressed. Input injection defense absent. Token-in-logs gap. Non-text input handling undefined. |
| Observability Readiness | 4 | 4 | All three primary success metrics have named signals, formulas, and targets. Parse failure rate formula is at risk from the state contradiction. Log durability undefined. |
| Risk Identification & Mitigation | 4 | 4 | Risk register is comprehensive with 12 well-described risks. Concurrent message risk and chart timeout enforcement risk are missing from the register. |

**Total Score: 51 / 70**

*Score interpretation: 42–55 = Significant refinement required.*

---

## 11. Mandatory Revisions

1. **Resolve the PendingClarification state contradiction.** Reconcile Section 5 (dispatch model), Section 6 (Flow 3), and Section 7 (state model) so that the `Resolved` state is either (a) reachable by the described dispatch logic, with the mechanism described, or (b) removed from the model and the Section 11.1 observability formula updated to not depend on it. The Section 11.1 parse failure resolution rate formula is incorrect under the current state model and must be corrected simultaneously.

2. **Define the storage model.** Add a named section (or a clearly scoped decision entry in the Decision Log) that identifies the storage technology class for the system. At minimum, specify: whether storage is embedded (e.g., SQLite) or external (e.g., a cloud-hosted relational database), what the persistence guarantee of the chosen mechanism is under the free-tier hosting constraint, and how the daily export (Section 8.3) will be triggered and stored. This is the longest-standing critical gap and directly blocks architecture design.

3. **Define the 3-day account deletion enforcement mechanism.** Add a description of the mechanism by which User records in Pending Deletion state are evaluated after 3 days and permanently purged. Name the mechanism (startup sweep, scheduled background task, check-on-next-interaction) and add it to Section 9 as a Failure Behavior scenario or add it as a new named operational process. Describe behavior when the bot was offline during the expiry window.

4. **Address keyword collision risk in the command dispatch model.** Add a disambiguation rule to Section 5 that defines behavior when a user's message begins with a reserved keyword but is plausibly a log-intent message (e.g., "history of my runs 5km"). Options include: require command keywords to appear as the sole leading token followed by a space-separated argument, or define a list of reserved keywords that may not be used as parameter names.

5. **Define the parameter name matching strategy.** Add a named matching rule to Section 5 or Section 4 (Core Entities) that specifies how the system matches user-typed parameter names in Flows 4, 5, 6, 7, and 8. State whether matching is: exact string equality, case-insensitive exact match, prefix match, or approximate. Define the behavior when multiple parameters match the same query.

6. **State the Telegram update delivery model (polling vs. webhook) as a decision or open question.** Add a Decision Log entry or Uncertainty entry for this choice. Include the hosting implications (webhook requires public HTTPS endpoint) and how the choice affects cold-start behavior and the 3-second latency target.

7. **Add a minimum input sanitization requirement to Section 8.7 or Section 10.** State that parameter names and log values received from user input must be sanitized or parameterized before any storage operation. This requirement must be technology-class agnostic and must survive whatever storage decision is made in Revision 2 above.

8. **Explicitly add non-text input rejection to Section 3 (Boundaries) and to the dispatch model.** State that non-text Telegram messages (voice notes, images, stickers, forwarded media) are outside the input boundary. Add a rejection behavior: these message types must be acknowledged with an informative message rather than silently discarded or passed to the parse engine.

9. **Integrate the operator data access disclosure into Flow 9 (First-Time Onboarding).** Section 10.4 defines this as a required disclosure. Flow 9 must include an explicit step that states the welcome/onboarding message will contain this disclosure. The control must be traceable to the flow that enforces it.

10. **Add a Help/Start flow for Active users.** Either define a Flow 12 (or extend Flow 9 with a conditional) to describe what the system returns when an Active user sends `help` or `start`. The dispatch table in Section 5 references "Onboarding or help text" with no corresponding flow definition, leaving this a behavior black hole.

---

## 12. Iteration Recommendation

**Iterate — Targeted Architecture Fixes Required**

System Context Document v0.2 has substantially improved over v0.1 and demonstrates a solid foundation. The document correctly addresses all ten mandatory revisions from the v0.1 review. However, three blocking issues prevent handoff to architecture design: the PendingClarification state contradiction (which invalidates the primary observability metric), the absent storage model (which leaves the entire persistence layer as an open implementation decision), and the undefined 3-day deletion enforcement mechanism (which leaves a user-facing contract without a system component to honor it). Items 1–3 of the Mandatory Revisions above are P1 blockers. Items 4–10 are required but do not independently block architecture design if the P1 items are resolved. The document should be revised to v0.3 addressing at minimum Mandatory Revisions 1, 2, and 3 before proceeding to architecture design.

---
*Review produced against: Architecture Review Critic v1.0 | System Context Document v0.2 | Business Analysis v0.3*
