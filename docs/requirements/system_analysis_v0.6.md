# System Context Document

> **Version:** v0.6
> **Status:** Revised draft — addressing mandatory revisions from system_analysis_v0.5_review.md
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

| Actor | Type (Internal/External) | Responsibility | Risk if Misaligned |
|---|---|---|---|
| End User | External | Submits free-text metric entries; creates and manages personal metrics; requests charts; configures and manages alerts; receives alert notifications; manages their account | If users are not already Telegram users, the system has no reach. If users define metrics inconsistently, history becomes fragmented (R-003). |
| Bot Owner / Operator | Internal | Maintains bot registration with Telegram; ensures the bot identity is active and reachable | If the bot's Telegram registration lapses or is revoked, the entire system becomes unreachable |
| Operational Owner / Maintainer | Internal (single person, AI-agent assisted) | Monitors system health; responds to incidents; maintains data integrity; handles user requests outside automated flows | Single person represents a bus-factor risk (R-008). Operational gaps halt all non-automated operations. |
| Telegram Platform | External | Routes messages between users and the bot; provides user identity context to the bot; enforces API usage policies | API policy changes or rate limiting could restrict or disable bot functionality (R-004). Telegram holds user personal identity — data the system itself never stores. |

---

## 3. System Boundaries

### Inside the System

- Reception and acknowledgement of inbound user messages
- Free-text parsing to extract metric name, value(s), and optional context
- Disambiguation flow: when automatic parsing fails, presenting a manual selection prompt to the user and processing their selection response
- User registration on first contact, assigning an opaque internal user identifier (**identity mapping**, not authentication — see Boundary Assumptions §4)
- User onboarding communication: retention policy disclosure, no-export policy disclosure
- Metric creation: recording a new metric with its name and user-defined periodicity — via explicit user command or implicitly triggered during a data entry flow
- Metric management: listing a user's metrics with active/inactive status, supporting future deduplication or aliasing resolution (R-003 flagged for system design)
- Data entry storage: recording timestamped, structured entries keyed to metric and internal user ID
- Activity monitoring: tracking entry frequency against each metric's defined periodicity to compute active/inactive status
- Threshold alert configuration: recording user-defined alert conditions against a metric
- Threshold alert management: pausing, re-activating, and deleting existing alert configurations
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
- - User authentication (verifying a sender's identity — delegated entirely to Telegram; the system only maps the platform-provided identifier)

### Boundary Assumptions

1. The system receives messages from Telegram in a structured event format that includes an opaque platform-level user identifier and a message body. The system maps this platform identifier to its own internal opaque user ID.
2. The system dispatches response messages back to the user via Telegram. The delivery guarantee and latency of that delivery are Telegram's responsibility, not the system's.
3. The system has no knowledge of a user's Telegram profile details (name, username, phone number). All processing is keyed to the internal opaque ID only.
4. **Identity mapping is in scope; identity authentication is out of scope.** The system performs identity mapping: associating an incoming Telegram platform identifier with an opaque internal user ID. It does not authenticate the sender. Authentication — verifying that a given message originates from a legitimate account holder — is Telegram's responsibility. The system trusts the platform-provided identifier entirely.
5. Alert notifications are delivered through the same Telegram messaging channel used for data entry — no alternative notification channel exists within this system's boundary.
6. Chart output is delivered as an image or inline visual within the Telegram conversation. Rendering fidelity depends on Telegram's display capabilities.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships | Ownership & Lifecycle |
|---|---|---|---|---|
| **InternalUser** | An opaque, de-personalized representation of a registered bot user. Contains no personal data. | `internal_user_id` (opaque, system-assigned), `first_interaction_timestamp`, `last_interaction_timestamp` | Owns zero or more Metrics; owns zero or more Entries (via Metrics); owns zero or more Alerts (via Metrics) | Created on first contact with the bot. Retained for minimum 1 year after `last_interaction_timestamp`. Deleted on explicit user account deletion request. |
| **Metric** | A named, user-defined measurement axis with a defined periodicity. Created implicitly on first data entry or explicitly by user command. | `metric_id`, `internal_user_id` (owner), `name` (user-defined string), `periodicity` (e.g., daily, weekly — set at creation), `created_at`, `status` (active / inactive — stored flag, updated by MetricActivityStatus computation; see note below) | Belongs to one InternalUser; has zero or more Entries; has zero or more Alerts | Created by user. Lifecycle tied to InternalUser. Name is as defined by user — no normalisation enforced at this stage (collision risk R-003 remains). Deletion cascades to all associated Entries and Alerts. |
| **Entry** | A single recorded data point for a metric at a specific point in time. | `entry_id`, `metric_id`, `internal_user_id`\*, `raw_input` (original free-text), `parsed_value(s)` (one or more numeric/string values), `entry_timestamp`, `resolution_method` (auto-parsed / user-selected) | Belongs to one Metric and one InternalUser | Created when a data entry flow completes successfully. **Immutable from a user perspective**: individual entries cannot be modified or selectively deleted by a user — a correction is made by creating a new entry. However, Entries are cascade-deleted when their parent Metric is explicitly deleted. This is the only mechanism by which a stored Entry is removed. |
| **ParseAttempt** | **[Inferred Model Element]** A transient record of an in-progress free-text parsing attempt that has not yet been resolved. Exists only when automatic parsing was inconclusive and a manual selection prompt has been issued to the user. | `attempt_id`, `internal_user_id`, `raw_input`, `candidate_metrics` (list), `issued_at`, `expiry_timestamp` | Associated with one InternalUser; resolves to one Entry or expires | Created when parse confidence is insufficient. Resolved when user responds to the selection prompt, or expires when `expiry_timestamp` is reached. Must not persist indefinitely. |
| **Alert** | A user-defined threshold condition on a metric. Fires when a new entry satisfies the condition. | `alert_id`, `metric_id`, `internal_user_id`\*, `condition_type` (e.g., above / below), `threshold_value`, `target_value_dimension` (for multi-value entries: identifies which value dimension this alert evaluates; optional for single-value metrics), `status` (monitoring / paused / deleted) | Belongs to one Metric and one InternalUser | Created by user. Evaluated on every new Entry for the associated Metric. Can be paused, re-activated, or deleted. |
| **MetricActivityStatus** | **[Inferred Model Element]** A computation rule that determines whether a metric meets the active definition: ≥4 entries logged in the last 5 periods of the metric's own periodicity. The result of this computation is stored back to the `status` attribute on the Metric entity. MetricActivityStatus is the computation mechanism; `status` on Metric is the cached/stored result of that computation. These are not competing constructs — they describe the same concept at different levels (rule vs. stored value). Risk: if computation is not triggered on every relevant event, `status` may become stale. | `metric_id`, `internal_user_id`, `periodicity`, `recent_period_entries` (count of last 5 periods filled), `is_active` (boolean result) | Derived from Entries for a given Metric; result drives update of Metric.`status` | Not independently owned. Computed from Entry history. Critical for success metric measurement (tracking retention). |

> \* **Referential integrity note (Entry.`internal_user_id` and Alert.`internal_user_id`):** These attributes are derivable transitively via the Metric relationship. They are retained for direct association and query clarity but introduce a potential referential inconsistency: the `internal_user_id` on Entry or Alert must always equal the `internal_user_id` of the owning Metric. This constraint must be enforced by system design — no entry or alert should ever be associated with a user different from the owning metric's user. See R-015.

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
  - If the inbound message that triggered registration is also a data entry for a metric that does not yet exist, the system encounters a three-way compound flow: Onboarding (Flow 1) + Data Entry (Flow 2) + Metric Creation sub-flow (Flow 7). The failure modes for partial success across any of these legs are undefined and must be explicitly handled in system design.

---

### Flow 2: Data Entry — Successful Automatic Parse

- **Trigger:** A registered user sends a free-text message interpretable as a metric entry.
- **Actor:** End User
- **Input:** Free-text message (e.g., `weight 82.5`, `ran 5km`, `mood 7`, `80kg 5reps`).
- **System Processing:**
  1. System receives the message and attempts to parse it: identify the target Metric by name match against the user's existing metrics, and extract the associated value(s).
  2. If the metric name does not exist for this user, the system initiates the Standalone Metric Creation sub-flow (see Flow 7). The data entry is held pending metric creation completion. If the user abandons the metric creation sub-flow, the entry is also left unresolved and is discarded (R-012).
  3. System stores a new Entry record with the parsed value(s), timestamp, and `resolution_method = auto-parsed`.
  4. System evaluates any active Alerts on this Metric (see Flow 5).
  5. System dispatches a confirmation message to the user.
- **Output:** Entry stored. Confirmation sent. Alert(s) evaluated.
- **Risk Points:**
  - A confident auto-parse may still be semantically wrong (e.g., `weight 82.5` stored against a metric named `weight` when the user intended a newly coined metric). No mechanism exists to correct this post-hoc other than a new entry.
  - Compound multi-value entries (e.g., `80kg 5reps`) require the parser to handle multi-value extraction — parsing complexity is higher for athlete use cases.
  - New metric creation during an entry flow creates an interruption — if the user abandons the periodicity sub-flow, the pending entry is also unresolved (R-012).

---

### Flow 3: Data Entry — Parse Failure & Manual Selection

- **Trigger:** A registered user sends a free-text message that the system cannot confidently resolve to a specific Metric.
- **Actor:** End User
- **Input:** Ambiguous or unrecognized free-text message.
- **System Processing:**
  1. System attempts automatic parse and determines confidence is insufficient.
  2. System creates a transient ParseAttempt record preserving the raw input and setting `expiry_timestamp`.
  3. System dispatches a manual selection prompt to the user, listing candidate Metrics (or offering "create new").
  4. System waits for user selection response. ParseAttempt is now in the "Awaiting Selection" state.
  5. On user selection: system stores the Entry against the chosen Metric with `resolution_method = user-selected`. ParseAttempt is resolved and discarded.
  6. On timeout (expiry_timestamp reached) or explicit user cancellation: ParseAttempt expires. System dispatches an acknowledgement message to the user informing them that the pending input has been discarded and no entry was stored. The raw input is not silently lost — the user is notified (D-012).
- **Output:** Entry stored (if user selects), or user notified of discarded input (if expired or cancelled). No silent data loss.
- **Risk Points:**
  - The system must maintain conversation state between the outbound prompt and the inbound user selection. Stateless handling would break this flow.
  - If the user sends a new message before responding to the selection prompt, the system must decide whether to treat the new message as the selection response or as a new independent input — ambiguous conversation-state management (R-010).
  - If no candidate metrics are surfaced in the prompt (e.g., user has no existing metrics), "create new" must be the offered path.

---

### Flow 4: Chart Request

- **Trigger:** A registered user requests a visual chart of one or more metrics.
- **Actor:** End User
- **Input:** Chart command referencing one or more metric names and optionally a time range.
- **System Processing:**
  1. System identifies the referenced Metric(s) for this user.
  2. System retrieves the Entry history for the specified Metric(s) and time range.
  3. System generates a chart image from the time-series data via the Chart Rendering Component (see §7).
  4. System dispatches the chart as a visual message to the user via Telegram.
- **Output:** Chart image delivered to user.
- **Risk Points:**
  - If the referenced metric name does not exactly match a stored Metric for the user, the system must handle the not-found case gracefully (error message, suggestions).
  - If a metric has too few entries to render a meaningful chart, the output may be misleading or unhelpful — user experience risk.
  - Chart image rendering must be compatible with Telegram's display format — a boundary constraint tied to the Telegram platform dependency.
  - Chart Rendering Component failure would silently block this flow if not handled (R-016).

---

### Flow 5: Alert Evaluation & Notification

- **Trigger:** A new Entry is stored for a Metric that has one or more active Alerts.
- **Actor:** System (automated, no user action required)
- **Input:** Newly stored Entry, associated Alert condition(s).
- **System Processing:**
  1. System retrieves all Alerts in Monitoring state for the Metric associated with the new Entry.
  2. For each Alert: evaluates whether the entry's value satisfies the alert condition (e.g., value > threshold). For multi-value entries, evaluation is performed against the Alert's `target_value_dimension`.
  3. For each satisfied Alert: dispatches a notification message to the owning InternalUser via Telegram. Alert transitions to Triggered state, then automatically returns to Monitoring after notification dispatch (Assumption 5).
- **Output:** Alert notification delivered to user (if condition met). No action if condition not met.
- **Risk Points:**
  - Multi-value entries require clarity on which value an alert evaluates against — this is addressed by the `target_value_dimension` attribute on the Alert entity.
  - If Telegram message dispatch fails, the alert fires internally but the user never receives the notification — no retry or delivery confirmation mechanism is defined (R-011).
  - Alert accuracy is a tracked success metric (>95% target); incorrect alert firing or missed alerts are measurable failures. Measurement mechanism: system must log each alert evaluation event (metric entry evaluated, condition result, dispatch outcome) to enable accuracy calculation.

---

### Flow 6: Account Deletion

- **Trigger:** A registered user explicitly requests deletion of their account and data.
- **Actor:** End User
- **Input:** Account deletion command.
- **System Processing:**
  1. System confirms intent with the user (confirmation step — **[Assumption SD-004]**).
  2. System permanently deletes all data associated with the InternalUser: all Entries (cascade from Metrics), all Metrics, all Alerts, any pending ParseAttempts.
  3. System deletes the InternalUser record.
  4. System dispatches a confirmation of deletion to the user.
- **Output:** All user data deleted. User effectively becomes unregistered — any future message would trigger onboarding again.
- **Risk Points:**
  - Deletion is irreversible. No export exists (R-006, D-010). Once deleted, data cannot be recovered.
  - If the confirmation step is absent and a user accidentally triggers deletion, total data loss occurs with no recourse.
  - The system cannot prevent or undo Telegram-side identity changes — if a user's Telegram account is lost/deleted before account deletion is requested, their bot data persists under the 1-year retention guarantee with no user-accessible recovery path.

---

### Flow 7: Standalone Metric Creation

- **Trigger:** A registered user sends an explicit metric creation command, OR the system needs to create a new Metric implicitly during a data entry flow (Flow 2, Step 2).
- **Actor:** End User
- **Input:** Metric creation command with metric name; or metric name extracted from a data entry that references a non-existent metric.
- **System Processing:**
  1. System extracts the proposed metric name from the command or from the triggering entry.
  2. System checks whether a Metric with this name already exists for this user (case-sensitive match at this stage — deduplication deferred to system design per R-003).
  3. If a Metric with the same name already exists: system notifies the user and offers to view or use the existing metric. Flow terminates without creating a duplicate.
  4. If no matching Metric exists: system requests the periodicity from the user (required — D-014).
  5. User provides periodicity within the timeout window.
  6. System creates the Metric record with name, periodicity, `created_at`, and `status = inactive` (no entries exist yet).
  7. System confirms creation to the user.
  8. If this flow was triggered implicitly from a data entry (Flow 2, Step 2), control returns to Flow 2, Step 3 to complete the entry storage.
- **Output:** New Metric created and confirmed. If triggered from Flow 2, entry storage proceeds.
- **Risk Points:**
  - If the user does not respond to the periodicity request within the timeout window, or explicitly cancels, the Metric transitions to the "Abandoned" state. If triggered implicitly from a data entry, the pending entry is also discarded (R-012).
  - Case-insensitive or typo-variant metric names are not detected as duplicates at this stage (R-003).
  - No periodicity validation beyond user-provided string — the system accepts the user's input as authoritative.

---

### Flow 8: Metric Listing & Management

- **Trigger:** A registered user sends a list-metrics or manage-metrics command.
- **Actor:** End User
- **Input:** Metric listing command.
- **System Processing:**
  1. System retrieves all Metrics owned by the InternalUser, including Metrics in Active and Inactive states.
  2. For each Metric, system computes or retrieves the MetricActivityStatus to provide current active/inactive status.
  3. System dispatches a structured list of the user's metrics, including name, periodicity, and current status (active / inactive).
- **Output:** Metric list delivered to user.
- **Risk Points:**
  - If the user has many metrics with similar names (R-003), the list may be confusing and is a precursor surface for a future deduplication/aliasing capability — explicitly flagged as a future concern in §3 but not yet modeled as a flow.
  - This flow does not include deletion of metrics — metric deletion is a destructive operation requiring explicit confirmation and is addressed as part of account deletion (Flow 6) or a future metric deletion sub-flow not yet defined in the business document.

---

### Flow 9: Alert Configuration

- **Trigger:** A registered user sends an alert creation command targeting a specific metric.
- **Actor:** End User
- **Input:** Alert creation command specifying metric name, condition type (above / below), threshold value, and optionally a target value dimension for multi-value metrics.
- **System Processing:**
  1. System identifies the target Metric for this user by name.
  2. If Metric is not found: system dispatches an error message to the user; flow terminates.
  3. System validates the alert parameters (condition type must be recognized; threshold must be a numeric value).
  4. If the target Metric is associated with multi-value entries: system requests or confirms the `target_value_dimension` from the user (e.g., which dimension — weight, reps — this alert monitors).
  5. System creates an Alert record with condition type, threshold value, target_value_dimension (if applicable), `status = monitoring`, and timestamps.
  6. System confirms alert creation to the user.
- **Output:** Alert created in Monitoring state; confirmation sent to user.
- **Risk Points:**
  - An alert created on a metric with no future entries will remain in Monitoring indefinitely — this is valid behavior, not a lifecycle gap.
  - Threshold value type compatibility with the metric's actual data values is not enforced at creation time — mismatch may only surface at evaluation time (Flow 5).
  - Multi-value dimension selection may be ambiguous to the user if dimensions are not explicitly named during entry.

---

### Flow 10: Alert Management

- **Trigger:** A registered user sends a command to pause, re-activate, or delete an existing alert.
- **Actor:** End User
- **Input:** Alert management command (pause / re-activate / delete) referencing an alert or metric identifier.
- **System Processing:**
  1. System identifies the target Alert for this user.
  2. If Alert is not found: system dispatches an error message; flow terminates.
  3. **Pause:** System sets Alert status to Paused; dispatches confirmation to user.
  4. **Re-activate:** System sets Alert status to Monitoring; dispatches confirmation to user.
  5. **Delete:** System confirms intent with user (destructive operation — confirmation step assumed per SD-004 rationale). On confirmation, system permanently deletes the Alert record and dispatches a deletion confirmation to the user.
- **Output:** Alert status updated or deleted; confirmation sent.
- **Risk Points:**
  - Entries that would have satisfied the alert condition during the Paused period are not retroactively evaluated when the alert is re-activated.
  - Alert deletion is irreversible — no historical record of past alert firings is retained after deletion.

---

## 6. State Model

### InternalUser States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Unregistered** | Default state — user has not interacted with the bot | User sends first message to the bot | Registered — Active | If Telegram platform ID changes for the same physical user (e.g., account recovery), a new InternalUser is created — history fragmentation |
| **Registered — Active** | First message received; onboarding complete; InternalUser record created. Also re-entered when any metric transitions to Active after a period of inactivity. | All of the user's metrics fall below the active threshold (none have ≥4 entries in the last 5 periods of their own periodicity) OR user requests account deletion | Registered — Inactive, Deleted | — |
| **Registered — Inactive** | All of the user's metrics are inactive (every metric has fewer than 4 entries in its last 5 periods, or the user has no metrics at all). This directly maps to the business definition of a non-active user. | Any of the user's metrics transitions back to the active threshold (≥4/5 periods filled), or user logs a new entry that re-qualifies a metric | Registered — Active | User data must be retained for 1 year after `last_interaction_timestamp` even in this state. The exact computation window per user must align with the per-metric periodicity definition. |
| **Deleted** | User explicitly requests account deletion and confirms | N/A — terminal state | (none) | Irreversible; no data recovery path. Any future contact from the same Telegram identity restarts onboarding as a brand-new user. |

---

### Metric States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Pending Periodicity** | Metric name referenced in an entry (implicit creation) or user explicitly creates a metric; system has issued a periodicity request and is waiting for user response | User provides periodicity within the timeout window OR timeout is reached / user cancels | Active, Abandoned | If abandoned, the triggering entry (if any) is also discarded — potential data loss (R-012) |
| **Active** | Metric exists with defined periodicity and has ≥4 entries in the last 5 periods of its own periodicity | Metric falls below the active threshold (fewer than 4 entries in the last 5 periods) OR user explicitly deletes the metric | Inactive, Deleted | — |
| **Inactive** | Metric exists but has fewer than 4 entries in the last 5 periods of its own periodicity (including newly created metrics with no entries yet) | User logs a new entry that brings the count back to ≥4/5 periods | Active | Inactive metrics still count toward data retention obligations. A newly created metric with no entries begins in this state. |
| **Abandoned** | User did not respond to the periodicity request within the timeout window, or explicitly cancelled during Pending Periodicity. | N/A — terminal state | (none) | Partial metric record is cleaned up on abandonment. The metric name becomes available again for re-creation. Any pending data entry that triggered implicit creation is also discarded. The abandonment path must notify the user (aligned with D-012 principle). |
| **Deleted** | User explicitly deletes a metric (confirmed destructive action) | N/A — terminal state | (none) | All historical Entries for this metric are cascade-deleted. All Alerts on this metric are cascade-deleted. This is irreversible and the deletion must be confirmed by the user before execution. |

---

### Entry States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Received** | Inbound message arrives and is attributed to a registered user | Parse attempt begins immediately | Parsing | — |
| **Parsing** | System is processing the raw input text | Parse succeeds with confidence OR parse confidence is insufficient | Stored (auto), Awaiting Selection | Transient state — should not persist beyond a single processing cycle |
| **Awaiting Selection** | Parse was inconclusive; manual selection prompt dispatched to user; ParseAttempt created | User selects a metric OR ParseAttempt expires / user cancels | Stored (manual), Discarded | State persists until user responds or ParseAttempt expires — conversation-state management required (R-010) |
| **Stored** | Entry successfully written with metric association and value(s) — either auto-parsed or user-selected | N/A under normal lifecycle. Can be cascade-deleted if the parent Metric is explicitly deleted by the user. | Cascade-Deleted | From a user perspective, entries are immutable: they cannot be individually modified or selectively deleted. Cascade deletion via Metric is the only removal mechanism. |
| **Cascade-Deleted** | The parent Metric was explicitly deleted by the user; all associated Entries are removed as part of the Metric deletion flow | N/A — terminal state | (none) | Cascade deletion is irreversible. This is consistent with the immutability principle: individual entries are never directly deleted or modified by users; only the parent Metric deletion removes them. |
| **Discarded** | User abandoned the manual selection flow, ParseAttempt expired, or user explicitly cancelled. Also applies when implicit metric creation during entry is abandoned. | N/A — terminal state | (none) | Raw input is not silently discarded — user must be notified that the pending input was not stored (D-012). Input is not recoverable after discard. |

---

### Alert States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Monitoring** | Alert created with valid condition and threshold (Flow 9). Alert immediately enters Monitoring upon creation — no intermediate Configured state exists, as there is no distinct behavior between creation and first evaluation. | Alert condition satisfied by a new Entry OR user pauses/deletes the alert | Triggered, Paused, Deleted | An alert on a metric with no future entries will remain in Monitoring indefinitely — this is valid behavior, not a lifecycle gap. |
| **Triggered** | Alert condition was satisfied by a new Entry; notification dispatched to user via Telegram | Alert automatically returns to Monitoring after notification dispatch (Assumption 5 — persistent repeating alert behavior) | Monitoring | Alert delivery is not guaranteed — Telegram dispatch failure is a silent risk (R-011). High-frequency entries on a volatile metric may generate excessive alert notifications — no rate-limiting is defined. |
| **Paused** | User explicitly paused the alert (Flow 10) | User re-activates the alert (Flow 10) | Monitoring | Entries received during the Paused period are not retroactively evaluated when the alert is re-activated. |
| **Deleted** | User explicitly deleted the alert (Flow 10, confirmed destructive action) | N/A — terminal state | (none) | — |

---

### ParseAttempt States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| **Awaiting Selection** | System has determined parse confidence is insufficient; ParseAttempt record created with `expiry_timestamp`; selection prompt dispatched to user | User responds with a valid metric selection OR `expiry_timestamp` is reached OR user explicitly cancels | Resolved, Expired | System must hold conversation state between prompt dispatch and user response. A new inbound message from the user during this state creates a conflict (R-010). Only one active ParseAttempt per user at a time is assumed — concurrent ParseAttempts are not modeled. |
| **Resolved** | User selected a valid target Metric from the prompt; Entry has been created and stored (Stored state in Entry lifecycle) | N/A — terminal state | (none) | ParseAttempt record is discarded upon resolution. |
| **Expired** | `expiry_timestamp` was reached with no user response, or user explicitly cancelled | N/A — terminal state | (none) | System must dispatch an acknowledgement message to the user on expiry, confirming that the pending input was not stored (D-012 principle). Raw input is not recoverable. |

---

## 7. External Dependencies

### External System Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Platform (including Bot API) | Primary input/output channel — all user interactions occur via Telegram; provides opaque user identity context; programmatic interface through which the system sends and receives messages, dispatches images, and presents selection prompts | Hard dependency — system is entirely non-functional without it; all user I/O passes through this single channel | High (R-004) |

> **Note:** The Telegram Platform and its Bot API are consolidated into a single dependency entry. The Bot API is the programmatic interface to the Telegram Platform — they represent one external system with two access aspects, not two independent systems.

---

### Required System Component Dependencies

These are system-internal components that the system must possess or rely upon to fulfill in-scope capabilities. Technology selection for each is deferred to architecture design. They are declared here to ensure their failure modes and risk profiles are captured at context level.

| System Component | Required For | Risk if Absent or Failed |
|---|---|---|
| **Data Persistence Layer** | Storage of InternalUser, Metric, Entry, Alert, and ParseAttempt records across all flows and across sessions | If absent or failed: all data is lost on restart; user isolation (R-005) has no enforcement point; data retention obligations (D-013) cannot be met. Risk level: **Critical** (R-013). |
| **Text Parsing / NLP Engine** | Free-text metric extraction in Flow 2 (automatic parse) and Flow 3 (ambiguity detection); drives the >85% data input success rate target | If degraded: parse failure rate rises; users encounter more disambiguation prompts; data capture quality falls below the >85% success target (R-002). Risk level: **Medium** (R-014). |
| **Chart Rendering Component** | Generation of chart images from metric time-series data in Flow 4 | If absent or failed: chart feature is unavailable; the >25% chart adoption success metric cannot be met; users lose the primary data visualization capability. Risk level: **Medium** (R-016). |

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

3. **When a user submits a free-text entry that references a metric that does not yet exist, the system initiates the Metric Creation sub-flow (Flow 7) requesting the periodicity before storing the entry. The pending entry is held until the metric is created or the sub-flow is abandoned.**
   - *Why it exists:* Periodicity is mandatory at metric creation (D-014), and it cannot be inferred. The business document does not explicitly describe the cross-flow between implicit metric creation and entry submission.
   - *Risk if false:* If periodicity is not collected at creation time, the system cannot compute active-user status for that metric, breaking the success metric measurement.
   - *Validation idea:* Confirm with stakeholder whether implicit metric creation (via entry) follows the same creation sub-flow as explicit metric creation (Flow 7).

4. **A ParseAttempt expires and is discarded if the user does not respond within a defined timeout window. The expiry timestamp is set at ParseAttempt creation. On expiry, the system dispatches a notification to the user.**
   - *Why it exists:* The business document (D-012) states that input is not silently discarded, but does not define what happens if the user never responds to the selection prompt. The system cannot hold state indefinitely.
   - *Risk if false:* If no expiry exists, stale ParseAttempts accumulate and may interfere with subsequent valid entries (R-009).
   - *Validation idea:* Define and confirm the expiry timeout duration with stakeholder during system design.

5. **After an Alert fires and the notification is dispatched, the Alert automatically returns to the Monitoring state and will fire again on the next qualifying entry (persistent repeating behavior, not one-shot).**
   - *Why it exists:* The business document does not describe alert lifecycle beyond firing. A one-shot alert vs. a repeating alert represents a meaningful design choice.
   - *Risk if false:* If alerts are one-shot (deleted after firing), users must reconfigure them after each trigger — poor user experience inconsistent with low-friction design intent.
   - *Validation idea:* Confirm expected alert lifecycle (one-shot vs. persistent repeating) with stakeholder.

6. **Chart requests reference a single metric or a small, bounded number of metrics per request.**
   - *Why it exists:* The business document does not specify the scope of chart requests. Unbounded multi-metric chart requests introduce chart rendering and command parsing complexity.
   - *Risk if false:* If users expect unlimited multi-metric overlay charts, the chart generation and command parsing logic is significantly more complex than anticipated.
   - *Validation idea:* Confirm expected chart scope (single vs. multi-metric; any overlay capability) with stakeholder during system design.

7. **Only one active ParseAttempt may exist per user at any given time.**
   - *Why it exists:* Concurrent ParseAttempts for the same user would create unresolvable conversation-state conflicts — the system would be unable to determine which selection prompt a user response is intended for.
   - *Risk if false:* If concurrent ParseAttempts are permitted, conversation-state management becomes exponentially more complex.
   - *Validation idea:* Confirm the single-active-ParseAttempt rule during system design, and define system behavior when a new ambiguous message arrives while a ParseAttempt is already active.

---

## 9. Risks

| Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|
| R-001 (inherited) | Business | High — product solves the wrong problem | Low–Medium | Accepted as premise. Monitor tracking retention against >40% target as the earliest signal. |
| R-002 (inherited) | Behavioral / System | High — corrupted user history | High | Manual selection fallback is the confirmed mitigation (D-012). Parse ambiguity surface area must be precisely defined during system design. NLP engine accuracy must be tracked against the >85% data input success rate target. |
| R-003 (inherited) | Behavioral | Medium — fragmented metric history | High | Deduplication / aliasing mechanism must be addressed in system design before launch. |
| R-004 (inherited) | System | High — full service disruption | Low–Medium | Accepted dependency. No mitigation in scope. |
| R-005 (inherited) | System / Business | Critical — user trust destruction | Low | Strict user isolation: all data queries must be scoped to a verified InternalUser ID. The Data Persistence Layer is the enforcement point for this isolation. Must be tested explicitly. Success metric: 100% isolation integrity. |
| R-006 (inherited) | Business | Medium — data unrecoverable on account/Telegram loss | Medium | Accepted. Users informed at onboarding. 1-year retention provides a partial recovery window. |
| R-007 (inherited) | Business / Factual | Low (mitigated by design) | Low | No personal data stored. Residual risk is Telegram-side and outside this system's boundary. |
| R-008 (inherited) | Business | Medium — operational gaps on single owner unavailability | Medium | Accepted. AI-agent assistance reduces burden. |
| R-009 (system) | System | Medium — orphaned ParseAttempts degrade conversation state | Medium | Expiry behaviour defined: `expiry_timestamp` attribute on ParseAttempt; expiry triggers notification to user. Covered in Assumption 4. |
| R-010 (system) | Behavioral | Medium — user sends new message before completing selection prompt; conversation state corrupted | Medium | System design must define conversation-state management and conflict resolution for concurrent interaction flows. Assumption 7 constrains to one active ParseAttempt per user. |
| R-011 (system) | System | Low–Medium — alert notification dispatch fails silently | Low–Medium | System design should define retry or dead-letter behaviour for failed alert dispatches to meet the >95% alert accuracy target. Alert evaluation events must be logged to enable accuracy measurement. |
| R-012 (system) | Behavioral | Low–Medium — implicit metric creation during entry flow creates an unresolved entry if user abandons periodicity sub-flow | Medium | System design must define atomicity of the combined entry + metric creation flow. If sub-flow is abandoned, pending entry is explicitly discarded and user is notified. See Assumption 3. |
| R-013 (system) | System | Critical — data loss, isolation failure | Low (if designed carefully) | The Data Persistence Layer must be declared as a system dependency at architecture stage. Data durability, backup, and isolation enforcement mechanisms must be explicitly designed. |
| R-014 (system) | System | Medium — parse accuracy falls below >85% target | Medium | NLP / Text Parsing Engine accuracy must be monitored against the success metric. Degradation must trigger a review of parsing rules or training data. |
| R-015 (system) | System | Medium — referential inconsistency between Entry/Alert and owning InternalUser | Low | The `internal_user_id` on Entry and Alert must always match the `internal_user_id` of the owning Metric. This constraint must be enforced in the Data Persistence Layer and tested explicitly. |
| R-016 (system) | System | Medium — chart delivery fails if Chart Rendering Component is unavailable | Low–Medium | Chart Rendering Component must be declared as a system dependency at architecture stage. Failure modes (rendering timeout, format incompatibility) must be defined. |

---

## 10. Logical Consistency Check

**Are there gaps in lifecycle?**

- **ParseAttempt lifecycle is now fully modeled** with three explicit states: Awaiting Selection → Resolved / Expired. Expiry includes a notification dispatch to the user. Gap from v0.5 is closed.
- **Metric "Abandoned" state is now defined** with entry condition, cleanup behavior, and user notification. Gap from v0.5 is closed.
- **Entry cascade deletion is now modeled** via the "Cascade-Deleted" state. The immutability claim is scoped correctly: entries are immutable from a user perspective (no individual modification or deletion) but can be removed via cascade on Metric deletion. Contradiction from v0.5 is resolved.
- **InternalUser Active/Inactive boundary is now quantitatively defined**: Inactive = all metrics have fewer than 4 entries in their last 5 periods (or user has no metrics). This directly maps to the business active-user definition. Gap from v0.5 is closed.
- **Remaining open gap:** The metric deletion sub-flow (individual metric deletion without full account deletion) is not yet explicitly modeled as a separate flow. It is referenced in the Metric "Deleted" state and in §3 (Inside the System) but Metric Listing & Management (Flow 8) does not yet model deletion. This is flagged as SU-006 and should be addressed if the business document is updated to explicitly describe individual metric deletion behavior.

**Are any actors undefined?**

- No undefined actors. All four actors (End User, Bot Owner / Operator, Operational Owner, Telegram Platform) are modeled. The Operational Owner's interactions are primarily out-of-band (system monitoring, incident response) and do not generate in-system flows — this is appropriate given the scope.

**Are there ambiguous states?**

- The Alert "Configured" state (v0.5) has been removed. Alert now enters "Monitoring" directly upon creation. The previous perpetual non-terminal ambiguity (an alert with no future entries stuck in "Configured") is resolved — Monitoring is a valid persistent state for alerts awaiting activity.
- The `Metric.status` vs. MetricActivityStatus ambiguity is resolved: MetricActivityStatus is the computation rule; `status` is the denormalized cached result. The risk of stale `status` is flagged in the entity description and must be addressed during system design (triggered update on every Entry creation or periodicity boundary crossing).
- Assumption 7 (one active ParseAttempt per user) removes the ambiguity of concurrent ParseAttempts competing for user response.

**Are there circular flows?**

- No circular flows detected. The Entry lifecycle is strictly linear (Received → Parsing → Stored / Discarded / Cascade-Deleted). The Alert lifecycle returns to Monitoring after firing — this is a legitimate cycle by design, not a problematic circular dependency. The manual selection flow (Flow 3) is a branching path of Flow 2, not a loop — it terminates in either a Stored or Expired/Discarded entry.

---

## Version

v0.6

## Based On

Business Analysis v0.5

## Changes Introduced

- **Version corrected throughout**: body, header, footer, and governance block now consistently reference v0.6 (resolves critical version mismatch from v0.5 file where body declared v0.1).
- **Four missing interaction flows added:** Flow 7 (Standalone Metric Creation), Flow 8 (Metric Listing & Management), Flow 9 (Alert Configuration), Flow 10 (Alert Management).
- **Metric creation sub-flow in Flow 2 now explicitly references Flow 7** as the sub-flow, instead of leaving it unmodeled.
- **Metric "Abandoned" state defined** with entry condition, cleanup behavior, and name availability note.
- **ParseAttempt state model added** to §6 with three states: Awaiting Selection, Resolved, Expired.
- **Entry "Cascade-Deleted" state added** to §6; Entry immutability scoped correctly (user-perspective immutability, cascade deletion remains possible).
- **Entry immutability vs. cascade deletion contradiction resolved**: declared that Entries are deleted when their parent Metric is explicitly deleted; immutability principle applies to individual user-level operations only.
- **Metric `status` attribute vs. MetricActivityStatus conflict resolved**: `status` is the stored denormalized cache; MetricActivityStatus is the computation rule; they represent the same concept at different abstraction levels.
- **Alert "Configured" state removed**: Alert now enters "Monitoring" directly upon creation; perpetual non-terminal state risk eliminated.
- **InternalUser Active/Inactive boundary now quantitatively defined**: maps directly to business active-user definition (all metrics below ≥4/5 periods threshold).
- **Telegram Platform and Bot API consolidated** into a single dependency entry in §7.
- **Three required system component dependencies declared** in §7: Data Persistence Layer (Critical), Text Parsing / NLP Engine (Medium), Chart Rendering Component (Medium).
- **ParseAttempt entity updated**: `expiry_timestamp` attribute added.
- **Alert entity updated**: `target_value_dimension` attribute added for multi-value entry support.
- **Flow 3 abandonment path fixed**: expiry and cancellation paths now include an explicit dispatch step notifying the user that their pending input was not stored (D-012 compliance).
- **Boundary clarification added**: identity mapping (in-scope) vs. identity authentication (out-of-scope) explicitly articulated in §3.
- **Referential integrity constraint noted** for `internal_user_id` on Entry and Alert entities; R-015 added.
- **Four new system risks added**: R-013 (storage component failure), R-014 (NLP parsing accuracy), R-015 (referential inconsistency), R-016 (chart rendering failure).
- **New Assumption 7 added**: one active ParseAttempt per user at any given time.
- **Traceability updated**: data input success rate >85% now includes measurement mechanism; alert accuracy measurement mechanism noted.

---

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| SD-001 | ParseAttempt introduced as an inferred transient entity | Business document confirms manual selection fallback (D-012) but does not name the intermediate state. A stateful prompt-response interaction requires a transient record. | v0.5 | Confirmed — state model and `expiry_timestamp` added in v0.6 |
| SD-002 | MetricActivityStatus modelled as a computation rule; `status` on Metric is the stored result | Active-user status is a measurement construct defined in business §5. The computation rule (MetricActivityStatus) drives updates to the stored flag (Metric.`status`). These are not competing constructs. | v0.6 | Resolved — conflict from v0.5 closed |
| SD-003 | Alert lifecycle confirmed as persistent repeating (not one-shot) | One-shot alerts would require user reconfiguration after each trigger, inconsistent with low-friction design intent. | v0.5 | Open — requires stakeholder confirmation (Assumption 5) |
| SD-004 | Account deletion and alert deletion require a confirmation step | Destructive irreversible operation with no recovery path. Absence of confirmation would create a critical user experience risk. Extended to Alert deletion in v0.6. | v0.5 | Open — requires stakeholder confirmation |
| SD-005 | Entry immutability scoped to user-perspective only; cascade deletion via Metric is permitted | Entry "immutable" means users cannot individually modify or delete entries. Cascade deletion when a parent Metric is deleted is the only removal mechanism and does not violate the immutability principle. | v0.6 | Confirmed |
| SD-006 | Alert "Configured" state removed; Alert enters "Monitoring" directly on creation | "Configured" had no distinct behavior from "Monitoring" and introduced a potential perpetual non-terminal state. Merged into "Monitoring" for clarity. | v0.6 | Confirmed |
| SD-007 | One active ParseAttempt per user at any given time | Concurrent ParseAttempts create unresolvable conversation-state conflicts. Single active constraint is the simplest model consistent with Telegram's single-channel interaction model. | v0.6 | Open — requires stakeholder confirmation of expected behavior when a second ambiguous message arrives during an active ParseAttempt |

---

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| SU-001 | System | ParseAttempt expiry timeout duration not defined | Stale ParseAttempts may accumulate if timeout is too long; user experience degraded if too short | Confirm expiry duration with stakeholder during system design |
| SU-002 | Behavioral | Conversation-state conflict when user sends new message during active selection prompt | Entry routing ambiguity; potential mis-assignment of entries | Define conflict resolution rule during system design (Assumption 7 constrains to one active ParseAttempt) |
| SU-003 | System | Alert lifecycle post-trigger (one-shot vs. persistent repeating) not confirmed by stakeholder | Alert state model incomplete until confirmed | Confirm with stakeholder (see SD-003, Assumption 5) |
| SU-004 | Behavioral | Implicit metric creation during entry — periodicity collection sub-flow interaction with pending entry not confirmed | If sub-flow interaction not defined, atomicity guarantee is unclear | Confirm sub-flow design with stakeholder (see Assumption 3, Flow 7) |
| SU-005 | System | Computation trigger for MetricActivityStatus / Metric.`status` update not defined | `status` may become stale if computation is not triggered on every relevant event | Define computation trigger (e.g., on every Entry creation and on periodicity boundary) during system design |
| SU-006 | System | Individual Metric deletion (separate from account deletion) is referenced in the state model but has no dedicated interaction flow | Architects may make inconsistent assumptions about individual metric deletion behavior | Define individual metric deletion flow explicitly; confirm with stakeholder whether it is a supported user action |
| SU-007 | Behavioral | Behavior when a second ambiguous message arrives while a ParseAttempt is already active (per Assumption 7) | Second message may be lost or may disrupt the active ParseAttempt | Define conflict resolution rule during system design |
Repeat taking into account my responses                                                                                                                                                                                                                                                                         
  SD-003 The alert firing would be one-shot. If user ingnored this, then do not account this record, but let user come back later to reconfigure it.                                                                                                                                                                
  SD-004 If user wants to delite their account, let them 3 days period possibility to restore it                                                                                                                                                                                                                    
  SD-007 As SD-003, if ParseAttempt failed, user can categorise by themself or came back later for this parameter     
---

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Reduce tracking abandonment (retention >40%) | MetricActivityStatus (computation rule); Metric.`status` (stored flag); Flow 2 & 3 (entry capture); Flow 7 (metric creation); Metric states; InternalUser Active/Inactive states (quantitatively defined as all-metrics-inactive). Measurement: % of users with ≥1 active metric still logging after 14 days (daily) / 5 periods (per metric periodicity). | R-001 (premise may be wrong); R-002 (parse failures reduce captured entries); R-012 (abandoned metric creation loses first entry) |
| Enable self-insight through history (charts >25%) | Flow 4 (Chart Request); Entry entity (immutable time-series, cascade-deletable via Metric); Chart Rendering Component (§7). Measurement: chart command invocations / active users. | R-006 (no export; chart is the only data visibility path); R-003 (fragmented metrics produce fragmented charts); R-016 (chart rendering failure blocks feature) |
| User data privacy and trust (isolation 100%) | InternalUser entity (opaque ID, no personal data); all flows scoped by internal_user_id; Data Persistence Layer (§7) as enforcement point; R-015 (referential integrity constraint). Measurement: audit log review, explicit test cases for cross-user data access. | R-005 (cross-user data leak); R-007 (Telegram holds identity — residual, out of scope); R-013 (storage failure removes isolation enforcement point) |
| Alert delivery accuracy (>95%) | Flow 5 (Alert Evaluation); Flow 9 (Alert Configuration); Flow 10 (Alert Management); Alert state model (Monitoring / Triggered / Paused / Deleted). Measurement: system must log each alert evaluation event (entry evaluated, condition result, dispatch outcome); ratio of successfully delivered notifications to expected firings. | R-011 (silent dispatch failure); SU-003 (alert lifecycle ambiguity) |
| Data input success rate (>85%) | Flow 2 (auto-parse); Flow 3 (manual selection fallback); Text Parsing / NLP Engine (§7). Measurement: system must log each inbound message attributed as a data entry attempt and its resolution outcome (auto-parsed / user-selected / discarded); ratio of stored entries to total entry attempts. | R-002 (parsing ambiguity); R-014 (NLP engine accuracy degradation) |
| Service continuity | Operational Owner actor; Telegram Platform external dependency; Data Persistence Layer (§7). | R-004 (Telegram API policy change); R-008 (single operator bus factor); R-013 (storage failure) |
| Portfolio demonstration | All entities, flows, and states collectively | R-003 (parameter collisions fragment history, degrading demo quality) |
