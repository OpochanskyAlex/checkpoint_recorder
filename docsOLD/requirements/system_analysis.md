# System Context Document

> **Version:** v0.8
> **Status:** Updated to include `/help` command discoverability requirement
> **Based On:** Business Analysis v0.6

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
| Bot Operator / System Owner | Internal | Maintains system availability; monitors operational health; manages deployment and configuration; enforces data isolation | Single point of failure for all operational responsibilities (R-008). If unavailable, incidents are not resolved. |
| Telegram Platform | External | Delivers messages bidirectionally between users and the bot; provides opaque user identifiers | If Telegram changes API policy, rate limits, or bot capabilities, the entire system is affected (R-004). |
| NLP Parsing Component | Internal | Interprets free-text entries and maps them to named metrics with numeric values | If parsing quality degrades below 85% success rate, core value proposition fails. Silent parse failures corrupt user history (R-002). |
| Alert Evaluation Component | Internal | Evaluates alert conditions against newly stored entries; dispatches notifications when thresholds are crossed | If evaluation is skipped or delayed, alert accuracy target (>95%) is not met (R-011). |
| Chart Rendering Component | Internal | Generates visual time-series charts from stored entry history on user request | If unavailable or producing incorrect output, chart adoption metric (>25%) is directly impacted (R-016). |
| Logging / Observability Component | Internal | Captures parse outcome events, alert evaluation events, chart invocations, and operational health signals required to measure all five success metrics | If absent, all five success metrics are unmeasurable; operational incidents are invisible to the Bot Operator. |
| Data Persistence Layer | Internal | Stores all user data (metrics, entries, alerts, account); enforces user-level data isolation | Critical dependency. Failure means data loss or cross-user data leak (R-005, R-013). |

---

## 3. System Boundaries

### Inside the System

- User registration and account lifecycle management (including account deletion with 3-day grace period)
- Metric creation, configuration, and individual metric deletion (including cascade deletion of associated entries and alerts)
- Free-text message ingestion and NLP parsing
- ParseAttempt lifecycle management (disambiguation prompts, resolution, deferral, and late categorisation)
- Entry storage and immutable history maintenance
- Alert configuration, condition evaluation (one-shot), and notification dispatch
- Alert reconfiguration and re-arming after firing
- Chart generation and delivery to the user via Telegram
- MetricActivityStatus computation using the closed periodicity vocabulary (`daily` | `weekly`)
- Data retention enforcement (1-year guarantee after last interaction; PendingDeletion purge after 3-day grace period)
- Logging and observability event capture (parse outcomes, alert evaluations, chart invocations, operational health signals)
- Deferred ParseAttempt management (retention of raw input; user-initiated late categorisation)
- In-bot command discoverability via a `/help` command that lists all available commands with descriptions

### Outside the System

- Telegram user identity management (names, phone numbers, usernames)
- Telegram message delivery infrastructure
- Telegram Bot API authentication and token issuance
- Any export of user data to external systems
- Multi-language NLP support
- Voice input processing
- External API integrations (fitness wearables, financial platforms)
- ML-based trend inference or predictions

### Boundary Assumptions

1. The Telegram platform reliably delivers messages to and from the bot; message delivery failures are outside the system's control.
2. The system maps Telegram's opaque user identifier to an internal user identifier. It does not store or process any Telegram identity fields (name, username, phone).
3. Telegram's opaque user identifier is stable over the lifetime of a user's account; if a user loses their Telegram account, their bot data becomes inaccessible to them.
4. The system operates as a single Telegram bot instance; bot-level identity management (token issuance, rotation) is handled by the Bot Operator outside the system's logical boundary.
5. The Telegram channel is a single shared channel: both data-entry interactions (including ParseAttempt disambiguation) and alert notifications are delivered over the same bot conversation thread. Alert notifications are NOT suppressed during active ParseAttempt sessions; formatting distinction is the primary mitigation for conversation state collision (see §11, item 5).
6. **[SD-003 Resolved]** The alert lifecycle is **one-shot**: after an alert condition is met, the alert transitions to status = Triggered. The alert will not fire again automatically. If the user ignores the notification, no further notifications are sent. The user may return at any time to reconfigure the alert (reset it to Active via Flow 6a) to enable future firings.
7. The ParseAttempt lifecycle is strictly limited to one active ParseAttempt per user at any given time. If a new ambiguous message arrives during an active ParseAttempt, the user is asked to resolve or defer the existing one first.
8. **[SD-007 Resolved]** A ParseAttempt that expires or is explicitly deferred by the user transitions to status = Deferred — not to a terminal failure state. The user may return at any time to categorise the deferred entry manually or discard it.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships |
|---|---|---|---|
| InternalUser | The system's representation of a registered user, keyed to an opaque Telegram-derived identifier. No personal data fields. | `internal_user_id` (opaque), `registration_timestamp`, `last_interaction_timestamp`, `account_status` (Active \| PendingDeletion \| Deleted), `deletion_scheduled_timestamp` (set when status = PendingDeletion) | Owns Metrics, Entries (via Metric), Alerts, ParseAttempts |
| Metric | A named, user-defined tracking dimension with a fixed periodicity from the closed vocabulary. Created explicitly by the user or auto-created on first entry for an unrecognized name. | `metric_id`, `internal_user_id`, `name` (user-defined), `unit` (optional, user-defined), `periodicity` (closed vocabulary: `daily` \| `weekly`), `dimension_names` (ordered list of named dimensions; populated at creation for multi-value metrics, or inferred from first compound entry), `created_timestamp`, `status` (Active \| Archived \| Deleted) | Belongs to InternalUser; has Entries, Alerts, MetricActivityStatus |
| Entry | An immutable record of a single metric data point. Once stored, the numeric value and dimension assignments cannot be changed. | `entry_id`, `metric_id`, `internal_user_id`, `value` (numeric, for single-value entries), `dimension_assignments` (ordered map of dimension name to numeric value, for compound entries — see §12), `stored_timestamp`, `entry_timestamp` (user-supplied or inferred from message time), `raw_input` (original free-text — see §4 Privacy Note) | Belongs to Metric and InternalUser; triggers Alert evaluation |
| Alert | A threshold rule defined by the user for a specific metric. Fires once (one-shot) when the condition is met; transitions to Triggered. Requires explicit user reconfiguration to fire again. | `alert_id`, `metric_id`, `internal_user_id`, `target_dimension` (dimension name for multi-value metrics; null for single-value metrics), `condition` (above \| below), `threshold_value`, `status` (Active \| Triggered \| Archived \| Deleted), `last_triggered_timestamp` | Belongs to Metric and InternalUser |
| ParseAttempt | An inferred, transient entity tracking an in-progress disambiguation session when the NLP parser cannot confidently identify a metric from a free-text input. | `parse_attempt_id`, `internal_user_id`, `raw_input`, `candidate_metrics` (ranked list of metric_ids and names), `status` (Pending \| Resolved \| Deferred \| Expired), `created_timestamp`, `expiry_timestamp` | Belongs to InternalUser; resolves to an Entry or transitions to Deferred for later user action |
| MetricActivityStatus | An inferred, derived entity representing the computed active/inactive status of a metric for a given user, based on entry frequency relative to the metric's periodicity. | `metric_id`, `internal_user_id`, `status` (Active \| Inactive), `periods_filled` (integer, 0–5), `computation_timestamp` | Belongs to Metric and InternalUser; drives retention success metric |

### §4 Privacy Note — `raw_input` Field

**[Inferred Model Risk — Acknowledged and Accepted]** The `raw_input` attribute on the Entry and ParseAttempt entities stores the verbatim free-text message submitted by the user. While the system stores no identity fields (name, email, username) as confirmed by D-007, users routinely include contextual content in their tracking messages (e.g., *"weight 82, after hospital visit"*, *"mood 2, anxious about therapy"*, *"expenses 200 for medication"*). Such content may constitute personal or special-category data under privacy frameworks, even without an associated identity field — particularly for health-adjacent metrics.

**Scope of D-007:** Decision D-007 ("store only de-personalized internal IDs") was formulated to address identity data (name, phone number, Telegram username). It does not address the content of user messages. The `raw_input` field therefore represents a **residual personal data exposure** beyond the scope of D-007's original intent.

**Justification for retention (portfolio scope):** The `raw_input` field is functionally required for two purposes: (a) ParseAttempt disambiguation — the system must retain the original message to present the correct disambiguation context to the user and to create an Entry from it upon resolution or late categorisation; (b) audit tracing — the original message is the only means of tracing a stored Entry back to its source input. Removing `raw_input` at storage time would break both the disambiguation flow and the audit trail.

**Policy:**

- `raw_input` is retained for the same duration as the associated Entry or ParseAttempt.
- On account deletion (Flow 10, step 5), all `raw_input` fields are included in the permanent data purge.
- On individual metric deletion (Flow 11, step 6), all `raw_input` fields on associated Entries and ParseAttempts are permanently deleted as part of the cascade.
- The system does **not** apply scrubbing or anonymization to `raw_input` at this stage. This is a **known limitation** accepted for portfolio scope.
- Users will be informed at onboarding (Flow 1, step 3) that their message text is stored verbatim.
- This risk is recorded in the risk register as R-017 and in the uncertainty register as SU-008.

**Update to D-007 and R-007:** D-007 remains valid for its original scope (no identity data stored). R-007 (GDPR / data privacy exposure) is updated to reflect that the residual personal data risk now extends to `raw_input` content, not only to identity fields. The risk classification for R-007 is elevated from Low to Medium accordingly (see §10).

---

## 5. Data & Interaction Flows

### Flow 1: User Onboarding (First Contact)

- **Trigger:** User sends any message to the bot for the first time (Telegram user ID not found in InternalUser store).
- **Actor:** End User
- **Input:** Any Telegram message (the first message may simultaneously be a metric data entry).
- **System Processing:**
  1. System receives the message and checks for an existing InternalUser record keyed to the Telegram user ID.
  2. No record found. System creates a new InternalUser record with an opaque internal ID mapped to the Telegram user ID. **This step is atomic and idempotent:** if a concurrent first message from the same user arrives before the record is committed, only one InternalUser record is created (duplicate prevention is a hard requirement).
  3. System dispatches an onboarding message to the user: confirms registration; explains the data retention policy (1-year minimum, lifetime in practice); explains the no-export limitation; explains that message text (`raw_input`) is stored verbatim; explains that alerts are one-shot (user must re-arm after each firing).
  4. **Compound flow — transactional boundary (SD-008 Resolved):** If the first message is also parseable as a data entry, the system attempts Flow 2 (Data Entry) after onboarding completes successfully. Transactional semantics:
     - Onboarding (step 2) is the primary atomic operation. It must succeed before any entry processing begins.
     - If onboarding fails, no entry or ParseAttempt is created. The user is not registered. They must send a new message to retry.
     - If onboarding succeeds but entry creation fails (e.g., NLP parse failure leading to ParseAttempt creation failure), the user is registered and the onboarding message is delivered, but the entry intent is not stored. The user is explicitly notified that their entry could not be processed and must be re-submitted.
     - If onboarding succeeds and a new Metric must be auto-created (metric name unrecognized), the periodicity selection prompt is dispatched before the entry is stored. If the user does not complete periodicity selection, the entry is not stored — the user remains registered and is not in an error state.
  5. System logs the registration event to the Logging / Observability Component.
- **Output:** InternalUser record created; onboarding message delivered; optionally an Entry or ParseAttempt created.
- **Risk Points:**
  - Step 2: Concurrent first messages from the same user could race to create duplicate InternalUser records. Idempotent registration (deduplication at the user ID mapping layer) is a hard requirement.
  - Step 4: Compound flow partial failure. The user is registered but their entry intent is lost. The system must notify the user explicitly to re-submit their entry. Silent loss of intent at first contact is a critical UX failure.
  - Step 3: No confirmation of the onboarding message receipt — the user may not read the retention or privacy notice. This is a known and accepted limitation at portfolio scale.

---

### Flow 2: Data Entry (Standard — Auto-Parsed)

- **Trigger:** Registered user sends a free-text message that the NLP parser identifies as a metric data entry with sufficient confidence.
- **Actor:** End User
- **Input:** Free-text message (e.g., *"weight 82.5"*, *"mood 3"*, *"80kg 5reps"*)
- **System Processing:**
  1. System receives the message and confirms the user is registered (InternalUser.account_status = Active).
  2. NLP parser analyzes the message and identifies the target metric name and numeric value(s) with sufficient confidence. If a multi-value compound entry is detected (e.g., `80kg 5reps`), values are mapped to dimension names using the dimension naming convention in §12.
  3. System checks whether the identified metric name matches an existing Metric for this user.
     - If match found: proceed to step 4.
     - If no match: system auto-creates a new Metric record with the parsed name. A periodicity selection prompt is dispatched to the user (closed vocabulary: `daily` | `weekly`). Entry storage proceeds only after the user confirms periodicity. If the user does not respond to the periodicity prompt, the entry is not stored; the user is in a valid state and may re-submit.
  4. System creates an immutable Entry record: `metric_id`, `value` or `dimension_assignments`, `stored_timestamp`, `entry_timestamp`, `raw_input` (verbatim original message). Entry storage is the primary durable operation. If entry storage fails, the user is notified and asked to re-submit. No confirmation is sent for a failed storage.
  5. System evaluates all Active alerts associated with the metric (post-storage). Alert evaluation failure must NOT roll back the entry — the entry is preserved and the evaluation failure is logged.
  6. System updates MetricActivityStatus for the metric.
  7. System dispatches a confirmation message to the user (e.g., *"Logged: weight 82.5 kg"*). Confirmation dispatch failure does not invalidate the stored entry.
  8. System logs the parse resolution outcome (success, metric name, entry_id) to the Logging / Observability Component.
- **Output:** Entry stored; alerts evaluated; MetricActivityStatus updated; confirmation delivered; parse outcome logged.
- **Risk Points:**
  - Step 2: A confident auto-parse may still be incorrect (user typo, ambiguous phrasing). Entry is immutable — a wrong value permanently pollutes the time series. At 85% parse accuracy, approximately 15 out of 100 entries may be silently incorrect, distorting charts and potentially triggering false alerts over time.
  - Step 3: Metric auto-creation interrupts the entry flow with a periodicity selection prompt. If the user does not complete it, no entry is stored. This is a confirmed design decision (SD-002).
  - Step 5: Alert evaluation is a post-storage operation. Its failure is logged but does not affect entry integrity.
  - Step 5: An alert notification dispatched during an active ParseAttempt session for another entry may cause conversation state confusion. See §11, item 5, for the resolution policy.

---

### Flow 3: Data Entry (Ambiguous — ParseAttempt Created)

- **Trigger:** Registered user sends a free-text message that the NLP parser cannot identify with sufficient confidence as a specific metric.
- **Actor:** End User
- **Input:** Free-text message that is ambiguous (e.g., *"3"*, *"82"* with no metric name, or a metric name with no value)
- **System Processing:**
  1. System receives the message and confirms the user is registered (InternalUser.account_status = Active).
  2. NLP parser identifies the message as ambiguous — cannot determine the target metric with sufficient confidence.
  3. System checks whether the user already has an active ParseAttempt (status = Pending).
     - If yes: **[SD-007 Resolved]** The new ambiguous message is not silently discarded and does not overwrite the existing ParseAttempt. The system notifies the user that a disambiguation is already in progress and asks them to either resolve the existing one first, or explicitly defer it (which transitions it to Deferred). The new ambiguous message is not stored as a ParseAttempt until the existing one is resolved or deferred.
     - If no: proceed to step 4.
  4. System creates a ParseAttempt record: `raw_input`, `candidate_metrics` (ranked list of possible matches), `status = Pending`, `expiry_timestamp` (set to ParseAttempt expiry window — see SU-001).
  5. System dispatches a disambiguation prompt to the user listing candidate metrics (or asking the user to specify the metric name if no candidates exist).
  6. System logs the ParseAttempt creation event (ambiguous input received) to the Logging / Observability Component.
- **Output:** ParseAttempt record created; disambiguation prompt delivered; parse outcome event logged.
- **Risk Points:**
  - Step 3: If the user's new message arrives while an existing ParseAttempt is Pending, the user must act on the existing one before the new entry can be processed. This may feel disruptive in rapid-fire messaging patterns (see R-010 and Assumption 7).
  - Step 5: The disambiguation prompt is delivered over the same Telegram conversation thread as alert notifications. An alert firing during an active ParseAttempt may confuse the user about which message requires a response (see §11, item 5).
  - Expiry: If the ParseAttempt expires without user response, it transitions to Deferred — not to a failure terminal. The `raw_input` is retained. The user may return later to categorise the entry or discard it (see Flow 3b).

---

### Flow 3a: ParseAttempt Resolution (User Responds to Disambiguation)

- **Trigger:** User selects a candidate metric from the disambiguation prompt, or provides a metric name manually.
- **Actor:** End User
- **Input:** User's selection or typed metric name response
- **System Processing:**
  1. System identifies the active ParseAttempt for the user (status = Pending).
  2. User's response is matched to a candidate metric, or the user provides a new metric name.
  3. ParseAttempt transitions to Resolved.
  4. System creates an Entry record using the resolved metric and the values parsed from the original `raw_input`. `entry_timestamp` is set to the original message time (not the resolution time), so that late resolution does not distort chronological history.
  5. Alert evaluation proceeds (as in Flow 2, step 5).
  6. System logs the ParseAttempt resolution outcome (resolved via user selection, metric_id, entry_id) to the Logging / Observability Component.
  7. Confirmation dispatched to user.
- **Output:** ParseAttempt resolved; Entry stored; alerts evaluated; parse outcome logged; confirmation delivered.
- **Risk Points:**
  - Step 2: User may select the wrong candidate. The entry is stored with the user-chosen metric — no further system validation is performed post-selection. Error is the user's responsibility after selection.
  - Step 1: If no active ParseAttempt exists when the user sends a selection (e.g., the ParseAttempt expired and transitioned to Deferred in the interim), the system must inform the user that the disambiguation session has expired and the response cannot be processed as a selection.

---

### Flow 3b: ParseAttempt Deferral and Late Categorisation

- **Trigger:** ParseAttempt expiry timeout reached without user response, OR user explicitly chooses to defer.
- **Actor:** System (expiry) or End User (explicit deferral)
- **Input:** Expiry event or user deferral command
- **System Processing — Deferral:**
  1. ParseAttempt transitions from Pending to Deferred.
  2. System retains the `raw_input` under the Deferred ParseAttempt record. The entry is not discarded and is not a failure. **[SD-007 Resolved]** The user is expected to return later and categorise the entry themselves, or to come back later to reconfigure the relevant metric and then categorise.
  3. System does not send an unsolicited notification to the user at the time of deferral.
  4. System logs the deferral event to the Logging / Observability Component.
- **System Processing — Late Categorisation (user returns):**
  5. User requests a view of their Deferred ParseAttempts.
  6. System presents the list of Deferred ParseAttempts with their retained `raw_input`.
  7. For each, the user may: (a) select a metric to categorise the entry (triggering Entry creation as in Flow 3a, step 4 onward), or (b) discard the ParseAttempt (transitions to Expired).
  8. System logs the late categorisation or discard event.
- **Output:** ParseAttempt status = Deferred; `raw_input` retained; no immediate user notification. On late categorisation: Entry created or ParseAttempt discarded (Expired).
- **Risk Points:**
  - Deferred ParseAttempts accumulate if the user never returns. A cleanup policy (auto-discard after a defined period in Deferred state) is deferred to system design (SU-006).
  - Late categorisation produces an Entry whose `entry_timestamp` reflects the original message time. The system must support `entry_timestamp` separate from `stored_timestamp` to preserve chronological accuracy.
  - If the user's deferred metric is later deleted (Flow 11) before they return to categorise, the associated ParseAttempt transitions to Expired as part of the cascade (see Flow 11, step 6).

---

### Flow 4: Chart Request

- **Trigger:** User sends a chart request command referencing a metric name.
- **Actor:** End User
- **Input:** Chart request message specifying the target metric (and optionally a time range)
- **System Processing:**
  1. System confirms user is registered (InternalUser.account_status = Active).
  2. System identifies the requested Metric for the user (status = Active or Archived).
  3. System checks whether the metric has at least 2 stored Entries in the requested range. If insufficient data exists, the user is notified and chart generation does not proceed.
  4. System retrieves all Entries for the metric within the specified (or default) time range.
  5. Chart Rendering Component generates a visual time-series chart from the entry data.
  6. Chart image is dispatched to the user via Telegram. The system sends a "generating chart..." acknowledgment within 5 seconds of receiving the request (see §8.1).
  7. System logs the chart invocation event (metric_id, user_id, timestamp) to the Logging / Observability Component.
- **Output:** Chart image delivered to user; chart invocation event logged.
- **Risk Points:**
  - Step 5: Chart Rendering Component failure (timeout, rendering error). No text-summary fallback is defined — user receives an error message. Failure is logged. This gap is accepted at portfolio scope (R-016).
  - Step 6: Chart delivery depends on Telegram's ability to accept image files. Large image files may fail dispatch. The system should cap chart image size or warn the user if the range produces a very large chart.

---

### Flow 5: Alert Notification Dispatch

- **Trigger:** Alert evaluation (triggered from Flow 2 step 5, or Flow 3a step 5) determines that an alert threshold condition is met for an Active alert.
- **Actor:** System (Alert Evaluation Component)
- **Input:** Entry that triggered the alert condition; Alert record (status = Active)
- **System Processing:**
  1. Alert Evaluation Component confirms the alert status is Active.
  2. Alert condition is evaluated against the new Entry value for the `target_dimension`. For single-value metrics, `target_dimension` is null and the evaluation applies to the entry's primary value.
  3. Condition met: alert transitions to status = Triggered. **[SD-003 Resolved — one-shot behavior]** The alert will not fire again automatically. If the user ignores this notification, no further notifications are sent. The user must explicitly re-arm the alert (Flow 6a) to receive future notifications.
  4. System dispatches an alert notification message to the user via Telegram. The notification is formatted distinctly from disambiguation selection prompts (see §11, item 5) to prevent conversation state confusion. A single delivery retry is performed if the initial dispatch fails.
  5. System logs the alert evaluation event (entry evaluated, condition result, dispatch outcome, alert_id) to the Logging / Observability Component.
- **Output:** Alert status = Triggered; notification dispatched; alert evaluation event logged.
- **Risk Points:**
  - Step 3: Alert is now in Triggered state — it will not fire again until the user explicitly re-arms it (Flow 6a). Users who expect repeated alerts and do not know they must re-arm will not receive future notifications. This is a confirmed UX design decision (SD-003). The onboarding message must explain this behavior.
  - Step 4: If the notification dispatch fails even after a retry, the alert remains in Triggered state (state cannot be undone). The failure is logged. The user will not receive the notification — a known and accepted gap at portfolio scale.
  - Step 4: If an alert notification fires during an active ParseAttempt disambiguation session for the same user, the formatting distinction between the alert notification and the selection prompt is the primary mitigation (see §11, item 5).

---

### Flow 6: Alert Configuration

- **Trigger:** User sends an alert configuration command for a specific metric.
- **Actor:** End User
- **Input:** Metric name, threshold value, condition (above | below), target dimension (for multi-value metrics)
- **System Processing:**
  1. System confirms user is registered and the target metric exists (status = Active or Archived).
  2. System validates that the threshold value is numeric and the condition is from the accepted set (above | below).
  3. For multi-value metrics: system validates that `target_dimension` is a known dimension for this metric — i.e., the dimension name has appeared in at least one stored Entry. Alerts on undefined dimensions are rejected.
  4. Alert record is created with status = Active.
  5. Confirmation dispatched to user.
- **Output:** Alert record created (status = Active); confirmation delivered.
- **Risk Points:**
  - Step 3: Dimension names must exist in at least one Entry before an alert can reference them. An alert cannot be configured for a dimension that has never been logged.
  - Step 4: User may configure a threshold that is never reachable given their actual metric values. No threshold plausibility validation is performed. The alert will remain Active indefinitely without firing.

---

### Flow 6a: Alert Reconfiguration (Re-arming a Triggered Alert)

- **Trigger:** User instructs the system to re-arm a previously Triggered alert or reconfigure its threshold.
- **Actor:** End User
- **Input:** Alert identifier or metric name reference; optionally new threshold value or condition
- **System Processing:**
  1. System locates the Alert record for the user (status = Triggered or Archived).
  2. If the user provides new threshold or condition values, these are updated on the Alert record.
  3. Alert status is reset to Active.
  4. Confirmation dispatched to user.
- **Output:** Alert status = Active; alert will now evaluate against future entries.
- **Risk Points:**
  - **[SD-003 Resolved — one-shot behavior confirmed]** After every alert firing, the user must explicitly re-arm the alert to receive future notifications. This is the confirmed design. Users who do not know they must re-arm will not receive repeated alerts. The onboarding message must explain this behavior.
  - Re-arming can be performed at any time after the alert has fired — there is no deadline for re-arming.

---

### Flow 7: Metric Creation (Explicit)

- **Trigger:** User explicitly creates a new metric (not via auto-creation during entry).
- **Actor:** End User
- **Input:** Metric name (user-defined), unit (optional), periodicity (from closed vocabulary: `daily` | `weekly`)
- **System Processing:**
  1. System confirms user is registered (InternalUser.account_status = Active).
  2. System checks that no Metric with the same name exists for this user (status = Active or Archived). Near-duplicate detection (e.g., case-insensitive match) is a system design consideration (SU-003); the minimum requirement is exact-name deduplication.
  3. System prompts user to select periodicity from the closed vocabulary (`daily` | `weekly`).
  4. Optionally, for multi-value metrics: system prompts the user to define named dimensions (e.g., *"weight"* and *"reps"*). If no named dimensions are defined at creation, the dimension naming convention in §12 applies on first compound entry.
  5. Metric record is created with status = Active, periodicity set to user's selection, `dimension_names` populated if provided.
  6. Confirmation dispatched to user.
- **Output:** Metric record created; confirmation delivered.
- **Risk Points:**
  - Step 2: Near-duplicate metric names (e.g., `mood` vs. `Mood` vs. `moood`) may not be detected as duplicates under exact-name matching. Users may accumulate fragmented history (R-003).
  - Step 3: If the user does not respond to the periodicity selection prompt, the metric is not created. No default periodicity is assigned.

---

### Flow 8: Metric Listing

- **Trigger:** User requests a list of their metrics.
- **Actor:** End User
- **Input:** Metric list request command
- **System Processing:**
  1. System retrieves all Metrics for the user with status = Active or Archived.
  2. System dispatches a formatted list of metrics (name, unit, periodicity, status, dimension names if multi-value).
- **Output:** Metric list delivered.
- **Risk Points:**
  - This flow is read-only. Individual metric deletion is handled in Flow 11.

---

### Flow 9: Alert Listing and Deletion

- **Trigger:** User requests a list of their alerts, or requests deletion of a specific alert.
- **Actor:** End User
- **Input:** Alert list or delete request command
- **System Processing:**
  1. System retrieves all Alerts for the user (all statuses except Deleted).
  2. System dispatches a formatted list of alerts (metric name, target dimension, condition, threshold, status).
  3. **Alert deletion:** If the user requests deletion of a specific alert, the system dispatches a single-step confirmation prompt. Upon confirmation, the alert record is permanently deleted (status = Deleted). No grace period applies to individual alert deletion — this is scoped and the distinction from account deletion (SD-004) is explicit.
- **Output:** Alert list delivered; optionally alert permanently deleted.
- **Risk Points:**
  - Alert deletion is immediate and irreversible. The user must reconfigure if accidentally deleted.
  - Deletion of an alert that is currently in Triggered state is permitted. The user is not blocked from deleting a Triggered alert.

---

### Flow 10: Account Deletion

- **Trigger:** User requests deletion of their account.
- **Actor:** End User
- **Input:** Account deletion request
- **System Processing:**
  1. System receives the deletion request and confirms the user is registered (InternalUser.account_status = Active).
  2. System sets InternalUser.account_status = PendingDeletion and records `deletion_scheduled_timestamp` (current timestamp + 3 calendar days).
  3. System dispatches a confirmation message to the user: informs them that their account is scheduled for permanent deletion in 3 days; that all data (metrics, entries, alerts, and message text) will be irreversibly deleted; and that they may restore their account within the 3-day window by contacting the bot. **[SD-004 Resolved]**
  4. During the 3-day grace period: InternalUser.account_status remains PendingDeletion. The user may interact with the bot to restore their account (see Flow 10a). No new entries are processed during the PendingDeletion period — the system informs the user that their account is pending deletion and asks if they wish to restore it.
  5. After 3 calendar days: a scheduled process identifies accounts where `deletion_scheduled_timestamp` has passed and status = PendingDeletion. The process performs a permanent, atomic purge of all user data: InternalUser record, all Metrics, all Entries (including `raw_input` fields), all Alerts, all ParseAttempts (including Deferred ones). Purge must be atomic per user — either all data is deleted or none. InternalUser.account_status transitions to Deleted upon successful purge.
  6. System logs the deletion event to the Logging / Observability Component.
- **Output:** Account in PendingDeletion state; after 3-day grace period, all data permanently and irreversibly deleted.
- **Risk Points:**
  - Step 3: The system cannot guarantee the user reads the 3-day notice (Telegram message delivery is unconfirmed at the application layer).
  - Step 5: Permanent deletion is irreversible. The 3-day grace period is the sole recovery mechanism. After deletion completes, no data recovery is possible (consistent with D-013 and the no-export policy, D-010).
  - Step 5: Grace period enforcement depends on a scheduled process. If the scheduled process fails (see §7, Scheduled Process), PendingDeletion accounts are never purged — the deletion commitment is unmet. This is a dependency risk (D-013 obligation).
  - Step 5: Purge atomicity — partial deletion (e.g., InternalUser record deleted but Entries not purged) is a data integrity failure (see §8.3).
  - If a user with a Deleted account sends a new message, the system treats them as a new user and initiates Flow 1 (onboarding).

---

### Flow 10a: Account Restoration (Within Grace Period)

- **Trigger:** User interacts with the bot while InternalUser.account_status = PendingDeletion within the 3-day window.
- **Actor:** End User
- **Input:** Any user message or explicit restore command
- **System Processing:**
  1. System detects InternalUser.account_status = PendingDeletion.
  2. System informs the user that their account is scheduled for deletion and asks if they wish to restore it.
  3. User confirms restoration. InternalUser.account_status is reset to Active; `deletion_scheduled_timestamp` is cleared.
  4. Confirmation dispatched to user: account is fully restored; all data is preserved.
- **Output:** Account restored to Active; all data preserved; scheduled deletion cancelled.
- **Risk Points:**
  - The 3-day window is the only restoration mechanism. Once the purge executes (Flow 10, step 5), restoration is impossible.
  - If the user sends a message during PendingDeletion but does not confirm restoration, the account remains in PendingDeletion and proceeds toward deletion.

---

### Flow 11: Individual Metric Deletion

- **Trigger:** User requests deletion of a specific named metric.
- **Actor:** End User
- **Input:** Metric name (or identifier) deletion request
- **System Processing:**
  1. System confirms user is registered (InternalUser.account_status = Active).
  2. System identifies the Metric by name for the user (status must be Active or Archived). If no matching metric is found, the user is notified.
  3. System dispatches a confirmation prompt to the user specifying: the metric name, the total number of Entries that will be deleted, the number of associated Alerts that will be deleted, and any Deferred ParseAttempts that will be discarded. The prompt makes explicit that this action is **permanent and irreversible** and that no grace period applies.
  4. User confirms deletion. If the user does not confirm within a reasonable timeout, the deletion request is cancelled with no changes made.
  5. System transitions Metric.status = Deleted.
  6. Cascade deletion (atomic batch): all Entries associated with the metric are permanently deleted (including `raw_input` fields); all Alerts associated with the metric are permanently deleted regardless of their current status (Active, Triggered, or Archived); all Deferred or Pending ParseAttempts associated with this metric are transitioned to Expired and their `raw_input` is discarded. The cascade must be treated as an atomic operation — no partial deletion is acceptable.
  7. System dispatches a deletion confirmation to the user (e.g., "Metric 'weight' and all associated data have been permanently deleted.").
  8. System logs the metric deletion event (metric_id, cascade counts) to the Logging / Observability Component.
- **Output:** Metric and all associated data permanently deleted; confirmation delivered; event logged.
- **Risk Points:**
  - Step 3: The confirmation prompt must clearly state what will be deleted. Cascade deletion is irreversible — the user must be fully informed before confirming.
  - Step 4: Timeout cancellation prevents accidental deletion from an unconfirmed prompt. No partial deletion occurs on timeout.
  - Step 6: Cascade atomicity is a hard requirement. A partial cascade (e.g., Entries deleted but Alerts not) leaves the system in an inconsistent state.
  - Step 6: Deleting a metric removes all its associated Alerts, including any Active ones. If the user had an Active alert on the metric, it is permanently deleted without further warning beyond the confirmation in step 3.
  - No grace period applies to individual metric deletion. Unlike account deletion (SD-004), metric deletion is scoped and the user is protected by the explicit confirmation step rather than a time-based grace window.

---

## 6. State Model

### InternalUser State Model

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Active | New InternalUser record created (Flow 1) OR account restored (Flow 10a) | User requests account deletion | PendingDeletion | Normal operating state. All flows available. |
| PendingDeletion | User requests account deletion (Flow 10, step 2) | (a) 3-day grace period expires and scheduled process executes → Deleted; (b) User restores account within 3 days → Active | Active, Deleted | Data exists but no new entries are processed. If the scheduled process fails to execute, account lingers in PendingDeletion indefinitely — deletion commitment is unmet. |
| Deleted | 3-day grace period expires and purge completes (Flow 10, step 5) | None (terminal state) | — | All data purged permanently. If a deleted user sends a new message, the system treats them as a new user (Flow 1). |

---

### Metric State Model

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Active | Metric created explicitly (Flow 7) OR auto-created during entry (Flow 2, step 3) | (a) User archives metric; (b) User deletes metric (Flow 11); (c) Cascade from parent InternalUser deletion (Flow 10) | Archived, Deleted | Normal tracking state. Alert evaluation is active for all Active alerts on this metric. |
| Archived | User archives metric (no new entries expected) | (a) User reactivates metric → Active; (b) User deletes metric (Flow 11); (c) Cascade from parent InternalUser deletion | Active, Deleted | No new entries expected. Existing entries and alerts are preserved. Alert evaluation behavior for Archived metrics is deferred to system design (SU-004). |
| Deleted | User deletes metric (Flow 11) OR cascade from account deletion (Flow 10) | None (terminal state) | — | All associated Entries, Alerts, and ParseAttempts are permanently deleted. Irreversible. |

---

### Entry State Model

Entries are immutable. They do not have a mutable lifecycle state beyond creation and cascade deletion.

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Stored | Entry successfully created (Flow 2 auto-parse, Flow 3a resolution, or Flow 3b late categorisation) | Cascade deletion from parent Metric deletion (Flow 11) or parent InternalUser deletion (Flow 10) | Deleted | Immutable. The `value` and `dimension_assignments` cannot be changed post-storage. `entry_timestamp` reflects the original message time even for late-categorised entries. |
| Deleted | Cascade deletion from Metric deletion (Flow 11) or account deletion (Flow 10) | None (terminal state) | — | Irreversible. `raw_input` purged as part of deletion. |

---

### Alert State Model

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Active | Alert created (Flow 6) OR alert re-armed (Flow 6a) | (a) Alert condition met → Triggered; (b) User archives alert; (c) User deletes alert (Flow 9); (d) Cascade from parent Metric or InternalUser deletion | Triggered, Archived, Deleted | Normal evaluation state. Alert is evaluated against every new Entry for its metric. |
| Triggered | Alert condition met during Entry evaluation (Flow 5) — one-shot behavior (SD-003 Resolved) | (a) User re-arms the alert (Flow 6a) → Active; (b) User archives alert; (c) User deletes alert (Flow 9); (d) Cascade from parent Metric or InternalUser deletion | Active, Archived, Deleted | Terminal for notification purposes only. The alert entity is NOT deleted — it remains in Triggered state until the user acts on it. It will not fire again until explicitly re-armed by the user. If notification dispatch failed, the alert is still Triggered — data integrity is preserved over notification delivery. |
| Archived | User archives alert | (a) User reactivates → Active; (b) User deletes alert; (c) Cascade from parent Metric or InternalUser deletion | Active, Deleted | Preserved for reference. Not evaluated against new entries. Can be reactivated. |
| Deleted | User deletes alert (Flow 9) OR cascade from Metric deletion (Flow 11) or account deletion (Flow 10) | None (terminal state) | — | Irreversible. |

---

### ParseAttempt State Model

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Pending | ParseAttempt created (Flow 3, step 4) — disambiguation prompt sent to user | (a) User responds and selects a metric → Resolved; (b) Expiry timeout reached → Deferred; (c) User explicitly defers → Deferred | Resolved, Deferred | Active disambiguation session. Only one Pending ParseAttempt allowed per user at a time. |
| Resolved | User selects a candidate metric or provides a metric name (Flow 3a) | None — terminal after Entry creation | — | Entry successfully created from the resolved ParseAttempt. `entry_timestamp` is set to original message time. |
| Deferred | Expiry timeout reached (SU-001) OR user explicitly defers (SD-007 Resolved) | (a) User returns and categorises the entry → Entry created → ParseAttempt transitions to Expired; (b) User discards the ParseAttempt → Expired; (c) Cascade from parent InternalUser deletion → Expired; (d) Cascade from parent Metric deletion (if candidate metric was resolved) → Expired | Expired | **[SD-007 Resolved]** `raw_input` is retained. This is a resting state — not a failure terminal. The user may return at any time to categorise the entry or discard it. Deferred ParseAttempts accumulate if the user never returns (SU-006). |
| Expired | User discards the ParseAttempt OR cascade deletion from Metric (Flow 11) or InternalUser (Flow 10) | None (terminal state) | — | `raw_input` is no longer actionable. Purged as part of cascade or user-initiated discard. |

---

## 7. External Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Bot API | Message delivery (inbound and outbound); opaque user identifier provision | Hard — system cannot function without it | Critical |
| Telegram Infrastructure | Delivery of messages, images (charts), and notification messages to end users | Hard — no alternative delivery channel | Critical |

### Required Internal Component Dependencies

| Component | Purpose | Dependency Type | Failure Risk |
|---|---|---|---|
| NLP Parsing Component | Interprets free-text entries; determines metric match and confidence score; maps compound entries to dimension values | Hard — core value proposition | Parse success rate collapses; all entries routed to ParseAttempt flow; 85% success target unachievable |
| Alert Evaluation Component | Evaluates alert conditions post-entry storage; dispatches notifications on threshold crossing | Soft — entry storage proceeds regardless of evaluation outcome | Alert accuracy target (>95%) cannot be met; alerts may silently not fire |
| Chart Rendering Component | Generates time-series chart images from stored entry history | Soft — system operates without it; chart feature unavailable | Chart adoption metric (>25%) unreachable; no fallback defined (R-016) |
| Data Persistence Layer | Stores all system data (users, metrics, entries, alerts, parse attempts); enforces per-user data isolation | Hard — total data loss on failure | Critical; R-013; R-005 (cross-user data leak risk if isolation fails) |
| Logging / Observability Component | Captures parse outcome events (success and failure), alert evaluation events (condition result, dispatch outcome), chart invocation events, and operational health signals. This component is the sole means by which all five success metrics can be computed. | Hard for success metric measurement; Soft for real-time user-facing operation | If absent: all five success metrics are unmeasurable; operational incidents (parse degradation, alert failures, storage errors) are invisible to the Bot Operator until users report them. No proactive monitoring is possible. |
| Scheduled Process (Retention and Deletion Enforcement) | Enforces the 1-year data retention guarantee; executes PendingDeletion account purges after the 3-day grace period; optionally cleans up stale Deferred ParseAttempts beyond the SU-006 cleanup window | Soft — system operates without it in real time, but retention and deletion commitments are unmet | D-013 retention obligation unmet if absent; PendingDeletion accounts never purged (SD-004 grace period breach); SU-006 deferred ParseAttempt accumulation |

---

## 8. Non-Functional Requirements (NFR Baseline)

> **[Inferred Model Section]** These are minimum-viable NFR targets for a portfolio-grade, approximately 10-user system. They are not enterprise SLAs. They establish the floor below which the system's core goals are directly threatened. All targets are explicitly provisional and must be reviewed if user volume exceeds the designed ceiling.

### 8.1 Performance

| Interaction Type | Acceptable Response Latency | Rationale |
|---|---|---|
| Entry acknowledgment (Flow 2 auto-parse) | End-to-end ≤ 5 seconds | Users expect near-real-time feedback. Delays longer than 5 seconds create uncertainty about whether the entry was received, increasing re-submission and duplicate entry risk. |
| Disambiguation prompt delivery (Flow 3) | End-to-end ≤ 5 seconds | Same rationale as entry acknowledgment; user is waiting for a response to their message. |
| Chart request acknowledgment ("generating...") | ≤ 5 seconds from chart request received | Users must receive a prompt acknowledgment before chart generation begins to avoid the appearance of no response. |
| Chart delivery (full image) | ≤ 30 seconds from chart request received | Chart generation is computationally heavier than simple lookups. A 30-second total budget is acceptable for a non-real-time, on-demand feature at this scale. |
| Alert notification dispatch (Flow 5) | ≤ 60 seconds from Entry storage to notification delivery | Alerts are not real-time safety mechanisms. A 60-second evaluation-to-dispatch window is acceptable for personal metric tracking. |
| Metric / alert list delivery (Flows 7, 8, 9) | End-to-end ≤ 5 seconds | Simple data retrieval operations against a small dataset (~100 time series). |

### 8.2 Availability

| Target | Rationale |
|---|---|
| Minimum uptime: ≥ 95% (measured monthly) | For a portfolio project with approximately 10 users, up to 5% downtime (~36 hours per month) is acceptable at portfolio scope. Below 95% availability, users who attempt to log during their regular habit window may not succeed — directly threatening the >40% retention target. |
| Designed user ceiling: ≤ 20 concurrent users | The system is designed for approximately 10 users. Beyond 20 users, an architecture review is required before further expansion. If the bot is made public or shared beyond the intended cohort, the system may degrade without warning beyond this ceiling. This ceiling is explicit and non-negotiable without an architecture review. |

### 8.3 Transactional Atomicity

| Scenario | Atomicity Expectation |
|---|---|
| User registration (Flow 1, step 2) | InternalUser record creation must be atomic and idempotent. Concurrent first messages from the same Telegram user must not produce duplicate InternalUser records. |
| Compound first-contact flow (Flow 1, step 4) | Onboarding (InternalUser creation) is the primary atomic unit. Entry or ParseAttempt creation is secondary. Failure in the secondary operation does not roll back onboarding. The user is notified explicitly if entry processing fails after successful registration. |
| Entry storage + Alert evaluation (Flow 2, steps 4–5) | Entry storage (step 4) and alert evaluation (step 5) are NOT required to be atomic. Entry storage takes precedence. Alert evaluation failure must not roll back the stored entry. |
| Entry storage + Confirmation dispatch (Flow 2, steps 4–7) | Entry storage is the durable operation. Confirmation dispatch failure does not invalidate the stored entry. The user may not receive confirmation, but the entry is preserved. |
| ParseAttempt creation + Disambiguation prompt (Flow 3, steps 4–5) | ParseAttempt creation and disambiguation prompt dispatch should be treated as a unit. If prompt dispatch fails after ParseAttempt creation, the ParseAttempt should be cleaned up (not left as a dangling Pending record with no user prompt), or the system must retry dispatch. A dangling Pending ParseAttempt with no associated user-visible prompt is a consistency failure. |
| Cascade deletion — account (Flow 10, step 5) | Purge must be atomic per user: either all user data is deleted or none. Partial purge is a data integrity failure. |
| Cascade deletion — metric (Flow 11, step 6) | Cascade must be atomic: Entries, Alerts, and ParseAttempts associated with the metric must all be deleted as a unit. Partial cascade is a data integrity failure. |
| PendingDeletion purge (Scheduled Process) | Purge must be atomic per user. If the scheduled process fails mid-purge, it must be resumable or idempotent — it must not leave a user in a partially-deleted state. |

### 8.4 Security NFR Baseline

| Area | Policy |
|---|---|
| Bot access control | **[Assumption — acknowledged gap, R-018]** The bot is currently designed as open to any Telegram user who sends it a message. Any Telegram user can trigger registration (Flow 1) without any prior authorization. For the intended ~10-user cohort, this is an accepted risk. If the operator wishes to restrict access to a known cohort, an allowlist or invitation-based mechanism must be introduced — this is a design decision deferred to the architect with an explicit note that the current design is open and uncontrolled. If the bot is shared publicly or its address becomes known beyond the intended cohort, registration from unintended users cannot be prevented. |
| Telegram Bot API token | The token is a privileged secret enabling full bot impersonation. Its protection — including storage mechanism, environment isolation, and rotation policy — is outside the system's logical boundary but is an operational responsibility of the Bot Operator. Loss or exposure of the token compromises all user interactions. |
| `raw_input` personal data | See §4 Privacy Note and R-017. Users are informed at onboarding that their message text is stored. Purged on account and metric deletion. No scrubbing applied at portfolio scope. |
| Rate limiting | No rate limiting is defined at this stage. At approximately 10 users, the risk of message flooding is low. If the bot is made public or usage increases substantially beyond the designed ceiling, rate limiting must be added before further scaling (R-019). |

---

## 9. Assumptions

1. **Users are already Telegram users.**
   - *Why it exists:* The bot is exclusively Telegram-based. No alternative interface exists.
   - *Risk if false:* Adoption ceiling defined by Telegram penetration. Product fails if users are not on Telegram.
   - *Validation idea:* Confirm target users actively use Telegram before deployment.

2. **Free-text entry is sufficient for capturing user intent without structured commands.**
   - *Why it exists:* Low friction is the core value proposition. Structured commands (e.g., `/log weight 82.5`) were considered and rejected in favor of free-text — consequence: higher NLP complexity and parse failure surface area.
   - *Risk if false:* Parse failures accumulate. Manual selection fallback (D-012) mitigates but does not eliminate. At 85% accuracy, approximately 15% of entries may be incorrect.
   - *Validation idea:* Monitor parse success rate in production. If below 85% threshold, reconsider the input model.

3. **Users will define their own metric names consistently over time.**
   - *Why it exists:* Auto-metric creation and NLP matching depend on consistent naming.
   - *Risk if false:* Duplicate or near-duplicate metrics accumulate (e.g., `mood`, `Mood`, `moood`). History fragmentation (R-003).
   - *Validation idea:* Implement near-duplicate detection; flag or prompt the user to merge candidate duplicates.

4. **The system maps Telegram's opaque user ID to an internal ID. Telegram's user ID is stable for the user's lifetime.**
   - *Why it exists:* Telegram IDs are the only identity anchor available without storing personal data.
   - *Risk if false:* If Telegram ever reuses user IDs, a new user's messages could be associated with a prior user's data — a critical cross-user data risk.
   - *Validation idea:* Accept as platform guarantee; monitor Telegram API changelog for changes to ID stability guarantees.

5. **Alert lifecycle is one-shot (SD-003 Resolved — confirmed stakeholder decision).**
   - *Why it exists:* Stakeholder decision. If a user ignores the alert notification, no repeated notifications are sent. The user may return at any time to reconfigure the alert.
   - *Risk if false:* N/A — this is a confirmed and irreversible stakeholder decision.
   - *Implication:* Users who expect repeated alerts must learn to re-arm them after each firing. Onboarding must explain this behavior explicitly.

6. **Users accept no data export and the 1-year retention guarantee as the data recovery policy (D-010, D-013).**
   - *Why it exists:* Stakeholder decisions D-010 and D-013.
   - *Risk if false:* Users lose data without recourse if Telegram access is lost or the account is deleted.
   - *Validation idea:* Inform users explicitly at onboarding. No validation planned — accepted risk.

7. **One active ParseAttempt per user at a time.**
   - *Why it exists:* System simplification. Managing multiple concurrent ParseAttempts per user adds significant state complexity.
   - *Risk if false:* In real Telegram usage, users frequently send messages in rapid succession. If a second ambiguous message arrives before the first ParseAttempt is resolved, the user is asked to resolve the existing one first — this may be a frequent occurrence rather than an edge case.
   - *Validation idea:* Monitor the frequency of "new message arrives during active ParseAttempt" events in production. If this pattern exceeds 10% of ParseAttempt sessions, reconsider the one-at-a-time constraint.

8. **The periodicity vocabulary is closed: `daily` | `weekly`.**
   - *Why it exists:* MetricActivityStatus computation ("last 5 periods") requires deterministic period boundary definitions. Arbitrary strings cannot be interpreted computationally.
   - *Risk if false:* Users may want periodicities not in the vocabulary (e.g., `monthly`, `fortnightly`). They will be unable to create metrics with those periodicities.
   - *Validation idea:* Monitor user requests for additional periodicities; expand the vocabulary with explicit boundary definitions in a future iteration.
   - *Period boundary definition:*
     - `daily`: A period is a calendar day (00:00–23:59 UTC, or user's inferred timezone if determinable — see SU-007). "Last 5 periods" = last 5 calendar days preceding and including today.
     - `weekly`: A period is a calendar week (Monday 00:00 – Sunday 23:59 UTC). "Last 5 periods" = last 5 complete calendar weeks preceding the current week.

9. **`raw_input` is retained as a known residual personal data risk (SD-005 Accepted).**
   - *Why it exists:* `raw_input` is functionally required for ParseAttempt disambiguation and audit tracing. Removal at storage time would break the disambiguation flow.
   - *Risk if false:* N/A — this is an accepted known risk with a defined policy.
   - *Implication:* Users must be informed at onboarding that their message text is stored verbatim. Account and metric deletion purge `raw_input` fields. No scrubbing is applied at portfolio scope.

10. **Account deletion includes a 3-day grace period (SD-004 Resolved — confirmed stakeholder decision).**
    - *Why it exists:* Stakeholder decision. Users may accidentally request account deletion. The 3-day window provides a restoration opportunity before irreversible purge.
    - *Risk if false:* N/A — confirmed stakeholder decision.
    - *Implication:* A scheduled process must enforce the purge after 3 days. Failure of this process leaves PendingDeletion accounts in limbo — the deletion commitment is unmet.

---

## 10. Risks

| Risk ID | Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|---|
| R-001 | Core friction hypothesis is wrong — abandonment driven by motivation, not friction | Business | High | Low–Medium | Accepted as project premise. Monitor retention metric; if below 40% after 14 days, reconsider hypothesis. |
| R-002 | Free-text parsing ambiguity causes incorrect data storage | Behavioral | High | High | Manual selection fallback (D-012). Cumulative impact: ~15% incorrect entries at 85% parse accuracy. Entry immutability amplifies data pollution over time. |
| R-003 | Parameter name collision and duplicates per user | System | Medium | High | Near-duplicate detection; deduplication or alias mechanism deferred to system design. |
| R-004 | Telegram API policy change restricts bot behavior | Business | High | Low–Medium | Accepted platform dependency. No in-scope mitigation. |
| R-005 | Cross-user data leak due to implementation error | System | Critical | Low | Strict per-user data isolation enforced in Data Persistence Layer. 100% non-negotiable target. |
| R-006 | No data export — total data loss on account deletion | Business | Medium | Medium | Accepted (D-010). Users informed at onboarding. 1-year retention guarantee and 3-day grace period provide partial mitigation. |
| R-007 | GDPR / data privacy exposure | Business | Medium | Low–Medium | Primary mitigation: only opaque internal IDs stored (D-007). Residual: Telegram holds identity fields outside this system. Additional residual: `raw_input` content may constitute personal or special-category data (see §4 Privacy Note). Risk elevated from Low to Medium to reflect `raw_input` scope extension. Users informed at onboarding; `raw_input` purged on deletion. No scrubbing at portfolio scope. |
| R-008 | Single operational owner — bus-factor risk | Business | Medium | Medium | AI agent assistance. Accepted for portfolio scope (D-011). |
| R-009 | NLP parse accuracy below 85% target | System | High | Medium | Monitoring via Logging / Observability Component. If below target, structured input fallback or NLP improvements required. |
| R-010 | ParseAttempt collision: new message arrives during active ParseAttempt | Behavioral | Medium | Medium | SD-007 Resolved: new ambiguous message is held; user asked to resolve or defer existing ParseAttempt first. Frequency of this pattern should be monitored in production. |
| R-011 | Alert notification dispatch failure (Telegram delivery failure) | System | Medium | Low | Single retry at portfolio scale. Alert state remains Triggered regardless of delivery success. Failure logged for operator visibility. |
| R-012 | MetricActivityStatus stale or incorrectly computed | System | Medium | Low–Medium | Computation trigger strategy deferred to system design (SU-005). Logging of computation events for audit trail. |
| R-013 | Data Persistence Layer failure — data loss or unavailability | System | Critical | Low | Critical dependency. Backup and recovery strategy required (deferred to system design). |
| R-014 | ParseAttempt expiry timeout misconfigured (SU-001) | System | Medium | Low | Timeout value must be set explicitly at system design. No automatic default. Starting recommendation: 24 hours (see SU-001). |
| R-015 | Compound flow partial failure on first contact (Onboarding + Entry + Metric) | System | Medium | Medium | Flow 1 defines transactional semantics (§8.3): onboarding is the atomic first step; entry failure after successful onboarding requires explicit user notification and re-submission prompt. |
| R-016 | Chart Rendering Component failure | System | Medium | Low | Failure logged; user receives error message. No text-summary fallback defined — accepted gap at portfolio scope. |
| R-017 | `raw_input` constitutes residual personal data not fully covered by D-007 | Business | Medium | High | Known and accepted residual risk. User informed at onboarding. `raw_input` purged on account and metric deletion. No scrubbing applied at portfolio scope (SD-005). See §4 Privacy Note. |
| R-018 | Uncontrolled bot registration: any Telegram user can register | System | Medium | Low–Medium | Acknowledged gap (§8.4). If user cohort exceeds approximately 10 users or the bot becomes public, an access control mechanism (allowlist, invite codes) must be introduced before further scaling. |
| R-019 | No rate limiting: bot may be flooded with messages | System | Low | Low | At 10-user scale, risk is low. If the bot is made public or usage increases substantially, rate limiting must be implemented before further scaling. |

---

## 11. Logical Consistency Check

1. **Are there gaps in lifecycle?**
   - InternalUser: Active → PendingDeletion → (Active via restoration | Deleted via purge). Complete. A Deleted user sending a new message is treated as a new user (Flow 1). No orphan state.
   - Metric: Active → Archived ↔ Active; Active or Archived → Deleted. Complete. Deleted is terminal.
   - Entry: Stored → Deleted (via cascade from metric or account deletion). Complete. Immutable in Stored state; `entry_timestamp` preserved for late-categorised entries.
   - Alert: Active → Triggered → Active (re-arm via Flow 6a); Active, Triggered, or Archived → Deleted. Complete. Triggered is terminal for notification purposes but not for the entity — the user can re-arm to Active (SD-003). Archived is a valid resting state, not a dead end.
   - ParseAttempt: Pending → Resolved (terminal) | Pending → Deferred → (Expired via discard or cascade). Complete. Deferred is a valid resting state, not a failure terminal (SD-007). Expired is the true terminal state.

2. **Are any actors undefined?**
   - All actors declared in §2 are referenced in at least one flow. The Logging / Observability Component, now declared as an actor in §2, is referenced in every flow's logging step.

3. **Are there ambiguous states?**
   - Alert Triggered: it is NOT terminal for the entity — the user can re-arm to Active. The distinction between "terminal for notification dispatch" and "non-terminal for the entity" is explicitly documented in the Alert State Model.
   - ParseAttempt Deferred: it is a resting state, not a failure terminal. The user retains the ability to categorise or discard. This is confirmed by SD-007.
   - No remaining ambiguous states identified.

4. **Are there circular flows?**
   - Flow 2 → Flow 5 (alert evaluation): not circular; alert evaluation is a downstream, post-storage effect.
   - Alert re-arming (Flow 6a) → Active state: re-arm is an explicit user action, not an automatic loop. No circular dependency.
   - ParseAttempt Deferred → user returns → Entry creation (Flow 3b): linear, no circular dependency.
   - No circular flows identified.

5. **Alert-into-ParseAttempt conversation state collision:**
   - The risk: if an alert fires while a ParseAttempt disambiguation session is active for the same user, both the alert notification and the selection prompt appear in the same Telegram conversation thread. The user may confuse the alert notification for a selectable option in the disambiguation prompt.
   - **Resolution policy:** Alert notifications are NOT suppressed during active ParseAttempt sessions — suppression would risk missing a threshold crossing that may be meaningful to the user. Instead, the system must use structurally distinct message formats for the two message types:
     - Disambiguation selection prompts: numbered list of candidate metric names with a clear header indicating a selection is required (e.g., "Which metric did you mean? Reply with a number:").
     - Alert notifications: a clearly marked notification block (e.g., a bold header "Alert fired:" followed by metric name, condition, and threshold) with no selectable options.
   - The formatting distinction is the primary and sole mitigation. This is a residual UX risk that cannot be fully eliminated in a single-channel Telegram bot architecture. It is acknowledged and accepted at portfolio scope.

---

## 12. Help Command

### Flow 12: Help Request

- **Trigger:** User sends the `/help` command.
- **Actor:** End User
- **Input:** `/help` command (no arguments required)
- **System Processing:**
  1. System receives the `/help` command. No registration check is required — the help response is available to any user including unregistered ones.
  2. System constructs and dispatches a formatted message listing all available bot commands with a brief description of each.
  3. No state changes, no entities created, no observability event emitted.
- **Output:** Formatted command reference delivered to user.
- **Risk Points:**
  - The help text must stay synchronized with the actual set of implemented commands. If commands are added or removed, the help response must be updated accordingly.
  - No personalization: the help response is static and does not reflect the user's current state (e.g., registered vs. unregistered, or which metrics/alerts exist).

---

## 13. Periodicity Vocabulary and Period Boundary Definitions

The system accepts only the following periodicity values at metric creation time. Free-form periodicity strings are not accepted. Any input that does not match the closed vocabulary is rejected, and the user is prompted to select from the valid options.

| Periodicity Value | Period Boundary Definition | "Last 5 Periods" Computation | Active Threshold |
|---|---|---|---|
| `daily` | A calendar day: 00:00–23:59 UTC (or user's inferred timezone if determinable — see SU-007). Each calendar day is one period. | Last 5 calendar days preceding and including today | ≥ 4 calendar days with at least one Entry stored within the period |
| `weekly` | A calendar week: Monday 00:00 – Sunday 23:59 UTC. Each complete calendar week is one period. The current incomplete week is not counted. | Last 5 complete calendar weeks preceding the start of the current week | ≥ 4 calendar weeks with at least one Entry stored within the period |

**Future vocabulary expansion:** If users request periodicities outside this vocabulary (e.g., `monthly`, `fortnightly`), the vocabulary must be expanded with explicit period boundary definitions before those periodicities can be supported. Arbitrary string input is rejected by the system without exception.

---

## 14. Dimension Naming Convention for Multi-Value Entries

When a user submits a compound entry (e.g., `80kg 5reps`), the NLP parser must assign names to each parsed numeric value. The naming convention is as follows, applied in priority order:

1. **Named dimensions defined at metric creation (highest priority):** If the user explicitly defined dimension names when creating the metric (e.g., "I want to track weight and reps"), the parser maps parsed values to those names in the order they were defined at creation time. The Metric record's `dimension_names` attribute stores this ordered list.

2. **Named dimensions inferred from metric's first compound entry (second priority):** If dimension names were not defined at creation but the metric's first stored entry is a compound entry, the system uses the unit tokens embedded in the raw input (e.g., `kg`, `reps`) as the dimension names. If no unit tokens are present, positional labels are assigned (see below).

3. **Positional labels as fallback (lowest priority):** If no named dimensions are available from creation or unit inference, numeric values are assigned positional labels: the first value is assigned `value_1`, the second is `value_2`, and so on.

**Alert configuration constraint:** An Alert may only reference a `target_dimension` name that has appeared in at least one stored Entry for that metric. Alerts on dimension names that have never been logged are rejected at configuration time (Flow 6, step 3).

**Consistency requirement:** The dimension naming assignment for a given metric must be consistent across all Entries for that metric. If a metric has used positional labels from its first entry, all subsequent entries follow the same positional convention. Dimension name changes require metric reconfiguration (deferred to system design).

---

## Version

v0.8

## Based On

Business v0.6

## Changes Introduced (v0.7 → v0.8)

- Updated version header to v0.8; based on Business Analysis v0.6.
- Added in-bot command discoverability to §3 System Boundaries (Inside the System).
- Added §12 Help Command with Flow 12 (Help Request).
- Renumbered former §12 (Periodicity Vocabulary) to §13; former §13 (Dimension Naming Convention) to §14.
- Decision Log: SD-009 added.

## Changes Introduced (v0.6 → v0.7)

- Updated version header to v0.7 and status to final pre-architecture draft.
- Added Logging / Observability Component as a named actor in §2.
- Updated §3 boundary assumptions: SD-003 and SD-007 fully propagated; Boundary Assumption 8 added (SD-007 Deferred state confirmation).
- Updated §4 InternalUser entity: added `deletion_scheduled_timestamp` attribute.
- Updated §4 Metric entity: added `dimension_names` attribute for multi-value metric support.
- Expanded §4 Privacy Note (`raw_input`): added explicit scope justification for D-007 applicability, defined what D-007 covers and does not cover, updated policy to cover metric-level cascade deletion.
- Updated §4 Alert entity: added explicit one-shot language and status vocabulary aligned with SD-003.
- Updated §4 ParseAttempt entity: added Deferred status description aligned with SD-007.
- Updated Flow 1 (Onboarding): fully specified compound flow transactional semantics (§8.3 alignment); added one-shot alert explanation to onboarding message.
- Updated Flow 2 (Data Entry): clarified entry storage atomicity and alert evaluation decoupling.
- Updated Flow 3 (Ambiguous Entry): fully propagated SD-007; specified behavior for new message arriving during active ParseAttempt.
- Updated Flow 3b (ParseAttempt Deferral): renamed to "Deferral and Late Categorisation"; added late categorisation subprocess steps (user returns, categorises or discards); aligned with SD-007.
- Updated Flow 4 (Chart Request): added 2-step acknowledgment (immediate acknowledgment within 5 seconds, chart delivery within 30 seconds); added minimum data check.
- Updated Flow 5 (Alert Notification Dispatch): fully propagated SD-003 one-shot behavior; added single retry policy; added formatting distinction requirement.
- Updated Flow 6a (Alert Reconfiguration): added explicit statement that re-arming is available at any time after firing.
- Updated Flow 7 (Metric Creation): added `dimension_names` definition step.
- Updated Flow 9 (Alert Deletion): clarified that no grace period applies to alert deletion; clarified Triggered alerts can be deleted.
- Updated Flow 10 (Account Deletion): fully propagated SD-004 (3-day grace period); specified behavior during PendingDeletion state; specified purge atomicity requirement.
- Updated Flow 10a (Account Restoration): added clarification that unconfirmed interaction does not cancel deletion.
- Verified Flow 11 (Individual Metric Deletion): confirmed completeness — trigger, confirmation, cascade behavior, user notification, alert handling, and ParseAttempt handling all present.
- Updated §6 InternalUser State Model: PendingDeletion state fully specified with SD-004 semantics.
- Updated §6 ParseAttempt State Model: Deferred state fully specified with SD-007 semantics; Expired clarified as true terminal.
- Updated §6 Alert State Model: Triggered state clarified as terminal for notification only (not for entity); re-arm path explicit.
- Updated §7: Logging / Observability Component dependency fully specified with event types and failure risk.
- Updated §7: Scheduled Process dependency updated to reference SD-004 (3-day purge) and SU-006 (stale Deferred ParseAttempt cleanup).
- Updated §8.1 (Performance): added chart acknowledgment ≤ 5 seconds and chart delivery ≤ 30 seconds distinction; added alert dispatch ≤ 60 seconds target.
- Updated §8.3 (Transactional Atomicity): added compound first-contact flow atomicity; ParseAttempt + prompt atomicity; metric cascade atomicity; scheduled process purge idempotency.
- Updated §8.4 (Security NFR): aligned bot access control wording with R-018.
- Updated §9 Assumptions: added Assumption 10 (SD-004 3-day grace period); updated Assumption 5 (SD-003 narrative); updated Assumption 8 (periodicity period boundary definitions embedded).
- Updated §10 Risk Register: elevated R-007 from Low to Medium to reflect `raw_input` scope extension; confirmed R-017, R-018, R-019.
- Updated §11 Logical Consistency Check: item 5 alert-into-ParseAttempt resolution updated with explicit formatting distinction policy.
- Renamed §12 to "Periodicity Vocabulary and Period Boundary Definitions" (removed dimension naming from §12; moved to §13).
- Added §13 Dimension Naming Convention for Multi-Value Entries (extracted from former §12; expanded with priority ordering and consistency requirement).
- Updated Decision Log: SD-003, SD-004, SD-007 all marked Resolved with full narrative.
- Updated Uncertainty Register: SU-001 candidate starting value (24 hours) recorded.
- Updated Traceability table to reflect Logging / Observability Component and §13 additions.

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-001 | Treat unversioned input as v0.1 | No version was specified | v0.2 | Confirmed |
| D-002 | No architecture proposed | Operating rules prohibit technical proposals | v0.2 | Confirmed |
| D-003 | Escalate GDPR risk to pre-launch blocker | Deferral without conditions insufficient | v0.3 | Superseded by D-008 |
| D-004 | Require stakeholder sign-off for no-data-export risk | Risk acceptance cannot be defaulted | v0.3 | Confirmed |
| D-005 | Add Hypothesis Validation Plan | Core hypothesis unvalidated | v0.3 | Superseded by D-009 |
| D-006 | Project intent confirmed as educational / portfolio | Stakeholder response to U-001 | v0.4 | Confirmed |
| D-007 | Privacy by design: store only de-personalized internal IDs (identity fields only) | Stakeholder response to U-004. Scope: covers identity data (name, phone, username). Does not cover `raw_input` message content. See §4 Privacy Note. | v0.4 | Confirmed — scope clarified in v0.7 |
| D-008 | Downgrade GDPR risk from pre-launch blocker to residual | Resolved by D-007 | v0.4 | Confirmed |
| D-009 | Accept friction hypothesis as project premise | Stakeholder decision | v0.4 | Confirmed |
| D-010 | Accept no-export risk on behalf of users | Stakeholder decision | v0.4 | Confirmed |
| D-011 | Single person with AI agents as operational owner | Stakeholder response to Q-004 | v0.4 | Confirmed |
| D-012 | Parse failure uses manual selection fallback | Stakeholder response to Q-009 | v0.5 | Confirmed |
| D-013 | Data retention: 1 year guaranteed, lifetime in practice | Stakeholder response to Q-010 | v0.5 | Confirmed |
| D-014 | Metric periodicity set at creation time by user from closed vocabulary | Stakeholder response to Q-011 | v0.5 | Confirmed |
| SD-001 | Alerts on multi-value metrics reference a specific named dimension | Threshold-based alerts require a single numeric dimension to evaluate against | v0.5 | Confirmed |
| SD-002 | Metric auto-creation requires periodicity selection before entry is stored | Periodicity is required for MetricActivityStatus computation; no default periodicity is appropriate | v0.5 | Confirmed |
| SD-003 | Alert lifecycle is one-shot: after firing, Alert.status = Triggered; user must explicitly re-arm to receive future notifications | Stakeholder decision: if the user ignores the alert notification, the alert record is not repeated automatically. The user can come back later to reconfigure the alert if they want it to fire again. | v0.6 | **Resolved** |
| SD-004 | Account deletion includes a 3-day grace period (PendingDeletion → Active recovery possible); after 3 days, permanent and irreversible deletion | Stakeholder decision: 3-day restoration window before permanent deletion | v0.6 | **Resolved** |
| SD-005 | `raw_input` is retained as a known residual personal data risk; no scrubbing applied at portfolio scope | Scrubbing adds implementation complexity disproportionate to portfolio scope; `raw_input` is functionally required for disambiguation and audit | v0.6 | Confirmed |
| SD-006 | Periodicity vocabulary is closed: `daily` \| `weekly` | Free-form periodicities cannot be computed for MetricActivityStatus; closed vocabulary required | v0.6 | Confirmed |
| SD-007 | ParseAttempt failure or timeout transitions to Deferred, not Expired; user may return to categorise later or come back later to reconfigure | Stakeholder decision: same policy as SD-003 — user can come back later; the entry is not discarded into an ambiguity terminal. ParseAttempt enters a "deferred" state, not a terminal failure. | v0.6 | **Resolved** |
| SD-008 | Compound first-contact flow atomicity: onboarding is the primary atomic step; entry failure after onboarding does not roll back registration | System design decision derived from Flow 1 transactional analysis | v0.7 | Confirmed |
| SD-009 | `/help` command is available without registration and returns a static formatted command list with no state side-effects | Discoverability must not be gated behind registration; static response avoids state complexity | v0.8 | Confirmed |

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| SU-001 | System | ParseAttempt expiry timeout value — not yet defined. Candidate starting value: 24 hours (user may not check Telegram immediately). | Determines how long a user has to respond to a disambiguation prompt before the ParseAttempt transitions to Deferred. | Set explicit timeout at system design. Start with 24 hours and tune based on production behavior. |
| SU-002 | System | NLP parsing confidence threshold — what constitutes "sufficient confidence" for auto-parse vs. ParseAttempt creation. | If threshold is too low, false auto-parses occur. If too high, too many ParseAttempts are created unnecessarily. | Define confidence scoring model at system design. Start with a conservative threshold and tune based on production parse success rate. |
| SU-003 | System | Metric auto-creation eligibility — when should auto-creation be suppressed. | If a user submits a numeric value for an unrecognized name, auto-creation may produce an unintended metric. | Define auto-creation eligibility rules at system design (e.g., require both a name token and a numeric value to auto-create). |
| SU-004 | System | Archived Metric alert behavior — should alert evaluation be suspended for Archived metrics. | Logically, archiving a metric implies the user is not actively tracking it; firing alerts on archived metrics may be counterproductive. | Confirm with stakeholder or default to: alert evaluation is suspended when Metric.status = Archived. |
| SU-005 | System | MetricActivityStatus computation trigger strategy: event-driven (on every Entry), scheduled (on periodicity boundary), or lazy (compute on read). | Each strategy has different implications for data freshness and system load. | Defer to system design. Lazy computation on read is the lowest-complexity starting point for portfolio scale. |
| SU-006 | System | Deferred ParseAttempt cleanup policy — how long should a ParseAttempt remain in Deferred state before automatic expiry. | Without a cleanup policy, Deferred ParseAttempts accumulate indefinitely if the user never returns to categorise or discard them. | Define cleanup policy at system design. Recommended starting point: 30-day automatic expiry from the Deferred entry timestamp. |
| SU-007 | System | Timezone handling for period boundary computation. | `daily` and `weekly` periods are defined in UTC. Users in timezones significantly offset from UTC may experience period boundaries at unexpected local times, potentially affecting MetricActivityStatus computation. | Use UTC as the system default. Per-user timezone preference is a future enhancement. |
| SU-008 | Business | `raw_input` privacy risk: no formal legal assessment of whether free-text metric tracking content constitutes personal data under GDPR Art. 4(1) or Art. 9 (special-category health data). | If formally classified as personal data or special-category data, the system's privacy-by-design claim is incomplete even with the §4 Privacy Note policy in place. | Accept for portfolio scope. If the system scales to a broader user base, obtain legal review before deployment at that scale. |

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Reduce tracking abandonment (retention >40%) | InternalUser (Active state); Metric (Active state); MetricActivityStatus; Flow 2 (Data Entry); Flow 3 / 3a / 3b (ParseAttempt lifecycle); §12 Periodicity Vocabulary | R-001 (friction hypothesis); R-002 (parse failures); R-009 (NLP accuracy below target); R-014 (ParseAttempt expiry misconfiguration) |
| Enable self-insight through history | Entry (Stored state — immutable); Flow 4 (Chart Request); Alert (Active state); Flow 5 (Alert Notification); §13 Dimension Naming Convention | R-002 (incorrect entries — immutable); R-006 (no export); R-016 (chart rendering failure) |
| User data privacy and trust | InternalUser (opaque ID only); §4 Privacy Note (`raw_input`); D-007 (identity field scope); SD-005 (`raw_input` residual risk accepted); Flow 10 / 10a (Account Deletion / Restoration); Flow 11 (Individual Metric Deletion — cascade purge) | R-005 (cross-user leak — critical); R-007 (identity fields + `raw_input` residual); R-017 (`raw_input` personal data risk) |
| Service continuity | Bot Operator / System Owner actor; Scheduled Process (§7); Logging / Observability Component (§2, §7); §8 NFR Baseline | R-008 (bus factor); R-013 (persistence failure); R-016 (chart failure) |
| Portfolio demonstration (all success metrics at target) | Logging / Observability Component (§2, §7 — required for all 5 metrics); §8 NFR Baseline; §12 Periodicity Vocabulary; §13 Dimension Naming Convention | R-009 (parse accuracy unmeasurable without observability); R-012 (MetricActivityStatus stale); R-018 (bot access control gap may inflate user count) |
