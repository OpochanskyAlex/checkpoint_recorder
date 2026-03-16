# System Context Document

> **Version:** v0.1
> **Status:** Initial draft — ready for architecture review
> **Based On:** Business Analysis v0.5

---

## Reviewed Business Version

v0.5

---

## 1. System Purpose

The system is a Telegram-native personal metric tracking assistant. It receives free-text messages from registered users inside the Telegram messaging platform, interprets those messages as metric data entries, stores the structured data against opaque user identifiers, and provides users with access to their historical data through chart rendering and threshold-based alerting.

The system does **not** replace Telegram. It operates exclusively within the Telegram messaging interface as a bot, acting as a data-capture and retrieval layer on top of an existing communication channel the user already uses daily.

The system is scoped to support approximately **10 users**, each maintaining approximately **10 tracked metrics**, yielding ~100 active metric time series at steady state. It is a single-operator, portfolio-grade product with no monetization intent at this stage.

---

## 2. Actors

| Actor | Type | Responsibility | Risk if Misaligned |
|---|---|---|---|
| End User | External | Submits free-text metric entries; creates and manages personal metrics; requests charts; receives alerts; manages their account | If users are not already Telegram users, the system has no reach. If users define metrics inconsistently, history becomes fragmented (R-003). |
| Bot Owner / Operator | Internal | Maintains bot registration with Telegram; ensures the bot identity is active and reachable | If the bot's Telegram registration lapses or is revoked, the entire system becomes unreachable |
| Operational Owner / Maintainer | Internal (single person, AI-agent assisted) | Monitors system health; responds to incidents; maintains data integrity; handles user requests outside automated flows | Single person represents a bus-factor risk (R-008). Operational gaps halt all non-automated operations. |
| Telegram Platform | External | Routes messages between users and the bot; provides user identity context to the bot; enforces API usage policies | API policy changes or rate limiting could restrict or disable bot functionality (R-004). Telegram holds user personal identity — data the system itself never stores. |

---

## 3. System Boundaries

### Inside the System

- Reception and acknowledgement of inbound user messages
- Free-text parsing to extract metric name, value(s), and optional context
- Disambiguation flow: when automatic parsing fails, presenting a manual selection prompt to the user and processing their selection response
- User registration on first contact, assigning an opaque internal user identifier
- User onboarding communication: retention policy disclosure, no-export policy disclosure
- Metric creation: recording a new metric with its name and user-defined periodicity
- Metric management: listing a user's metrics, supporting future deduplication or aliasing resolution (R-003 flagged for system design)
- Data entry storage: recording timestamped, structured entries keyed to metric and internal user ID
- Activity monitoring: tracking entry frequency against each metric's defined periodicity to compute active/inactive status
- Threshold alert configuration: recording user-defined alert conditions against a metric
- Threshold alert evaluation: detecting when a new entry crosses a configured alert condition
- Alert notification dispatch: triggering a notification message back to the user via Telegram
- Chart generation: producing a visual representation of a metric's time series on user request
- Account deletion: removing user data upon explicit user request
- Data retention enforcement: maintaining data for at minimum 1 year after last user interaction

### Outside the System

- The Telegram messaging infrastructure (routing, delivery, identity management)
- User identity storage (Telegram holds name, phone, username — the system never receives or stores these)
- Data export to any external format or destination
- ML-based trend prediction or inference
- Multi-language natural language processing
- Voice input processing
- Integration with external data sources (fitness wearables, financial APIs, etc.)
- Web or mobile interface of any kind
- User authentication (delegated entirely to Telegram)

### Boundary Assumptions

1. The system receives messages from Telegram in a structured event format that includes an opaque platform-level user identifier and a message body. The system maps this platform identifier to its own internal opaque user ID.
2. The system dispatches response messages back to the user via Telegram. The delivery guarantee and latency of that delivery are Telegram's responsibility, not the system's.
3. The system has no knowledge of a user's Telegram profile details (name, username, phone number). All processing is keyed to the internal opaque ID only.
4. Alert notifications are delivered through the same Telegram messaging channel used for data entry — no alternative notification channel exists within this system's boundary.
5. Chart output is delivered as an image or inline visual within the Telegram conversation. Rendering fidelity depends on Telegram's display capabilities.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships | Ownership & Lifecycle |
|---|---|---|---|---|
| **InternalUser** | An opaque, de-personalized representation of a registered bot user. Contains no personal data. | `internal_user_id` (opaque, system-assigned), `first_interaction_timestamp`, `last_interaction_timestamp` | Owns zero or more Metrics; owns zero or more Entries (indirectly through Metrics) | Created on first contact with the bot. Retained for minimum 1 year after `last_interaction_timestamp`. Deleted on explicit user account deletion request. |
| **Metric** | A named, user-defined measurement axis with a defined periodicity. Created implicitly on first data entry or explicitly by user command. | `metric_id`, `internal_user_id` (owner), `name` (user-defined string), `periodicity` (e.g., daily, weekly — set at creation), `created_at`, `status` (active / inactive) | Belongs to one InternalUser; has zero or more Entries; has zero or more Alerts | Created by user. Lifecycle tied to InternalUser. Name is as defined by user — no normalisation enforced at this stage (collision risk R-003 remains). |
| **Entry** | A single recorded data point for a metric at a specific point in time. | `entry_id`, `metric_id`, `internal_user_id`, `raw_input` (original free-text), `parsed_value(s)` (one or more numeric/string values), `entry_timestamp`, `resolution_method` (auto-parsed / user-selected) | Belongs to one Metric and one InternalUser | Created when a data entry flow completes successfully. Immutable after creation. Never modified — a correction would be a new entry. |
| **ParseAttempt** | **[Inferred Model Element]** A transient record of an in-progress free-text parsing attempt that has not yet been resolved. Exists only when automatic parsing was inconclusive and a manual selection prompt has been issued to the user. | `attempt_id`, `internal_user_id`, `raw_input`, `candidate_metrics` (list), `issued_at` | Associated with one InternalUser; resolves to one Entry or is abandoned | Created when parse confidence is insufficient. Resolved when user responds to the selection prompt or the interaction is abandoned. Should not persist indefinitely — expiry behaviour is an open system-design question. |
| **Alert** | A user-defined threshold condition on a metric. Fires when a new entry satisfies the condition. | `alert_id`, `metric_id`, `internal_user_id`, `condition_type` (e.g., above / below), `threshold_value`, `status` (active / paused / deleted) | Belongs to one Metric and one InternalUser | Created by user. Evaluated on every new Entry for the associated Metric. Can be deactivated or deleted. |
| **MetricActivityStatus** | **[Inferred Model Element]** A derived, computed view of whether a metric meets the active-user definition (≥4 entries in last 5 periods of the metric's own periodicity). Not necessarily a stored entity — may be computed on demand. | `metric_id`, `internal_user_id`, `periodicity`, `recent_period_entries` (count of last 5 periods filled), `is_active` (boolean) | Derived from Entries for a given Metric | Not independently owned. Computed from Entry history. Critical for success metric measurement (tracking retention). |

---

## 5. Data & Interaction Flows

---

### Flow 1: User First Contact & Onboarding

- **Trigger:** A Telegram user sends a message to the bot for the first time (no existing InternalUser record for their platform ID).
- **Actor:** End User
- **Input:** Any inbound message (could be a greeting, a data entry, or a command).
- **System Processing:**
  1. System detects no InternalUser record for the incoming platform user identifier.
  2. System creates a new InternalUser, assigning an opaque internal ID.
  3. System dispatches an onboarding message communicating: (a) the data retention policy (1 year minimum after last interaction, lifetime in practice), (b) the no-export limitation, (c) basic usage guidance.
  4. System then processes the original inbound message as per the appropriate flow (entry, command, etc.).
- **Output:** Onboarding message delivered to user. InternalUser record created.
- **Risk Points:**
  - If onboarding message is not delivered or not read, user proceeds without awareness of the no-export limitation or retention policy. This is a trust and transparency risk (linked to R-006, D-010).
  - If the inbound message that triggered registration is also a data entry, the system must handle both flows atomically — partial failure could result in a registered user with a lost first entry.

---

### Flow 2: Data Entry — Successful Automatic Parse

- **Trigger:** A registered user sends a free-text message interpretable as a metric entry.
- **Actor:** End User
- **Input:** Free-text message (e.g., `weight 82.5`, `ran 5km`, `mood 7`, `80kg 5reps`).
- **System Processing:**
  1. System receives the message and attempts to parse it: identify the target Metric by name match against the user's existing metrics, and extract the associated value(s).
  2. If the metric name does not exist for this user, the system creates a new Metric record. The periodicity of a newly created metric must be obtained from the user — **[Assumption: a metric creation sub-flow is triggered requesting periodicity before the entry is stored; see Assumption 3]**.
  3. System stores a new Entry record with the parsed value(s), timestamp, and `resolution_method = auto-parsed`.
  4. System evaluates any active Alerts on this Metric (see Flow 5).
  5. System dispatches a confirmation message to the user.
- **Output:** Entry stored. Confirmation sent. Alert(s) evaluated.
- **Risk Points:**
  - A confident auto-parse may still be semantically wrong (e.g., `weight 82.5` stored against a metric named `weight` when the user meant a newly coined metric). No mechanism exists to correct this post-hoc other than a new entry.
  - Compound multi-value entries (e.g., `80kg 5reps`) require the parser to handle multi-value extraction — parsing complexity is higher for athlete use cases (Stakeholder row in §3).
  - New metric creation during an entry flow creates an interruption — if the user abandons the periodicity sub-flow, the entry may be left in an unresolved state (R-003 adjacent).

---

### Flow 3: Data Entry — Parse Failure & Manual Selection

- **Trigger:** A registered user sends a free-text message that the system cannot confidently resolve to a specific Metric.
- **Actor:** End User
- **Input:** Ambiguous or unrecognized free-text message.
- **System Processing:**
  1. System attempts automatic parse and determines confidence is insufficient.
  2. System creates a transient ParseAttempt record preserving the raw input.
  3. System dispatches a manual selection prompt to the user, listing candidate Metrics (or offering "create new").
  4. System waits for user selection response.
  5. On user selection: system stores the Entry against the chosen Metric with `resolution_method = user-selected`, and discards the ParseAttempt.
  6. On user abandonment or timeout: ParseAttempt expires; no Entry is stored; raw input is not silently discarded (confirmed — D-012).
- **Output:** Entry stored (if user selects), or input discarded with user acknowledgement (if abandoned). No silent data loss.
- **Risk Points:**
  - The system must maintain state between the outbound prompt and the inbound user selection. Stateless handling would break this flow.
  - If the user sends a new message before responding to the selection prompt, the system must decide whether to treat the new message as the selection response or as a new independent input — ambiguous conversation-state management.
  - If no candidate metrics are surfaced in the prompt (e.g., user has no existing metrics), "create new" must be the offered path.
  - Expiry behaviour for unresolved ParseAttempts is not defined in the business document — **[Assumption 4]**.

---

### Flow 4: Chart Request

- **Trigger:** A registered user requests a visual chart of one or more metrics.
- **Actor:** End User
- **Input:** Chart command referencing one or more metric names and optionally a time range.
- **System Processing:**
  1. System identifies the referenced Metric(s) for this user.
  2. System retrieves the Entry history for the specified Metric(s) and time range.
  3. System generates a chart image from the time-series data.
  4. System dispatches the chart as a visual message to the user via Telegram.
- **Output:** Chart image delivered to user.
- **Risk Points:**
  - If the referenced metric name does not exactly match a stored Metric for the user, the system must handle the not-found case gracefully (error message, suggestions).
  - If a metric has too few entries to render a meaningful chart, the output may be misleading or unhelpful — user experience risk.
  - Chart image rendering must be compatible with Telegram's display format — a boundary constraint tied to the Telegram platform dependency.

---

### Flow 5: Alert Evaluation & Notification

- **Trigger:** A new Entry is stored for a Metric that has one or more active Alerts.
- **Actor:** System (automated, no user action required)
- **Input:** Newly stored Entry, associated Alert condition(s).
- **System Processing:**
  1. System retrieves all active Alerts for the Metric associated with the new Entry.
  2. For each Alert: evaluates whether the entry's value satisfies the alert condition (e.g., value > threshold).
  3. For each satisfied Alert: dispatches a notification message to the owning InternalUser via Telegram.
- **Output:** Alert notification delivered to user (if condition met). No action if condition not met.
- **Risk Points:**
  - Multi-value entries (e.g., `80kg 5reps`) require clarity on which value an alert evaluates against — alert configuration must specify the target value dimension.
  - If Telegram message dispatch fails, the alert fires internally but the user never receives the notification — no retry or delivery confirmation mechanism is defined.
  - Alert accuracy is a tracked success metric (>95% target); incorrect alert firing or missed alerts are measurable failures.

---

### Flow 6: Account Deletion

- **Trigger:** A registered user explicitly requests deletion of their account and data.
- **Actor:** End User
- **Input:** Account deletion command.
- **System Processing:**
  1. System confirms intent with the user (confirmation step is an **[Assumption]** — not explicitly described in business document but standard for destructive operations).
  2. System permanently deletes all data associated with the InternalUser: Entries, Metrics, Alerts, any pending ParseAttempts.
  3. System deletes the InternalUser record.
  4. System dispatches a confirmation of deletion to the user.
- **Output:** All user data deleted. User effectively becomes unregistered — any future message would trigger onboarding again.
- **Risk Points:**
  - Deletion is irreversible. No export exists (R-006, D-010). Once deleted, data cannot be recovered.
  - If the confirmation step is absent and a user accidentally triggers deletion, total data loss occurs with no recourse.
  - The system cannot prevent or undo Telegram-side identity changes — if a user's Telegram account is lost/deleted before account deletion is requested, their bot data persists under the 1-year retention guarantee with no user-accessible recovery path.

---

## 6. State Model

### InternalUser States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Unregistered** | Default state — user has not interacted with the bot | User sends first message to the bot | Registered | If Telegram platform ID changes for the same physical user (e.g., account recovery), a new InternalUser is created — history fragmentation |
| **Registered — Active** | First message received; onboarding complete; InternalUser record created | User ceases all interaction (inactivity) OR requests deletion | Registered — Inactive, Deleted | None specific |
| **Registered — Inactive** | No interaction received for a period that would qualify no metrics as "active" | User sends a new message | Registered — Active | User data must be retained for 1 year after `last_interaction_timestamp` even in this state |
| **Deleted** | User explicitly requests account deletion | N/A — terminal state | (none) | Irreversible; no data recovery path |

---

### Metric States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Pending Periodicity** | Metric name referenced in an entry but no matching Metric exists; creation flow initiated | User provides periodicity OR user abandons flow | Active, Abandoned | If abandoned, the triggering entry is also unresolved — potential data loss |
| **Active** | Metric exists with defined periodicity; entries are being logged against it | No entries logged for a sustained period (inactivity) OR explicit deletion | Inactive, Deleted | |
| **Inactive** | No entries logged for a period exceeding the metric's own periodicity window | User logs a new entry against this metric | Active | Inactive metrics still count toward data retention obligations |
| **Deleted** | User explicitly deletes a metric | N/A — terminal state | (none) | All historical Entries for this metric are also deleted — data loss risk |

---

### Entry States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Received** | Inbound message arrives and is attributed to a registered user | Parse attempt begins immediately | Parsing |  |
| **Parsing** | System is processing the raw input text | Parse succeeds with confidence OR parse confidence insufficient | Stored (auto), Awaiting Selection | Transient state — should not persist beyond a single processing cycle |
| **Awaiting Selection** | Parse was inconclusive; manual selection prompt dispatched to user | User selects a metric OR session times out / user abandons | Stored (manual), Discarded | State persists until user responds — conversation-state management required |
| **Stored** | Entry successfully written with metric association and value(s) | N/A — terminal state (entries are immutable) | (none) | Immutable; no correction mechanism exists — a wrong entry remains in history |
| **Discarded** | User abandoned the manual selection flow OR explicit discard | N/A — terminal state | (none) | Raw input is not silently lost but is also not recoverable after discard |

---

### Alert States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Configured** | User creates an alert with a condition and threshold on a metric | First Entry evaluated against this alert | Monitoring | |
| **Monitoring** | Alert is active; each new Entry for the associated Metric is evaluated | Alert condition satisfied by a new entry OR user deactivates/deletes the alert | Triggered, Paused, Deleted | |
| **Triggered** | Alert condition was satisfied; notification dispatched to user | Alert automatically returns to Monitoring after notification (assumed — see Assumption 5) | Monitoring | Alert delivery is not guaranteed — Telegram dispatch failure is a silent risk |
| **Paused** | User explicitly pauses the alert | User re-activates the alert | Monitoring | Paused alerts are not evaluated — entries during pause period will not fire the alert retroactively |
| **Deleted** | User explicitly deletes the alert | N/A — terminal state | (none) | |

---

## 7. External Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Messaging Platform | Primary input/output channel — all user interactions occur via Telegram; provides opaque user identity context | Hard dependency — system is non-functional without it | High (R-004) |
| Telegram Bot API | Programmatic interface through which the system sends and receives messages, dispatches images, and presents selection prompts | Hard dependency — all system I/O passes through this interface | High (R-004) |

> **Note:** No other external systems are identified as dependencies. The business document explicitly excludes all external integrations (fitness wearables, financial APIs, etc.) from scope.

---

## 8. Assumptions

1. **The Telegram platform provides a stable, opaque, per-user identifier that the system can use as the key for mapping to its own internal user ID.**
   - *Why it exists:* The privacy-by-design constraint (D-007) requires that the system never stores personal data. The system needs a stable platform-level identifier to map to its opaque internal ID.
   - *Risk if false:* If the platform identifier changes across sessions for the same user (e.g., account migration), the system would create duplicate InternalUser records and fragment the user's history.
   - *Validation idea:* Confirm stability of Telegram's user ID in bot API documentation before system design begins.

2. **A metric name collision (e.g., `mood` vs `Mood` vs `moood`) is treated as distinct metrics by the system until a deduplication or aliasing mechanism is introduced.**
   - *Why it exists:* The business document flags R-003 (parameter name collision) but defers the resolution mechanism to system design. The system must behave consistently in the absence of that mechanism.
   - *Risk if false:* If the system silently merges similar-looking metric names, entries may be stored under the wrong metric.
   - *Validation idea:* Define deduplication/aliasing rules explicitly during system design before first user data is collected.

3. **When a user submits a free-text entry that references a metric that does not yet exist, the system initiates a metric creation sub-flow requesting the periodicity before storing the entry.**
   - *Why it exists:* Periodicity is mandatory at metric creation (D-014), and it cannot be inferred. The business document does not explicitly describe the cross-flow between implicit metric creation and entry submission.
   - *Risk if false:* If periodicity is not collected at creation time, the system cannot compute active-user status for that metric, breaking the success metric measurement.
   - *Validation idea:* Confirm with stakeholder whether implicit metric creation (via entry) follows the same creation flow as explicit metric creation.

4. **A ParseAttempt (pending manual selection) expires and is discarded if the user does not respond within a defined timeout window.**
   - *Why it exists:* The business document (D-012) states that input is not silently discarded, but does not define what happens if the user never responds to the selection prompt. The system cannot hold state indefinitely.
   - *Risk if false:* If no expiry exists, stale ParseAttempts accumulate and may interfere with subsequent valid entries.
   - *Validation idea:* Define and confirm expiry behaviour with stakeholder during system design.

5. **After an Alert fires and the notification is dispatched, the Alert automatically returns to the Monitoring state and will fire again on the next qualifying entry.**
   - *Why it exists:* The business document does not describe alert lifecycle beyond firing. A one-shot alert vs. a repeating alert represents a meaningful design choice.
   - *Risk if false:* If alerts are one-shot (deleted after firing), users must reconfigure them after each trigger — poor user experience.
   - *Validation idea:* Confirm expected alert lifecycle (one-shot vs. persistent) with stakeholder.

6. **Chart requests reference a single metric or a small, fixed number of metrics per request.**
   - *Why it exists:* The business document does not specify the scope of chart requests. Unbounded multi-metric chart requests introduce complexity.
   - *Risk if false:* If users expect multi-metric overlay charts, the chart generation and command parsing logic is significantly more complex.
   - *Validation idea:* Confirm expected chart scope with stakeholder during system design.

---

## 9. Risks

| Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|
| R-001 (inherited) | Business | High — product solves the wrong problem | Low–Medium | Accepted as premise. Monitor tracking retention against 40% target as the earliest signal. |
| R-002 (inherited) | Behavioral / System | High — corrupted user history | High | Manual selection fallback is the confirmed mitigation. Parse ambiguity surface area must be precisely defined during system design. |
| R-003 (inherited) | Behavioral | Medium — fragmented metric history | High | Deduplication / aliasing mechanism must be addressed in system design before launch. |
| R-004 (inherited) | System | High — full service disruption | Low–Medium | Accepted dependency. No mitigation in scope. |
| R-005 (inherited) | System / Business | Critical — user trust destruction | Low | Strict user isolation: all data queries must be scoped to a verified InternalUser ID. Isolation must be tested explicitly. Success metric: 100% isolation integrity. |
| R-006 (inherited) | Business | Medium — data unrecoverable on account/Telegram loss | Medium | Accepted. Users informed at onboarding. 1-year retention provides a partial recovery window. |
| R-007 (inherited) | Business / Factual | Low (mitigated by design) | Low | No personal data stored. Residual risk is Telegram-side and outside this system's boundary. |
| R-008 (inherited) | Business | Medium — operational gaps on single owner unavailability | Medium | Accepted. AI-agent assistance reduces burden. |
| R-009 (new — system) | System | Medium — orphaned ParseAttempts degrade conversation state | Medium | Define expiry behaviour and cleanup mechanism for unresolved ParseAttempts. Covered in Assumption 4. |
| R-010 (new — system) | Behavioral | Medium — user sends new message before completing selection prompt; conversation state corrupted | Medium | System design must define conversation-state management and conflict resolution for concurrent interaction flows. |
| R-011 (new — system) | System | Low–Medium — alert notification dispatch fails silently | Low–Medium | System design should define retry or dead-letter behaviour for failed alert dispatches to meet the >95% alert accuracy target. |
| R-012 (new — system) | Behavioral | Low–Medium — implicit metric creation during entry flow creates an unresolved entry if user abandons periodicity sub-flow | Medium | System design must define atomicity of the combined entry + metric creation flow. See Assumption 3. |

---

## 10. Logical Consistency Check

**Are there gaps in lifecycle?**

- **ParseAttempt expiry** is not defined. A ParseAttempt in "Awaiting Selection" state has no defined terminal transition if the user never responds. This is flagged as Assumption 4 and R-009. This gap must be closed during system design.
- **Metric created implicitly during entry** (Assumption 3): the lifecycle intersection between Metric "Pending Periodicity" state and Entry "Awaiting Selection" / "Parsing" state is not fully modelled. Both flows can be in-progress simultaneously for the same user, creating a compound state that needs explicit handling.
- **InternalUser retention after deletion request**: once Deleted, no re-registration barrier exists. A user who deletes their account and re-contacts the bot will be treated as a brand-new user. This is consistent with the no-personal-data model but means any "1-year guarantee" window for the deleted account is abandoned. This is accepted behaviour but should be confirmed.

**Are any actors undefined?**

- No undefined actors. All four actors (End User, Bot Owner / Operator, Operational Owner, Telegram Platform) are modelled. The Operational Owner's interactions are primarily out-of-band (system monitoring, incident response) and do not generate in-system flows — this is appropriate given the scope.

**Are there ambiguous states?**

- The boundary between `Registered — Active` and `Registered — Inactive` for InternalUser is not quantitatively defined. The business document defines "active user" in terms of per-metric activity, not user-level inactivity. An InternalUser with all inactive metrics is effectively "Registered — Inactive" by inference. This mapping needs to be made explicit.
- `Alert — Triggered` → `Alert — Monitoring` transition is assumed (Assumption 5) and not confirmed by the business document. The state is ambiguous until confirmed.

**Are there circular flows?**

- No circular flows detected. The Entry lifecycle is strictly linear (Received → Parsing → Stored/Discarded). The Alert lifecycle returns to Monitoring after firing — this is a legitimate cycle by design, not a problematic circular dependency.
- The manual selection flow (Flow 3) is a branching path of Flow 2, not a loop — it terminates in either a Stored or Discarded entry.

---

## Version

v0.1

## Based On

Business Analysis v0.5

## Changes Introduced

- Initial system context document derived from Business Analysis v0.5.
- System boundaries defined: 12 in-scope capabilities identified; 9 out-of-scope items confirmed.
- 5 core entities identified: InternalUser, Metric, Entry, ParseAttempt (inferred), Alert; MetricActivityStatus noted as a derived/computed element.
- 6 interaction flows modelled: Onboarding, Successful Entry, Parse Failure & Manual Selection, Chart Request, Alert Evaluation, Account Deletion.
- State models defined for 4 entity types: InternalUser (4 states), Metric (5 states), Entry (5 states), Alert (5 states).
- 2 external dependencies identified: Telegram Platform and Telegram Bot API.
- 6 system-level assumptions introduced (Assumptions 1–6) to cover gaps not resolved by business document.
- 4 new system risks introduced (R-009 through R-012) beyond the 8 inherited business risks.

---

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| SD-001 | ParseAttempt introduced as an inferred transient entity | Business document confirms manual selection fallback (D-012) but does not name the intermediate state. A stateful prompt-response interaction requires a transient record. | v0.1 | Open — requires stakeholder confirmation of expiry behaviour |
| SD-002 | MetricActivityStatus modelled as a derived/computed element, not a stored entity | Active-user status is a measurement construct defined in business §5. Whether it is stored or computed on demand is a system design decision deferred to architecture. | v0.1 | Deferred to system design |
| SD-003 | Alert lifecycle assumed to be persistent (repeating), not one-shot | One-shot alerts would require user reconfiguration after each trigger, which is inconsistent with low-friction design intent. Assumption 5 must be confirmed. | v0.1 | Open — requires stakeholder confirmation |
| SD-004 | Account deletion assumed to include a confirmation step | Destructive irreversible operation with no recovery path. Absence of confirmation would create a critical user experience risk aligned with R-006. | v0.1 | Open — requires stakeholder confirmation |

---

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| SU-001 | System | ParseAttempt expiry and abandonment behaviour not defined | Unresolved ParseAttempts accumulate; conversation state degrades | Confirm with stakeholder; define expiry rule during system design |
| SU-002 | Behavioral | Conversation-state conflict when user sends new message during active selection prompt | Entry routing ambiguity; potential mis-assignment of entries | Define conflict resolution rule during system design |
| SU-003 | System | Alert lifecycle post-trigger (one-shot vs. persistent repeating) not confirmed | Alert state model is incomplete until confirmed | Confirm with stakeholder (see SD-003) |
| SU-004 | Behavioral | Implicit metric creation during entry — periodicity collection sub-flow not described | If periodicity sub-flow is not defined, active-user measurement cannot function for implicitly created metrics | Confirm sub-flow design with stakeholder (see Assumption 3) |
| SU-005 | System | InternalUser "Inactive" boundary condition not quantitatively defined | Retention monitoring and active-user reporting may produce inconsistent results | Define inactivity threshold during system design |

---

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Reduce tracking abandonment (retention >40%) | MetricActivityStatus (derived entity); Flow 2 & 3 (entry capture); Metric states; InternalUser Active/Inactive states | R-001 (premise may be wrong); R-002 (parse failures reduce captured entries); R-012 (abandoned metric creation loses first entry) |
| Enable self-insight through history (charts >25%) | Flow 4 (Chart Request); Entry entity (immutable time-series); Metric entity | R-006 (no export; chart is the only data visibility path); R-003 (fragmented metrics produce fragmented charts) |
| User data privacy and trust (isolation 100%) | InternalUser entity (opaque ID, no personal data); all flows scoped by internal_user_id | R-005 (cross-user data leak); R-007 (Telegram holds identity — residual, out of scope) |
| Alert delivery accuracy (>95%) | Flow 5 (Alert Evaluation); Alert state model | R-011 (silent dispatch failure); SU-003 (alert lifecycle ambiguity) |
| Service continuity | Operational Owner actor; Telegram Platform external dependency | R-004 (Telegram API policy change); R-008 (single operator bus factor) |
| Portfolio demonstration | All entities, flows, and states collectively | R-003 (parameter collisions fragment history, degrading demo quality) |
