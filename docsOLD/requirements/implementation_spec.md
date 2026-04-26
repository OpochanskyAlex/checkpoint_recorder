# Implementation Specification

> **Version:** v1.0
> **Date:** 2026-04-12
> **Status:** Partially Ready for Development — 2 open items are P0-blocking

---

## 1. Document References

- **Business Version:** v0.5 (`business_analysis.md`)
- **Context Version:** v0.7 (`system_analysis.md`)
- **Architecture Version:** v0.9 (`architecture.md`)
- **Spec Version:** v1.0
- **Date:** 2026-04-12

---

## 2. System Scope Confirmation

The system is a Telegram-native personal metric tracking assistant operating as a single-process, component-structured monolith. It receives free-text messages from registered users, interprets them as metric data entries, stores structured data keyed to opaque user identifiers, and provides users with historical data access through chart rendering and threshold-based alerting.

### Included Capabilities

- User registration (idempotent, Telegram-triggered)
- Free-text metric data entry with NLP parsing
- Manual disambiguation flow for ambiguous entries (ParseAttempt lifecycle)
- Metric creation (explicit and auto-create on first entry), listing, archival/reactivation, and cascade deletion
- Multi-value (compound) entry support via user-defined dimension names
- Threshold alert configuration, one-shot evaluation, and notification dispatch
- Time-series chart generation and delivery
- Account deletion with 3-day grace period and restoration
- Late categorization of Deferred ParseAttempts
- Per-user conversation state management (persisted, process-restart safe)
- Scheduled jobs: retention enforcement, PendingDeletion purge, stale ParseAttempt cleanup, stale PendingPeriodicity cleanup
- Structured observability event capture for all five business success metrics

### Explicit Exclusions

- Telegram user identity management (name, username, phone)
- Data export to external systems
- Multi-language NLP support
- Voice input
- External API integrations (wearables, financial platforms)
- ML-based trend inference or predictions
- User-triggered alert archiving/reactivation (deferred)
- Near-duplicate metric name detection (SU-003, deferred)
- Monetization or commercial analytics

---

## 3. Functional Requirements

---

### FR-1: Idempotent User Registration (Onboarding)

**Description:**
When the system receives a message from a Telegram user whose opaque ID is not present in the InternalUser store, it creates exactly one InternalUser record, mapping the Telegram ID to an opaque internal identifier. Concurrent first messages from the same user must not produce duplicate InternalUser records.

**Trigger:**
Any inbound Telegram message from a user with no existing InternalUser record.

**Input:**
Opaque Telegram user identifier; raw message text.

**Processing Rules:**
1. Perform atomic check-and-create on the InternalUser store keyed to the Telegram user ID. If the record already exists (race condition), use the existing record without modification.
2. Assign a new opaque `internal_user_id`. No personal data (name, username, phone) is stored.
3. Set `account_status = Active`, `registration_timestamp = now()`, `last_interaction_timestamp = now()`.
4. Dispatch onboarding message covering: data retention policy (1-year minimum, lifetime in practice), no-export limitation, verbatim `raw_input` storage, one-shot alert behavior.
5. After onboarding message is dispatched, if the first message is parseable as a data entry, attempt Flow FR-4 (Standard Data Entry). Transactional boundary: onboarding must complete before entry processing begins. If onboarding fails, no entry is created. If onboarding succeeds but entry processing fails, user is registered and explicitly notified to re-submit.

**Output:**
- InternalUser record created (or confirmed existing).
- Onboarding message delivered to user.
- `registration_event` emitted to Observability Collector.
- Optionally, an Entry or ParseAttempt created.

**Edge Cases:**
- Concurrent first messages: idempotent — only one InternalUser record created.
- First message is simultaneously a valid data entry: compound flow, transactional boundary respected.
- First message triggers auto-create of a new Metric: periodicity selection prompt dispatched before entry is stored; if user abandons, user remains registered, no entry created.
- Onboarding fails after partial write: user is not registered; no entry created.

**Acceptance Criteria:**
- AC-FR1-1: Sending two simultaneous first messages from the same user produces exactly one InternalUser record.
- AC-FR1-2: InternalUser record contains no name, username, or phone number fields.
- AC-FR1-3: Onboarding message references data retention policy, no-export limitation, verbatim message storage, and one-shot alerts.
- AC-FR1-4: A `registration_event` is observable in the Observability Collector after successful registration.
- AC-FR1-5: If entry processing fails after successful registration, the user receives an explicit notification to re-submit. No silent loss.

---

### FR-2: Account Status Gate

**Description:**
Before any handler processes an inbound message, the User Session Guard checks the InternalUser account status. Messages from users with `account_status = PendingDeletion` are routed exclusively to the account restoration flow. Messages from users with `account_status = Deleted` receive a "no active account" response with instructions to re-register.

**Trigger:**
Every inbound Telegram message after initial routing by Message Dispatcher.

**Input:**
Opaque Telegram user ID; current InternalUser record.

**Processing Rules:**
1. Retrieve the InternalUser record for the Telegram user ID.
2. If `account_status = Active`: allow normal routing.
3. If `account_status = PendingDeletion`: route to Account Manager restoration prompt only. No other intents processed.
4. If `account_status = Deleted`: return error message. No InternalUser record is reactivated. If user wishes to restart, a new registration (FR-1) is triggered by their next message.

**Output:**
- Routing decision to Message Dispatcher.
- Error message to user if `Deleted`.

**Edge Cases:**
- User with `PendingDeletion` sends a data entry: must not be stored; user informed account is pending deletion.
- User with `Deleted` status sends any message: treated as a new first-contact (re-registration).

**Acceptance Criteria:**
- AC-FR2-1: A user with `account_status = PendingDeletion` cannot store new entries or create metrics; receives restoration prompt.
- AC-FR2-2: A user with `account_status = Deleted` receives a "no active account" message, not a handler error.
- AC-FR2-3: Re-registration of a `Deleted` user creates a new InternalUser record with a new `internal_user_id`.

---

### FR-3: Conversation State Routing

**Description:**
The Message Dispatcher consults the User Session Guard for the current per-user conversation state before applying any intent classification. If the state is non-Idle, the message is routed according to the state-specific policy, overriding standard intent classification.

**Trigger:**
Every inbound message from an Active user.

**Input:**
Inbound message; current conversation state for the user (from Data Repository).

**Processing Rules:**
1. Retrieve current `ConversationState` for the user.
2. If `Idle`: apply standard intent classification and route to the appropriate component.
3. If `PendingDisambiguation`: route to ParseAttempt Manager. Any non-disambiguation message receives: "resolve or defer the active disambiguation before continuing."
4. If `PendingPeriodicity`: route to Entry Processor as periodicity selection. Non-periodicity messages receive: "please select a periodicity to complete your entry first."
5. If `PendingMetricDeletionConfirmation`: route to Metric Manager. Non-confirmation messages cancel the deletion and return user to Idle.
6. If `PendingRestorationConfirmation`: route to Account Manager. Non-confirmation leaves account in PendingDeletion; user is informed.
7. At most one non-Idle state per user at any time. Any attempt to enter a second non-Idle state is rejected.

**Output:**
Routing decision; optionally a blocking message to the user.

**Edge Cases:**
- User is in `PendingPeriodicity` and sends an ambiguous entry: blocked with periodicity prompt reminder; no new ParseAttempt created.
- User is in `PendingDisambiguation` and sends a command: blocked with disambiguation reminder.
- Process restarts mid-state: ConversationState loaded from Data Repository; user remains in their prior state.

**Acceptance Criteria:**
- AC-FR3-1: A user in `PendingDisambiguation` who sends a non-disambiguation message receives a blocking response; no new routing occurs.
- AC-FR3-2: ConversationState survives process restart and is correctly applied on next message.
- AC-FR3-3: Two non-Idle states cannot coexist for the same user at any time.

---

### FR-4: Standard Data Entry (Auto-Parsed)

**Description:**
When the NLP Parsing Engine identifies a metric name and numeric value(s) from a user's free-text message with sufficient confidence, the system creates an immutable Entry record and confirms storage to the user.

**Trigger:**
Registered Active user sends a free-text message; NLP confidence meets the configured threshold.

**Input:**
Free-text message; user's existing metric name vocabulary; NLP confidence threshold (configurable, SU-002).

**Processing Rules:**
1. NLP Parsing Engine processes the message; returns `(metric_name, values, dimension_assignments, confidence_score, outcome)`.
2. If `confidence_score ≥ threshold` and `outcome = auto-parse`:
   a. Look up Metric by `(internal_user_id, metric_name)`.
   b. If found: proceed to step 3.
   c. If not found: auto-create flow — dispatch periodicity selection prompt; set `ConversationState = PendingPeriodicity`. Entry is not stored until periodicity is confirmed. Metric record is not written until periodicity is confirmed.
3. Create Entry record: `metric_id`, `value` or `dimension_assignments`, `stored_timestamp = now()`, `entry_timestamp` (from message time or user-supplied), `raw_input = verbatim message`. Entry storage is atomic and durable. If storage fails, notify user to re-submit; do not send confirmation.
4. After successful storage: trigger Alert Engine evaluation (post-commit event, not transactionally coupled).
5. Emit `parse_outcome_event` (outcome=success, entry_id) to Observability Collector.
6. Dispatch confirmation message to user.

**Output:**
Immutable Entry record stored; confirmation message; `parse_outcome_event` emitted.

**Edge Cases:**
- New metric auto-creation: periodicity prompt dispatched; entry stored only after confirmation.
- User does not respond to periodicity prompt: SU-009 timeout triggers cleanup by Scheduled Process; no metric or entry created.
- Alert evaluation fails after entry storage: entry is preserved; failure logged; no rollback.
- Confirmation dispatch fails: entry is preserved; user may not receive confirmation (known limitation).
- Compound entry (e.g., `80kg 5reps`): `dimension_assignments` populated; `value` null.

**Acceptance Criteria:**
- AC-FR4-1: An entry is created with `raw_input` matching the verbatim message text.
- AC-FR4-2: A new metric is NOT written to Data Repository until periodicity is confirmed by the user.
- AC-FR4-3: Alert evaluation failure does not roll back or block the stored entry.
- AC-FR4-4: A `parse_outcome_event` with outcome=success is emitted for every successfully stored entry.
- AC-FR4-5: Confirmation message is NOT sent if entry storage fails.

---

### FR-5: Ambiguous Entry — ParseAttempt Lifecycle

**Description:**
When the NLP Parsing Engine cannot identify a metric with sufficient confidence, the system creates a ParseAttempt record, presents a ranked disambiguation prompt to the user, and awaits manual metric selection. The system must never silently discard an ambiguous entry.

**Trigger:**
NLP outcome = `ambiguous` or `confidence_score < threshold` for an Active user in Idle state.

**Input:**
Raw message text; ranked candidate metric list from NLP Engine; current user conversation state.

**Processing Rules:**
1. Confirm user is in Idle state and has no existing Pending ParseAttempt.
2. Create ParseAttempt record: `raw_input`, `candidate_metrics` (ranked), `status = Pending`, `expiry_timestamp = now() + SU-001 (default 24h)`.
3. Atomicity compensation (AD-9): if prompt dispatch fails after record creation, delete the ParseAttempt record. If deletion also fails, emit `dangling_parse_attempt_alert` to Observability Collector; operator must manually clear.
4. Dispatch disambiguation prompt listing candidate metrics with selection options.
5. Set `ConversationState = PendingDisambiguation`.
6. Emit `parse_outcome_event` (outcome=ambiguous, parse_attempt_id).

**Resolution Paths:**
- **User selects a metric:** ParseAttempt Manager → Entry Processor (create Entry from raw_input using selected metric); `status = Resolved`; `ConversationState = Idle`.
- **User explicitly defers:** `status = Deferred`; `ConversationState = Idle`. Entry not stored; available for late categorization (FR-15).
- **Expiry (SU-001 elapsed):** Scheduled Process transitions `status = Deferred`; `ConversationState = Idle`. Emit expiry event.

**Output:**
ParseAttempt record; disambiguation prompt; `parse_outcome_event` emitted; ConversationState updated.

**Edge Cases:**
- User in non-Idle state when ambiguous message arrives: blocked; no ParseAttempt created.
- Prompt dispatch fails after record creation: record deleted (atomicity compensation); error returned to user.
- Dangling Pending ParseAttempt (prompt dispatch failure + deletion failure): operator-detectable via `dangling_parse_attempt_alert` within `parse_attempt_dangling_detection_window` (default 30s, configurable).

**Acceptance Criteria:**
- AC-FR5-1: A user never has more than one Pending ParseAttempt at any time.
- AC-FR5-2: A ParseAttempt record is deleted if the disambiguation prompt fails to dispatch.
- AC-FR5-3: A `parse_outcome_event` with outcome=ambiguous is emitted for every ParseAttempt created.
- AC-FR5-4: A deferred ParseAttempt retains `raw_input` and remains available for late categorization.
- AC-FR5-5: ParseAttempt expiry transitions `status = Deferred`, not a terminal error state.

---

### FR-6: Metric Auto-Creation (on first entry for unrecognized name)

**Description:**
When a parsed metric name does not match any existing Metric for the user, the system initiates a two-step metric creation flow: dispatch a periodicity selection prompt, then atomically create the Metric record and the Entry record upon confirmation.

**Trigger:**
FR-4 Step 2c: metric name not found in user's Metric store.

**Input:**
Parsed metric name; user's periodicity selection response.

**Processing Rules:**
1. Dispatch periodicity selection prompt to user offering `daily` or `weekly`.
2. Set `ConversationState = PendingPeriodicity`. Metric record is NOT yet created in Data Repository.
3. Await user's periodicity selection (routed by FR-3).
4. On receipt of valid periodicity selection: atomically create Metric record (`name`, `periodicity`, `unit` if present, `status = Active`, `created_timestamp = now()`) and write Entry record. Both writes are part of the same atomic operation.
5. Set `ConversationState = Idle`.
6. On SU-009 timeout: Scheduled Process clears PendingPeriodicity state. No metric or entry created. Emit `periodicity_prompt_event` with outcome=abandoned.

**Output:**
Metric record and Entry record created atomically; ConversationState set to Idle; confirmation sent.

**Edge Cases:**
- Invalid periodicity input: system re-prompts (not treated as non-periodicity message).
- SU-009 timeout before user responds: state cleared; user remains registered; no data created.
- Metric name already exists by the time user confirms (concurrent session edge case): deduplication at DB layer (unique constraint AD-11) — return existing metric, proceed to Entry creation only.

**Acceptance Criteria:**
- AC-FR6-1: No Metric record appears in Data Repository before periodicity is confirmed.
- AC-FR6-2: Metric + Entry creation is atomic — either both succeed or neither is stored.
- AC-FR6-3: SU-009 timeout emits a `periodicity_prompt_event` with outcome=abandoned and clears PendingPeriodicity state.
- AC-FR6-4: The unique constraint on `(internal_user_id, metric_name)` prevents duplicate metric creation under race conditions.

---

### FR-7: Explicit Metric Creation

**Description:**
A registered Active user may explicitly create a Metric by issuing a create command, providing a name, periodicity, and optionally a unit and dimension names.

**Trigger:**
User issues `/metric_create` command with required parameters.

**Input:**
`name` (string), `periodicity` (`daily`|`weekly`), `unit` (optional string), `dimension_names` (optional ordered list of strings for compound metrics).

**Processing Rules:**
1. Validate `name`: non-empty, ≤100 characters, unique for the user (check `(internal_user_id, metric_name)` uniqueness — enforced at DB layer per AD-11).
2. Validate `periodicity`: must be `daily` or `weekly` (closed vocabulary).
3. Validate `unit` if provided: non-empty string, ≤50 characters.
4. Validate `dimension_names` if provided: non-empty list; each name ≤50 characters; no duplicates within the list.
5. Create Metric record with `status = Active`, `created_timestamp = now()`.
6. Respond with confirmation including the assigned `metric_id` and summary of created metric.

**Output:**
Metric record created; confirmation message.

**Edge Cases:**
- Duplicate metric name for the same user: return error; do not create. Suggest the user list their existing metrics.
- `periodicity` value not in `{daily, weekly}`: return validation error.
- `dimension_names` provided with a single name (degenerate compound): treat as single-value metric; ignore `dimension_names`.

**Acceptance Criteria:**
- AC-FR7-1: A Metric with a duplicate name for the same user is rejected with an error message.
- AC-FR7-2: A Metric with `periodicity` outside `{daily, weekly}` is rejected.
- AC-FR7-3: A successfully created Metric appears in the user's metric list.

---

### FR-8: Metric Listing

**Description:**
A registered Active user may retrieve a list of all their Active and Archived Metrics, including each metric's computed MetricActivityStatus.

**Trigger:**
User issues `/metric_list` command.

**Input:**
User's `internal_user_id`.

**Processing Rules:**
1. Retrieve all Metric records for the user with `status ∈ {Active, Archived}`.
2. For each Metric, compute or retrieve MetricActivityStatus (lazy computed on read — AD-4).
3. MetricActivityStatus computation: count Entry records within the last 5 periods of the metric's `periodicity`; count distinct periods with at least one entry. `periods_filled` = count of distinct periods (0–5). `status = Active` if `periods_filled ≥ 4`, else `Inactive`.
4. Return list with: metric name, periodicity, unit (if any), status (Active/Archived), MetricActivityStatus (Active/Inactive, periods_filled).

**Output:**
List of Metrics with activity status; response to user.

**Edge Cases:**
- No metrics exist: return empty list with guidance to create one.
- Metric has no entries: `periods_filled = 0`, `status = Inactive`.

**Acceptance Criteria:**
- AC-FR8-1: Deleted metrics do not appear in the list.
- AC-FR8-2: MetricActivityStatus reflects entries within the last 5 periods at time of request.
- AC-FR8-3: A metric with exactly 4 entries in 5 periods returns `MetricActivityStatus.status = Active`.

---

### FR-9: Metric Archival and Reactivation

**Description:**
A user may archive an Active Metric (suspending alert evaluation for it) or reactivate an Archived Metric. Archival does not delete the Metric or its Entries.

**Trigger:**
User issues `/metric_archive` or `/metric_reactivate` command with a metric identifier.

**Input:**
`metric_id` or metric name; user's `internal_user_id`.

**Processing Rules:**
1. Verify the Metric belongs to the user.
2. For archival: Metric must be in `status = Active`. Set `status = Archived`.
3. For reactivation: Metric must be in `status = Archived`. Set `status = Active`.
4. Alert evaluation on Archived metrics is suspended (AD-8). All existing Active Alerts on the metric are not deleted; they resume when the Metric is reactivated.
5. Respond with confirmation of new status.

**Output:**
Metric status updated; confirmation message.

**Edge Cases:**
- Archiving an already-Archived Metric: return informational message; no change.
- Reactivating an already-Active Metric: return informational message; no change.
- Archiving a Metric with no alerts: no alert-side effects; proceed normally.

**Acceptance Criteria:**
- AC-FR9-1: After archival, new entries for the metric do NOT trigger alert evaluation.
- AC-FR9-2: After reactivation, alert evaluation resumes for Active alerts on the metric.
- AC-FR9-3: Entries for an Archived metric can still be added (archival does not block data entry).

---

### FR-10: Metric Deletion with Cascade

**Description:**
A user may permanently delete an Active or Archived Metric. Deletion cascades to all associated Entries, Alerts, ParseAttempts, and MetricActivityStatus records. Deletion is irreversible and requires user confirmation.

**Trigger:**
User issues `/metric_delete` command with a metric identifier.

**Input:**
`metric_id` or metric name; user confirmation response.

**Processing Rules:**
1. Verify Metric belongs to the user; Metric `status` must be `Active` or `Archived`.
2. Dispatch deletion confirmation prompt. Set `ConversationState = PendingMetricDeletionConfirmation`.
3. Await user confirmation.
4. On confirmation: execute cascade deletion atomically (AD-7) — delete Metric, all associated Entries (including `raw_input` fields), all associated Alerts, all associated ParseAttempts (including `raw_input` fields), MetricActivityStatus. All writes are part of one atomic operation.
5. Set `ConversationState = Idle`.
6. On non-confirmation or cancellation: cancel deletion; set `ConversationState = Idle`; inform user.
7. Emit cascade deletion confirmation event to Observability Collector.

**Output:**
Metric and all associated data permanently deleted; confirmation message.

**Edge Cases:**
- Cascade deletion partially fails: atomic rollback; user notified; operator-detectable via Observability Collector. No partial deletion is visible.
- Metric already Deleted: return error.
- User does not respond to confirmation: system behavior governed by conversation state routing (FR-3); non-confirmation cancels deletion.

**Acceptance Criteria:**
- AC-FR10-1: After cascade deletion, no Entry, Alert, or ParseAttempt record referencing the deleted Metric is retrievable.
- AC-FR10-2: Cascade deletion is atomic — either all records are deleted or none are.
- AC-FR10-3: `raw_input` fields on associated Entries and ParseAttempts are permanently purged as part of cascade deletion.
- AC-FR10-4: Deletion without user confirmation is impossible.

---

### FR-11: Alert Configuration

**Description:**
A user may configure a threshold alert on any Active Metric. When the alert condition is met after a new entry is stored, the system fires a one-shot notification and transitions the alert to `Triggered`. The alert does not fire again automatically.

**Trigger:**
User issues `/alert_set` command.

**Input:**
`metric_id` or metric name, `target_dimension` (null for single-value metrics; required dimension name for compound metrics), `condition` (`above`|`below`), `threshold_value` (numeric).

**Processing Rules:**
1. Verify Metric exists for the user and `status = Active`.
2. For compound metrics: validate `target_dimension` is a valid dimension name within the Metric's `dimension_names`.
3. For single-value metrics: `target_dimension = null`.
4. Validate `condition ∈ {above, below}`.
5. Validate `threshold_value` is a finite numeric value (not NaN, not ±Infinity).
6. Create Alert record: `status = Active`, `last_triggered_timestamp = null`.
7. Respond with confirmation including alert summary.

**Output:**
Alert record created; confirmation message.

**Edge Cases:**
- Alert set on an Archived Metric: return error; alert cannot be set on an Archived Metric.
- Multiple alerts on the same metric/dimension combination: allowed (no uniqueness constraint on alerts per metric/dimension).
- `threshold_value` = 0: allowed.
- `target_dimension` not in Metric's `dimension_names`: return validation error.

**Acceptance Criteria:**
- AC-FR11-1: An Alert with `target_dimension` not in the Metric's `dimension_names` is rejected.
- AC-FR11-2: An Alert set on an Archived Metric is rejected.
- AC-FR11-3: A newly created Alert has `status = Active`.

---

### FR-12: Alert Evaluation (Post-Entry)

**Description:**
After each Entry is durably stored, the system evaluates all Active Alerts for the associated Metric. If a threshold condition is met, the alert transitions to `Triggered` and a notification is dispatched to the user.

**Trigger:**
Post-commit event after successful Entry storage (not transactionally coupled to Entry write).

**Input:**
Newly stored Entry record; all Active Alerts for the Metric.

**Processing Rules:**
1. Retrieve all Alerts for the Metric where `status = Active`.
2. Skip evaluation if `Metric.status = Archived` (AD-8). Enforced via explicit conditional check — entries CAN be stored for Archived metrics (FR-9 does not block data entry), so this is not structurally guaranteed.
3. For each Active Alert:
   a. For single-value entries: compare `Entry.value` against `Alert.threshold_value` using `Alert.condition`.
   b. For compound entries: compare `Entry.dimension_assignments[Alert.target_dimension]` against `Alert.threshold_value` using `Alert.condition`.
   c. If condition is met: set `Alert.status = Triggered`; set `Alert.last_triggered_timestamp = now()`.
4. Dispatch alert notification to user (single retry on failure).
5. Emit `alert_evaluation_event` (alert_id, entry_id, outcome) to Observability Collector.
6. Alert evaluation failure must NOT roll back the stored Entry.

**Output:**
Alert status updated to `Triggered`; notification dispatched; `alert_evaluation_event` emitted.

**Edge Cases:**
- Alert evaluation component fails entirely: entry is preserved; failure logged; `alert_evaluation_event` marked failed.
- Notification dispatch fails after single retry: Alert is `Triggered` but user not informed (R-011, known limitation). Emit `notification_dispatch_failure_event`.
- Entry.dimension_assignments does not contain `Alert.target_dimension`: skip evaluation for that alert; log warning.

**Acceptance Criteria:**
- AC-FR12-1: Alert evaluation failure does not roll back or block the stored Entry.
- AC-FR12-2: After triggering, `Alert.status = Triggered` regardless of notification dispatch outcome.
- AC-FR12-3: An `alert_evaluation_event` is emitted for every alert evaluated, with outcome recorded.
- AC-FR12-4: Alert evaluation is skipped for metrics where `Metric.status = Archived`.

---

### FR-13: Alert Re-arming

**Description:**
A user may reset a `Triggered` Alert back to `Active` status so it may fire again in the future.

**Trigger:**
User issues `/alert_rearm` command with an alert identifier.

**Input:**
`alert_id`; user's `internal_user_id`.

**Processing Rules:**
1. Verify Alert belongs to the user.
2. Alert must be in `status = Triggered`.
3. Set `Alert.status = Active`. `last_triggered_timestamp` is retained (not cleared).
4. Respond with confirmation.

**Output:**
Alert status updated to `Active`; confirmation message.

**Edge Cases:**
- Attempting to re-arm an already-Active alert: return informational message; no change.
- Attempting to re-arm an Archived or Deleted alert: return error.

**Acceptance Criteria:**
- AC-FR13-1: After re-arming, the Alert is in `status = Active` and will be evaluated on next matching entry.
- AC-FR13-2: `last_triggered_timestamp` is preserved after re-arming.

---

### FR-14: Chart Generation and Delivery

**Description:**
A user may request a time-series chart for a specified Metric. The system delivers an immediate acknowledgment and generates the chart image in a background coroutine, delivering it via Telegram Gateway.

**Trigger:**
User issues `/chart` command with a metric identifier and optional time range.

**Input:**
`metric_id` or metric name; optional time range (default: last 30 days — see OI-7).

**Processing Rules:**
1. Verify Metric belongs to the user; `status ∈ {Active, Archived}`.
2. Dispatch immediate acknowledgment message (≤5s from receipt — AG-1).
3. Launch background coroutine (fire-and-forget — AD-10): retrieve Entry history for the metric within the specified time range; generate time-series chart image.
4. Background coroutine: deliver chart image via Telegram Gateway (up to 30s). On rendering or delivery failure: dispatch a second Telegram message to the user with an error description (AD-10).
5. Emit `chart_invocation_event` and `chart_delivery_outcome_event` (success or failure) to Observability Collector.

**Output:**
Immediate acknowledgment; chart image delivered asynchronously; observability events emitted.

**Edge Cases:**
- Metric has no entries: return error message instead of chart (empty chart is not meaningful).
- Chart rendering failure: second error message dispatched to user; `chart_delivery_outcome_event` with outcome=failure emitted.
- Background coroutine crash after acknowledgment: user receives acknowledgment but no chart and no error (known limitation — AD-10). Operator-detectable via missing `chart_delivery_outcome_event`.

**Acceptance Criteria:**
- AC-FR14-1: Acknowledgment is dispatched within 5 seconds of the chart request.
- AC-FR14-2: Chart delivery is attempted within 30 seconds of the request.
- AC-FR14-3: A `chart_invocation_event` and `chart_delivery_outcome_event` are emitted for every chart request.
- AC-FR14-4: A chart request for a Metric with zero entries returns an error, not an empty chart.

---

### FR-15: Late Categorization of Deferred ParseAttempts

**Description:**
A user may view and categorize any of their Deferred ParseAttempts, assigning each to a Metric and creating the corresponding Entry.

**Trigger:**
User issues `/deferred_list` or `/deferred_categorize` command.

**Input:**
User's `internal_user_id`; selected ParseAttempt `parse_attempt_id`; selected `metric_id`.

**Processing Rules:**
1. For `/deferred_list`: retrieve all ParseAttempts for the user with `status = Deferred`. Return list with `raw_input`, `created_timestamp` for each.
2. For `/deferred_categorize`: user selects a Deferred ParseAttempt and a target Metric.
3. Verify selected Metric belongs to the user and `status = Active`.
4. Trigger Entry Processor: create Entry from `raw_input` using the selected Metric (FR-4 from step 3 onward).
5. Transition ParseAttempt `status = Resolved`.
6. Emit `late_categorization_event` to Observability Collector.

**Output:**
Entry created; ParseAttempt status updated to Resolved; confirmation message.

**Edge Cases:**
- User assigns a Deferred ParseAttempt to an Archived Metric: return error; must select an Active Metric.
- Deferred list is empty: return informational message.
- ParseAttempt already Resolved or Expired: return error; cannot re-categorize.

**Acceptance Criteria:**
- AC-FR15-1: A Deferred ParseAttempt that is categorized produces an Entry and transitions to `status = Resolved`.
- AC-FR15-2: A `late_categorization_event` is emitted for each successful late categorization.
- AC-FR15-3: Late categorization to an Archived Metric is rejected.

---

### FR-16: Account Deletion with Grace Period

**Description:**
A user may request deletion of their account. The system transitions the account to `PendingDeletion` for a 3-day grace period. During this period, the user may restore the account. After the grace period, the Scheduled Process permanently deletes all user data.

**Trigger:**
User issues `/account_delete` command.

**Input:**
User's `internal_user_id`; confirmation response.

**Processing Rules:**
1. Dispatch deletion confirmation prompt.
2. On confirmation: set `account_status = PendingDeletion`; set `deletion_scheduled_timestamp = now() + 72h`.
3. Notify ParseAttempt Manager to transition any active Pending ParseAttempt to Deferred before PendingDeletion transition completes.
4. Set `ConversationState = Idle` (if not already).
5. Inform user: account will be permanently deleted in 3 days; they may restore it before that deadline.
6. All subsequent messages from the user are routed exclusively to the restoration flow (FR-2).

**Output:**
`account_status = PendingDeletion`; `deletion_scheduled_timestamp` set; user informed.

**Edge Cases:**
- User with an active Pending ParseAttempt requests deletion: ParseAttempt Manager transitions ParseAttempt to Deferred before PendingDeletion completes.
- User requests deletion while in a non-Idle conversation state: state is cleared; deletion proceeds.
- Deletion confirmation not provided: deletion does not occur; `ConversationState = Idle`.

**Acceptance Criteria:**
- AC-FR16-1: After `/account_delete` confirmation, `account_status = PendingDeletion` and `deletion_scheduled_timestamp = now() + 72h`.
- AC-FR16-2: Any active Pending ParseAttempt is transitioned to Deferred before PendingDeletion is set.
- AC-FR16-3: No new entries, metrics, or alerts can be created by a PendingDeletion user.

---

### FR-17: Account Restoration

**Description:**
A user with `account_status = PendingDeletion` may restore their account to `Active` status within the 3-day grace period. All data is preserved.

**Trigger:**
User sends any message while `account_status = PendingDeletion`; account_status_gate routes to restoration flow (FR-2).

**Input:**
User's `internal_user_id`; confirmation response to restoration prompt.

**Processing Rules:**
1. Account Manager dispatches: "Your account is pending deletion. Confirm to restore it, or let the timer expire."
2. Set `ConversationState = PendingRestorationConfirmation`.
3. On confirmation: set `account_status = Active`; clear `deletion_scheduled_timestamp`; set `ConversationState = Idle`.
4. Inform user account is restored.
5. On non-confirmation: account remains `PendingDeletion`; user informed.

**Output:**
`account_status = Active`; confirmation message.

**Edge Cases:**
- Grace period expires before user restores: Scheduled Process permanently deletes data (FR-18). Restoration no longer possible.
- User confirms restoration multiple times: idempotent — second confirmation has no effect if already Active.

**Acceptance Criteria:**
- AC-FR17-1: After restoration confirmation, `account_status = Active` and `deletion_scheduled_timestamp` is cleared.
- AC-FR17-2: Restoration is only possible while `account_status = PendingDeletion`.
- AC-FR17-3: Restoration after grace period expiry is not possible.

---

### FR-18: Scheduled Data Purge and Retention Enforcement

**Description:**
The Scheduled Process runs at least every 12 hours and performs: (a) permanent purge of accounts where `deletion_scheduled_timestamp` has elapsed, (b) stale ParseAttempt cleanup, (c) stale PendingPeriodicity state cleanup, (d) enforcement of 1-year data retention guarantee.

**Trigger:**
Time-triggered; scheduled interval ≤12h.

**Input:**
Current timestamp; Data Repository state.

**Processing Rules:**
1. **Run-lock:** Atomic check-and-set on `scheduler_lock` record. If lock exists and is not expired: abort invocation; emit `scheduler_overlap_event`. If lock acquired: proceed. Release lock on completion (success or failure). A stale lock (timestamp > 2× scheduled interval) may be overridden by operator.
2. **PendingDeletion purge:** For all InternalUser records where `account_status = PendingDeletion` and `deletion_scheduled_timestamp ≤ now()`: execute atomic cascade deletion of all user data (all Metrics, Entries, Alerts, ParseAttempts, ConversationState, MetricActivityStatus, `raw_input` fields). Set `account_status = Deleted`. Operation is atomic per user (AD-7).
3. **1-Year retention enforcement:** For all InternalUser records where `account_status = Active` and `last_interaction_timestamp < now() - 1 year`: emit `retention_review_event` for operator action. Auto-deletion of Active accounts is not performed without explicit operator action.
4. **Stale ParseAttempt cleanup:** For all ParseAttempts where `status = Deferred` and `created_timestamp < now() - SU-006 (cleanup window, default 30 days — see OI-4)`: transition `status = Expired`; emit expiry event.
5. **Stale PendingPeriodicity cleanup:** For all ConversationState records where `state = PendingPeriodicity` and `state_entered_timestamp < now() - SU-009 (default 24h)`: clear state → Idle; emit `periodicity_prompt_event` (outcome=abandoned).
6. Emit `scheduler_heartbeat` event on every successful run.
7. All operations are idempotent.

**Output:**
Purged data; updated statuses; `scheduler_heartbeat` and job-specific events emitted.

**Edge Cases:**
- Cascade deletion of a single user fails: log failure; emit error event; continue processing other users; do not halt the entire job.
- `scheduler_lock` is stale: operator-detectable via missing heartbeats; may be overridden.
- SU-006 cleanup window undefined: stale Deferred ParseAttempt cleanup uses proposed default of 30 days pending OI-4 resolution.

**Acceptance Criteria:**
- AC-FR18-1: A `scheduler_heartbeat` event is emitted for every successful scheduled process run.
- AC-FR18-2: `scheduler_overlap_event` is emitted when a concurrent invocation is detected and aborted.
- AC-FR18-3: After purge, no Entry, Alert, ParseAttempt, or `raw_input` data for a Deleted user is retrievable.
- AC-FR18-4: Stale PendingPeriodicity states older than SU-009 are cleared to Idle.
- AC-FR18-5: Cascade deletion per user is atomic — either all data purged or none.

---

## 4. Non-Functional Requirements

| ID | Category | Requirement | Target | Measurement |
|----|----------|-------------|--------|-------------|
| NFR-1 | Performance | Entry acknowledgment latency | ≤ 5 seconds (p95) from message receipt to confirmation dispatch | Measure `stored_timestamp` → confirmation event delta in Observability Collector |
| NFR-2 | Performance | Disambiguation prompt dispatch latency | ≤ 5 seconds (p95) from message receipt to prompt dispatch | Observability Collector: `parse_outcome_event` timestamp delta |
| NFR-3 | Performance | Chart acknowledgment latency | ≤ 5 seconds (p95) from chart request to acknowledgment dispatch | `chart_invocation_event` → acknowledgment timestamp delta |
| NFR-4 | Performance | Chart delivery latency | ≤ 30 seconds (p95) from chart request to image delivery | `chart_delivery_outcome_event` timestamp delta |
| NFR-5 | Availability | Monthly uptime | ≥ 95% | Uptime measured as fraction of hours with at least one successful Telegram Gateway poll cycle per hour; `scheduler_heartbeat` gap detection |
| NFR-6 | Data Integrity | Entry immutability | 100% — no Entry record's `value`, `dimension_assignments`, or `raw_input` may be modified after creation | Audit: no UPDATE operations on Entry table; test: attempt direct modification returns error |
| NFR-7 | Security | Per-user data isolation | 100% — zero cross-user data visibility incidents | Audit test: queries scoped to `internal_user_id`; no unscoped query returns multi-user data |
| NFR-8 | Security | Telegram token confidentiality | Token never appears in source code, logs, or observability events | Static analysis scan; log grep; schema validation gate |
| NFR-9 | Privacy | `raw_input` exclusion from observability events | 0 events emitted containing `raw_input` content | Schema validation gate at emission boundary; rejected events logged as schema violations |
| NFR-10 | Observability | Parse outcome coverage | 100% of NLP parse attempts produce a `parse_outcome_event` | Count of entries + ParseAttempts vs. count of `parse_outcome_event` records per time window |
| NFR-11 | Observability | Alert evaluation coverage | 100% of alert evaluations produce an `alert_evaluation_event` | Count of entry-triggers vs. count of evaluation events per time window |
| NFR-12 | Observability | Scheduler heartbeat frequency | One `scheduler_heartbeat` per scheduled interval (≤12h); missing heartbeat = operator incident | Alert on gap > 2× scheduled interval in Observability Collector |
| NFR-13 | Data Retention | Minimum retention guarantee | User data retained for ≥ 1 year after `last_interaction_timestamp` | Scheduled Process audit: no Active user data purged before 1-year mark |
| NFR-14 | Data Retention | PendingDeletion grace period | Permanent purge occurs no earlier than 72h after `deletion_scheduled_timestamp` | Scheduled Process: check `deletion_scheduled_timestamp ≤ now()` before purge |
| NFR-15 | Scalability | Concurrent user ceiling | Stable operation at 20 concurrent users | Load test at 20 concurrent message-sending users; no data isolation failures |
| NFR-16 | Auditability | Cascade deletion completeness | All `raw_input` fields purged on account deletion and metric deletion | Post-deletion audit query: zero entries with purged metric_id or user_id |
| NFR-17 | Reliability | ParseAttempt atomicity | Zero dangling Pending ParseAttempts with no dispatched prompt after `parse_attempt_dangling_detection_window` | Observability query: Pending ParseAttempt with no `prompt_dispatched` event within window |
| NFR-18 | Data Integrity | Metric name uniqueness per user | Zero duplicate `(internal_user_id, metric_name)` pairs | DB-layer unique constraint; test: concurrent creation of same metric name returns one success |

---

## 5. Validation Rules

| Field / Entity | Validation Rule | Error Condition | System Response |
|----------------|----------------|-----------------|-----------------|
| InternalUser.account_status | Must be one of: `Active`, `PendingDeletion`, `Deleted` | Any other value | Reject write; emit schema error event |
| Metric.name | Non-empty string; ≤100 characters | Empty, null, or exceeds limit | Return validation error to user |
| Metric.name | Unique per `(internal_user_id, metric_name)` | Duplicate name for same user | Return error: "You already have a metric with this name." DB constraint enforces |
| Metric.periodicity | Must be one of: `daily`, `weekly` | Any other value | Return validation error: "Periodicity must be 'daily' or 'weekly'" |
| Metric.unit | If provided: non-empty, ≤50 characters | Empty string when provided | Return validation error |
| Metric.dimension_names | If provided: non-empty list; each name ≤50 characters; no duplicates within list | Duplicate dimension names; name exceeds limit | Return validation error listing the offending names |
| Metric.status | Must be one of: `Active`, `Archived`, `Deleted` | Any other value | Reject write; emit schema error |
| Entry.value | Numeric; finite (not NaN, not ±Infinity); null only if `dimension_assignments` populated | NaN or Infinity | Reject entry; notify user of invalid value |
| Entry.dimension_assignments | Map keys must match Metric.dimension_names; values must be finite numeric | Key not in Metric.dimension_names | Reject entry; notify user |
| Entry.entry_timestamp | ISO 8601 timestamp; must not be in the future by more than 1 minute (clock skew tolerance) | Future timestamp beyond tolerance | Use `stored_timestamp` instead; log warning |
| Alert.condition | Must be one of: `above`, `below` | Any other value | Return validation error |
| Alert.threshold_value | Finite numeric (not NaN, not ±Infinity) | NaN or Infinity | Return validation error |
| Alert.target_dimension | Must be null for single-value metrics; must be a valid name in Metric.dimension_names for compound metrics | Invalid or missing dimension | Return validation error |
| Alert.status | Must be one of: `Active`, `Triggered`, `Archived`, `Deleted` | Any other value | Reject write; emit schema error |
| ParseAttempt.status | Must be one of: `Pending`, `Resolved`, `Deferred`, `Expired` | Any other value | Reject write; emit schema error |
| ConversationState | Must be one of: `Idle`, `PendingDisambiguation`, `PendingPeriodicity`, `PendingMetricDeletionConfirmation`, `PendingRestorationConfirmation` | Any other value | Reject write; emit schema error |
| ConversationState (per user) | At most one non-Idle state per user | Attempt to set second non-Idle state | Reject; inform user of existing pending prompt |
| NLP confidence_score | Must be in range [0.0, 1.0] | Out of range | Treat as `outcome = unrecognized`; log warning |
| Observability event | Must not contain `raw_input` or any free-text user content | Schema validation gate rejects event | Log rejected event as schema violation; do not emit to collector |
| scheduler_lock | Exactly one record; acquire via atomic check-and-set | Lock exists and is not expired | Abort scheduled run; emit `scheduler_overlap_event` |

---

## 6. Status & Lifecycle Model

### InternalUser.account_status

| Status | Entry Condition | Exit Condition | Allowed Transitions |
|--------|----------------|----------------|---------------------|
| `Active` | New registration; or restoration from PendingDeletion | User requests deletion | → `PendingDeletion` |
| `PendingDeletion` | User confirms account deletion | Grace period elapses (Scheduled Process) or user restores | → `Deleted` (Scheduled Process after 72h); → `Active` (user restoration within 72h) |
| `Deleted` | Scheduled Process purge after grace period | Re-registration creates a NEW InternalUser record (not a transition) | No transitions — terminal state |

### Metric.status

| Status | Entry Condition | Exit Condition | Allowed Transitions |
|--------|----------------|----------------|---------------------|
| `Active` | Metric created (explicit or auto-create) | User archives or deletes | → `Archived`; → `Deleted` |
| `Archived` | User archives an Active metric | User reactivates or deletes | → `Active`; → `Deleted` |
| `Deleted` | User deletes (cascade deletion confirmed) | None — terminal | No transitions |

### Alert.status

| Status | Entry Condition | Exit Condition | Allowed Transitions |
|--------|----------------|----------------|---------------------|
| `Active` | Alert created; or user re-arms a Triggered alert | Alert condition met; cascade deletion | → `Triggered` (condition met); → `Deleted` (cascade) |
| `Triggered` | Alert condition met; notification dispatched | User re-arms; cascade deletion | → `Active` (re-arm); → `Deleted` (cascade) |
| `Archived` | Reserved — user-triggered archival deferred per architecture | — | → `Deleted` (cascade) |
| `Deleted` | Cascade deletion (metric or account) | None — terminal | No transitions |

### ParseAttempt.status

| Status | Entry Condition | Exit Condition | Allowed Transitions |
|--------|----------------|----------------|---------------------|
| `Pending` | ParseAttempt created; prompt dispatched | User selects metric; user defers; expiry timer fires; account enters PendingDeletion | → `Resolved` (user selects); → `Deferred` (user defers; expiry; PendingDeletion) |
| `Resolved` | User selects a metric; Entry created | None — terminal | No transitions |
| `Deferred` | User explicitly defers; expiry timer fires; account enters PendingDeletion | User performs late categorization; Scheduled Process cleanup (SU-006) | → `Resolved` (late categorization); → `Expired` (Scheduled Process cleanup) |
| `Expired` | Scheduled Process cleanup after SU-006 window | None — terminal | No transitions |

### ConversationState (per user)

| State | Entry Condition | Exit Condition | Routing Behavior |
|-------|----------------|----------------|------------------|
| `Idle` | Default; restored after any non-Idle state exits | Any transition to non-Idle | Standard intent classification |
| `PendingDisambiguation` | ParseAttempt Manager dispatches disambiguation prompt | Resolution/deferral/expiry of ParseAttempt | Route all messages to ParseAttempt Manager; block other intents |
| `PendingPeriodicity` | Entry Processor dispatches periodicity selection prompt | Periodicity confirmed; SU-009 timeout | Route all messages to Entry Processor; block other intents |
| `PendingMetricDeletionConfirmation` | Metric Manager dispatches deletion confirmation prompt | User confirms or cancels | Route to Metric Manager; cancellation on non-confirmation |
| `PendingRestorationConfirmation` | Account Manager dispatches restoration confirmation prompt | User confirms or does not confirm | Route to Account Manager; no change on non-confirmation |

---

## 7. Integration Requirements

| External Actor / System | Purpose | Data Exchanged | Failure Handling |
|------------------------|---------|----------------|------------------|
| Telegram Bot API (inbound) | Receive user messages via polling or webhook | Opaque Telegram user ID, message text, message timestamp | Retry up to 3× with exponential backoff on auth failure; halt process and emit `token_auth_failure_event` after exhaustion; operator must intervene |
| Telegram Bot API (outbound) | Deliver text messages and chart images to users | Message text; chart image bytes; target user's Telegram ID | Single retry for alert notifications; fire-and-forget for confirmations; second error message for chart delivery failure; Telegram API unavailability surfaced via Observability |
| NLP Parsing Engine | Parse free-text messages into structured metric data | Input: raw text string, user's metric vocabulary. Output: `(metric_name, values, dimension_assignments, confidence_score, outcome)` | Parse failure (exception or unrecognized) treated as `outcome = unrecognized`; triggers ParseAttempt flow; never causes silent data loss |
| Data Repository | Durable storage of all system entities | All entity reads and writes (see §9 for entity model) | Write failure: surface to user with retry instruction; never confirm storage without durable write. Read failure: surface as service unavailable; log for operator |
| Observability Collector | Capture structured events for metrics and health monitoring | Structured event records (IDs only, no free-text content) | Fire-and-forget; if collector unavailable, log to stderr; continue processing; coverage gap is operator-visible via absent events |

---

## 8. Error Handling & Failure Scenarios

### EH-1: Telegram Token Authentication Failure

- **Trigger:** Telegram Bot API returns token authentication error.
- **System Behavior:** Retry up to 3× with exponential backoff. If all retries fail, emit `token_auth_failure_event` to Observability Collector, then halt the process. Process supervisor handles restart.
- **User Impact:** All inbound and outbound messages halted during token failure window.
- **Recovery:** Operator investigates token validity; process supervisor restarts the process; token rotation is a redeploy-with-new-env-var operation.

### EH-2: Telegram API Rate Limit

- **Trigger:** Telegram API returns rate limit error on outbound message dispatch.
- **System Behavior:** Apply backoff per Telegram API guidance. Emit `telegram_rate_limit_event`. If alert notification fails due to rate limit after one retry, alert is Triggered but user not notified. Log `notification_dispatch_failure_event`.
- **User Impact:** Delayed or failed message delivery. Alert state is updated correctly regardless.
- **Recovery:** Operator-detectable via Observability. No automatic retry beyond the defined single retry for alert notifications.

### EH-3: Entry Storage Failure

- **Trigger:** Data Repository write fails during Entry creation.
- **System Behavior:** Do NOT send confirmation to user. Notify user: "Your entry could not be saved. Please re-submit." Do NOT trigger Alert Engine.
- **User Impact:** Entry is not stored. User must re-submit.
- **Recovery:** User re-submits; Data Repository recovers independently.

### EH-4: ParseAttempt Prompt Dispatch Failure (Atomicity Compensation)

- **Trigger:** ParseAttempt record created in Data Repository; subsequent prompt dispatch to Telegram Gateway fails.
- **System Behavior:** Delete the ParseAttempt record from Data Repository (atomicity compensation — AD-9). If deletion also fails, emit `dangling_parse_attempt_alert` event to Observability Collector. Return error to user.
- **User Impact:** User receives error; must re-submit. If dangling record persists, their subsequent submission will be blocked by the one-active-ParseAttempt constraint until operator clears it.
- **Recovery:** Operator clears the dangling ParseAttempt record. Detectable via `dangling_parse_attempt_alert` within `parse_attempt_dangling_detection_window` (default 30s).

### EH-5: Cascade Deletion Atomicity Failure

- **Trigger:** Data Repository write fails mid-cascade during metric or account deletion.
- **System Behavior:** Atomic rollback — no partial deletion is visible. Notify user: "Deletion could not be completed. Please try again." Emit `cascade_deletion_failure_event`.
- **User Impact:** All data remains intact. User may retry.
- **Recovery:** User retries deletion command. Operator investigates Data Repository state via Observability.

### EH-6: Alert Evaluation Failure

- **Trigger:** Alert Engine fails during post-commit evaluation.
- **System Behavior:** Entry is NOT rolled back. Log failure to Observability Collector with `alert_evaluation_event` (outcome=failed). Do not notify user of evaluation failure.
- **User Impact:** Alert may not fire when expected. Alert state is not changed.
- **Recovery:** Operator-detectable via failed `alert_evaluation_event`. No automatic retry.

### EH-7: Alert Notification Dispatch Failure

- **Trigger:** Telegram Gateway fails to deliver alert notification after single retry.
- **System Behavior:** Alert.status remains `Triggered` (persisted regardless of notification outcome). Emit `notification_dispatch_failure_event`.
- **User Impact:** Alert condition was met; user is not informed. Alert will not fire again automatically (one-shot behavior).
- **Recovery:** User must re-arm the alert and re-trigger it by submitting a new entry meeting the condition. No automatic recovery.

### EH-8: Chart Generation or Delivery Failure (Background Coroutine)

- **Trigger:** Chart rendering fails or Telegram delivery of chart image fails after acknowledgment was sent.
- **System Behavior:** Dispatch a second Telegram message to the user with an error description (AD-10). Emit `chart_delivery_outcome_event` (outcome=failure).
- **User Impact:** User receives acknowledgment and then an error message. No chart delivered.
- **Recovery:** User may retry the chart request.

### EH-9: Background Coroutine Silent Crash

- **Trigger:** Chart Generator background coroutine crashes after acknowledgment without dispatching either the chart or an error message.
- **System Behavior:** No second message dispatched. `chart_delivery_outcome_event` is never emitted.
- **User Impact:** User receives acknowledgment but no chart and no error (known limitation — AD-10).
- **Recovery:** Operator-detectable via missing `chart_delivery_outcome_event` following `chart_invocation_event`. User may retry.

### EH-10: Scheduler Overlap / Concurrent Invocation

- **Trigger:** A new Scheduled Process invocation fires while a previous run is still executing.
- **System Behavior:** New invocation checks the run-lock record atomically. If lock is active and not expired, abort new invocation. Emit `scheduler_overlap_event`.
- **User Impact:** None (new invocation aborted cleanly; prior invocation continues).
- **Recovery:** Operator-detectable via `scheduler_overlap_event`. If lock is stale (timestamp > 2× scheduled interval), operator may override.

### EH-11: Observability Collector Unavailable

- **Trigger:** Observability Collector fails to accept an event emission.
- **System Behavior:** Log event to stderr / local log. Continue processing the triggering operation normally. Do not retry event emission.
- **User Impact:** None during the outage. Metric coverage gap is operator-visible via absent events.
- **Recovery:** Operator investigates Observability Collector health. Events emitted during outage are irrecoverably lost.

### EH-12: Observability Event Schema Violation (raw_input detected)

- **Trigger:** A component attempts to emit an event containing `raw_input` or free-text user content.
- **System Behavior:** Schema validation gate at the emission boundary rejects the event. Log the rejection as a schema violation (without the offending content). Continue processing.
- **User Impact:** None.
- **Recovery:** Developer investigation; structural enforcement updated to prevent recurrence.

---

## 9. Data Model (Conceptual)

| Entity | Attributes | Required | Relationships | Constraints |
|--------|------------|----------|---------------|-------------|
| InternalUser | `internal_user_id` (opaque, system-generated), `registration_timestamp`, `last_interaction_timestamp`, `account_status` (Active\|PendingDeletion\|Deleted), `deletion_scheduled_timestamp` (nullable) | All except `deletion_scheduled_timestamp` | Owns Metrics, Alerts, ParseAttempts, ConversationState | No personal data fields; `internal_user_id` must not be derivable from Telegram ID |
| Metric | `metric_id`, `internal_user_id`, `name`, `periodicity` (daily\|weekly), `unit` (nullable), `dimension_names` (ordered list, nullable), `created_timestamp`, `status` (Active\|Archived\|Deleted) | `metric_id`, `internal_user_id`, `name`, `periodicity`, `status` | Belongs to InternalUser; has Entries, Alerts, MetricActivityStatus | Unique constraint: `(internal_user_id, name)`; `dimension_names` must have no duplicates; `periodicity` is closed vocabulary |
| Entry | `entry_id`, `metric_id`, `internal_user_id`, `value` (numeric, nullable), `dimension_assignments` (map: dimension_name → numeric, nullable), `stored_timestamp`, `entry_timestamp`, `raw_input` (verbatim text, immutable) | `entry_id`, `metric_id`, `internal_user_id`, `stored_timestamp`, `raw_input` | Belongs to Metric and InternalUser | Immutable after creation; exactly one of `value` or `dimension_assignments` is populated; `dimension_assignments` keys must match Metric.dimension_names |
| Alert | `alert_id`, `metric_id`, `internal_user_id`, `target_dimension` (nullable), `condition` (above\|below), `threshold_value` (numeric), `status` (Active\|Triggered\|Archived\|Deleted), `last_triggered_timestamp` (nullable) | `alert_id`, `metric_id`, `internal_user_id`, `condition`, `threshold_value`, `status` | Belongs to Metric and InternalUser | `target_dimension` null for single-value; valid dimension name for compound; `condition` closed vocabulary |
| ParseAttempt | `parse_attempt_id`, `internal_user_id`, `raw_input`, `candidate_metrics` (ordered list of metric_id + name pairs), `status` (Pending\|Resolved\|Deferred\|Expired), `created_timestamp`, `expiry_timestamp` | All fields | Belongs to InternalUser | At most one `status = Pending` ParseAttempt per user at any time |
| MetricActivityStatus | `metric_id`, `internal_user_id`, `status` (Active\|Inactive), `periods_filled` (integer 0–5), `computation_timestamp` | All fields | Belongs to Metric and InternalUser | Derived/lazy-computed on read (AD-4); `periods_filled` range [0, 5] |
| ConversationState | `internal_user_id`, `state` (Idle\|PendingDisambiguation\|PendingPeriodicity\|PendingMetricDeletionConfirmation\|PendingRestorationConfirmation), `state_entered_timestamp`, `context` (nullable) | `internal_user_id`, `state` | Belongs to InternalUser | One record per user; persisted; survives process restarts; closed vocabulary |
| scheduler_lock | `lock_id` (singleton), `acquired_timestamp`, `acquiring_process_id` | All fields | Standalone | Exactly one record; atomic check-and-set; stale if `acquired_timestamp < now() - 2× scheduled_interval` |

---

## 10. Business Rules Registry

**BR-1: One-Shot Alert**
- **Rule:** Once an Alert transitions to `Triggered`, it will not fire again automatically. The user must explicitly re-arm it.
- **Condition:** Alert.status = Triggered after evaluation.
- **Enforcement Point:** Alert Engine (post-evaluation); Alert.status persisted as Triggered.
- **Risk if Violated:** User assumes alert is still watching; silent data condition breach. Stated in onboarding message (FR-1).

**BR-2: Entry Immutability**
- **Rule:** Once an Entry record is written, its `value`, `dimension_assignments`, `entry_timestamp`, and `raw_input` cannot be modified.
- **Condition:** Any write to an existing Entry record.
- **Enforcement Point:** Data Repository layer; no UPDATE operations on Entry table.
- **Risk if Violated:** Historical data integrity compromised; time-series charts become unreliable.

**BR-3: No Silent Parse Failure**
- **Rule:** When the NLP Parsing Engine cannot auto-parse a message with sufficient confidence, the system must create a ParseAttempt and prompt the user. Silent discard of user intent is prohibited.
- **Condition:** NLP outcome ≠ auto-parse.
- **Enforcement Point:** Entry Processor / ParseAttempt Manager routing.
- **Risk if Violated:** User loses data without notification; core value proposition fails.

**BR-4: Per-User Data Isolation**
- **Rule:** No query or response may return data belonging to a different user's `internal_user_id`.
- **Condition:** All data reads.
- **Enforcement Point:** Data Repository layer — all queries are scoped by `internal_user_id`. Not enforced at application filtering layer (AD-5).
- **Risk if Violated:** Critical trust and privacy failure (R-005).

**BR-5: No Personal Data Storage**
- **Rule:** The system must not store Telegram username, display name, phone number, or email. Only an opaque `internal_user_id` is stored.
- **Condition:** User registration (FR-1) and any subsequent data write.
- **Enforcement Point:** Account Manager; Data Repository schema (no personal data fields).
- **Risk if Violated:** GDPR/privacy exposure (R-007); undermines D-007.

**BR-6: raw_input Exclusion from Observability**
- **Rule:** No observability event may contain `raw_input` or any verbatim user message text.
- **Condition:** All event emissions to Observability Collector.
- **Enforcement Point:** Schema validation gate at emission boundary (structural enforcement).
- **Risk if Violated:** Personal data exposure in logs; violates privacy policy stated at onboarding.

**BR-7: Metric Name Uniqueness per User**
- **Rule:** A user cannot have two Metrics with the same name.
- **Condition:** Metric creation (explicit or auto-create).
- **Enforcement Point:** Database-layer unique constraint on `(internal_user_id, name)` (AD-11).
- **Risk if Violated:** History fragmentation across duplicate metrics (R-003).

**BR-8: Cascade Deletion Atomicity**
- **Rule:** Deleting a Metric or user account must delete all associated records atomically. No partial deletion state is permitted.
- **Condition:** Metric deletion (FR-10); account purge by Scheduled Process (FR-18).
- **Enforcement Point:** Data Repository transaction boundary (AD-7).
- **Risk if Violated:** Orphaned records; potential cross-user data leakage from orphaned entries (R-005).

**BR-9: Periodicity Closed Vocabulary**
- **Rule:** Metric periodicity must be exactly `daily` or `weekly`. No other values are valid.
- **Condition:** Metric creation.
- **Enforcement Point:** Input validation (FR-7, FR-6); Data Repository schema constraint.
- **Risk if Violated:** MetricActivityStatus computation breaks; retention metric unmeasurable.

**BR-10: PendingDeletion Grace Period**
- **Rule:** Permanent user data purge must not occur sooner than 72 hours after `deletion_scheduled_timestamp`.
- **Condition:** Scheduled Process PendingDeletion purge.
- **Enforcement Point:** Scheduled Process: check `deletion_scheduled_timestamp ≤ now()` before purging.
- **Risk if Violated:** Premature data loss; violates user-facing retention commitment (D-013).

**BR-11: Onboarding Message Content**
- **Rule:** Every new user registration must be accompanied by an onboarding message explicitly stating: (a) 1-year minimum data retention, (b) no data export, (c) verbatim `raw_input` storage, (d) one-shot alert behavior.
- **Condition:** InternalUser creation (FR-1).
- **Enforcement Point:** Account Manager onboarding message composition.
- **Risk if Violated:** Users uninformed of privacy practices and behavioral constraints; trust breach.

**BR-12: Compound First-Contact Transactional Boundary**
- **Rule:** If a user's first message is also a data entry, onboarding must complete successfully before entry processing begins. Entry failure after successful onboarding must produce an explicit user notification to re-submit (not silent loss).
- **Condition:** FR-1 compound flow.
- **Enforcement Point:** Account Manager / Entry Processor coordination.
- **Risk if Violated:** Silent data loss at first contact is a critical UX failure (R-015).

---

## 11. Open Issues & Clarifications

### OI-1: NLP Confidence Threshold (SU-002) — P1

- **Why Unresolved:** The confidence threshold separating auto-parse from ambiguous/unrecognized has not been defined.
- **Impact on Implementation:** Too low → incorrect auto-parses permanently pollute immutable entry history. Too high → excessive ParseAttempts; friction undermines core value proposition.
- **Suggested Resolution Path:** Implement as configurable env var; start at 0.7; tune via `parse_outcome_event` operational data. Trigger re-evaluation if auto-parse error rate exceeds 15% of entries.

### OI-2: NLP Library / Service Choice — P0 (blocking)

- **Why Unresolved:** The NLP Parsing Engine's underlying technology has not been selected.
- **Impact on Implementation:** Blocks Entry Processor and ParseAttempt Manager implementation. Affects confidence_score semantics and latency characteristics.
- **Suggested Resolution Path:** Evaluate against: latency ≤5s, zero cost (portfolio), no personal data transmitted externally. Rule-based or lightweight statistical parser recommended as starting point given constrained domain vocabulary.

### OI-3: Data Repository Technology (AU-003) — P0 (blocking)

- **Why Unresolved:** Storage technology not selected.
- **Impact on Implementation:** Must support ACID transactions, unique constraints, concurrent reads, atomic check-and-set, and ConversationState persistence.
- **Suggested Resolution Path:** SQLite with WAL mode satisfies all requirements at portfolio scale (single process, ≤20 concurrent users) with zero operational overhead. PostgreSQL is the upgrade path.

### OI-4: Deferred ParseAttempt Cleanup Window (SU-006) — P1

- **Why Unresolved:** Cleanup window for Deferred ParseAttempts undefined.
- **Impact on Implementation:** FR-18 step 4 (stale ParseAttempt cleanup) blocked.
- **Suggested Resolution Path:** Default = 30 days (configurable via env var). Spec uses this as proposed default pending stakeholder confirmation.

### OI-5: MetricActivityStatus Staleness Tolerance — P2

- **Why Unresolved:** Maximum tolerable age of a cached MetricActivityStatus not defined.
- **Impact on Implementation:** Stale status misrepresents tracking retention metric.
- **Suggested Resolution Path:** Recompute if `computation_timestamp < now() - 1 periodicity unit` (24h for daily; 7 days for weekly).

### OI-6: Alert Listing and Delete Commands — P2

- **Why Unresolved:** Command surface for `/alert_list` and `/alert_delete` implied but not specified.
- **Impact on Implementation:** Users cannot manage alerts they cannot see.
- **Suggested Resolution Path:** Add `/alert_list` (Active and Triggered alerts per metric) and `/alert_delete` (with confirmation). Confirm with stakeholder.

### OI-7: Chart Time Range Default and Image Format — P2

- **Why Unresolved:** Default time range and chart output format not specified.
- **Impact on Implementation:** Chart Generator needs a defined default range and output format.
- **Suggested Resolution Path:** Default = last 30 days; format = PNG; axes: entry_timestamp (x), value/dimension (y); one line per dimension for compound metrics.

### OI-8: Re-registration Telegram ID Mapping Atomicity — P3

- **Why Unresolved:** When a Deleted user re-registers, the Telegram user ID → internal_user_id mapping must be updated atomically to point to the new record.
- **Impact on Implementation:** If not atomic, messages from the re-registered user may be routed to the old (Deleted) record.
- **Suggested Resolution Path:** Telegram ID mapping update and new InternalUser creation must be part of the same atomic operation. Confirm this is handled in Account Manager registration flow.

---

## 12. Traceability Matrix

| Business Goal | Context Element | Architecture Component | Functional Requirement | Risk Addressed |
|--------------|-----------------|----------------------|----------------------|----------------|
| Reduce tracking abandonment | Flow 1 (Onboarding), Flow 2 (Data Entry) | Telegram Gateway, Entry Processor, NLP Parsing Engine | FR-1, FR-4 | R-001 (friction hypothesis), R-002 (parse failure) |
| Reduce tracking abandonment | Flow 3 (Ambiguous Entry), ParseAttempt lifecycle | ParseAttempt Manager, User Session Guard | FR-5, FR-15 | R-002 (no silent discard — D-012) |
| Data input success rate > 85% | NLP Parsing Engine, ParseAttempt | NLP Parsing Engine | FR-4, FR-5 | R-002; NFR-10 (parse outcome coverage) |
| Enable self-insight through history | Flow 5 (Chart Request), Entry immutability | Chart Generator, Data Repository | FR-4 (immutability), FR-14 | R-006 (no export accepted); BR-2 |
| Feature adoption — charts > 25% | Flow 5 | Chart Generator, Observability Collector | FR-14 | EH-8, EH-9 (chart failure modes) |
| User data privacy and trust | Data isolation (AD-5), Cascade atomicity (AD-7), Privacy by design (D-007) | Data Repository, Account Manager | FR-1 (no personal data), FR-10, FR-18, BR-4, BR-5 | R-005 (cross-user leak), R-007 (GDPR residual) |
| User data privacy and trust | raw_input privacy (§4 Privacy Note, SCD v0.7) | Observability Collector (schema gate) | BR-6, NFR-9 | R-007 (raw_input personal data residual) |
| Alert delivery accuracy > 95% | Alert Engine (one-shot, post-commit) | Alert Engine | FR-11, FR-12, FR-13 | R-011 (notification dispatch failure) |
| Service continuity (≥95% uptime) | Scheduled Process, process supervisor, run-lock | Scheduled Process, Telegram Gateway | FR-18, EH-1, EH-10 | R-008 (single-person operator) |
| Tracking retention > 40% | MetricActivityStatus computation, periodicity | Metric Manager, Scheduled Process | FR-8, FR-6, FR-18 | R-003 (duplicate metric names) |
| Portfolio demonstration | All five success metrics observable | Observability Collector | NFR-10, NFR-11, NFR-12, FR-18 | R-008 (operator visibility) |
| Data retention guarantee (1 year) | Data Repository, Scheduled Process, D-013 | Scheduled Process | FR-18, NFR-13, NFR-14, BR-10 | R-006 (no export), D-013 |
| Onboarding information completeness | Flow 1 (Onboarding message), §4 Privacy Note | Account Manager | FR-1, BR-11 | R-006 (user informed of no export), R-007 |

---

## 13. Readiness Assessment

### Are requirements testable?
**Yes.** Every Functional Requirement (FR-1 through FR-18) includes explicit Acceptance Criteria with measurable outcomes. Every Non-Functional Requirement (NFR-1 through NFR-18) specifies a numeric target and a measurement method.

### Are dependencies defined?
**Mostly yes, with two blocking open items.** OI-2 (NLP library) and OI-3 (Data Repository technology) must be resolved before development begins. All component interface contracts are defined. Development of Telegram Gateway, Message Dispatcher, User Session Guard, Account Manager, Metric Manager, Alert Engine, Scheduled Process, and Observability Collector may begin immediately.

### Are lifecycle states complete?
**Yes.** InternalUser, Metric, Alert, ParseAttempt, and ConversationState lifecycle models are fully specified with entry conditions, exit conditions, and allowed transitions.

### Are NFRs measurable?
**Yes.** All 18 NFRs specify a numeric target and a concrete measurement method via Observability Collector event queries or Data Repository audit queries.

### Is specification internally consistent?
**Yes, with one clarification introduced.** FR-12 explicitly states that alert evaluation skip for Archived metrics is enforced via a conditional check — not structurally guaranteed — because entries CAN be stored for Archived metrics (FR-9 does not block data entry). This corrects an implicit assumption in Architecture v0.9 (AD-8).

### Open Items Blocking Development

| Priority | Item | Blocking For |
|----------|------|-------------|
| P0 — Must resolve before dev | OI-2: NLP library/service choice | Entry Processor, ParseAttempt Manager |
| P0 — Must resolve before dev | OI-3: Data Repository technology | All persistence-dependent components |
| P1 — Must resolve before integration test | OI-1: NLP confidence threshold | FR-4/FR-5 integration testing |
| P1 — Must resolve before scheduler impl | OI-4: Deferred ParseAttempt cleanup window | FR-18 step 4 |
| P2 — Should resolve before MVP | OI-5: MetricActivityStatus staleness tolerance | FR-8 correctness |
| P2 — Should resolve before MVP | OI-6: Alert listing/delete commands | User alert management |
| P2 — Should resolve before MVP | OI-7: Chart time range default and format | FR-14 implementation |
| P3 — Resolve before production | OI-8: Re-registration Telegram ID mapping atomicity | FR-1, FR-2 edge case |

### Final Readiness Verdict

**Partially Ready for Development**

The specification is implementation-ready for all components whose dependencies are resolved. Development on Telegram Gateway, Message Dispatcher, User Session Guard, Account Manager, Metric Manager, Alert Engine, Scheduled Process, and Observability Collector may begin. Entry Processor and ParseAttempt Manager development is blocked on OI-2 and OI-3.

---

## Governance Block

### Version
v1.0

### Based On
- Business Analysis v0.5
- System Context Document v0.7
- Architecture Overview v0.9

### Change Summary
- Formalized 18 Functional Requirements with explicit acceptance criteria covering all system flows
- Formalized 18 Non-Functional Requirements with numeric targets and measurement methods
- Specified complete Validation Rules per entity/field
- Specified Status & Lifecycle Models for all five stateful entities
- Specified Integration Requirements with failure handling for all external actors
- Specified 12 Error Handling scenarios covering all high-risk failure modes
- Specified Conceptual Data Model aligned to System Context v0.7 entities with constraints
- Specified 12 Business Rules with enforcement points and risk statements
- Identified 8 Open Issues; 2 are P0-blocking for development
- Built Traceability Matrix covering all five business success metrics
- **Clarification introduced:** Alert evaluation skip condition (FR-12) is an explicit conditional check on `Metric.status = Archived` — not structurally guaranteed — because entries can be stored for Archived metrics (FR-9)
- **Clarification introduced:** 1-year retention enforcement emits `retention_review_event` for operator action rather than auto-purging Active accounts

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|----|----------|-----------|---------|--------|
| IS-D-001 | MetricActivityStatus recomputed if older than one periodicity unit | Prevents stale status from misrepresenting tracking retention metric | v1.0 | Proposed — pending stakeholder confirmation (OI-5) |
| IS-D-002 | 1-year retention enforcement emits operator review event, not auto-purge, for Active accounts | Business document specifies guaranteed retention, not auto-deletion; auto-purge of Active users requires explicit stakeholder approval | v1.0 | Confirmed (conservative interpretation) |
| IS-D-003 | Deferred ParseAttempt default cleanup window proposed at 30 days | No business requirement sets a shorter window; 30 days balances accumulation risk against late-categorization usability | v1.0 | Proposed — pending stakeholder confirmation (OI-4) |
| IS-D-004 | Chart default time range proposed as last 30 days | "All history" produces unreadable charts for long-running metrics; 30 days aligns with monthly comparison use case | v1.0 | Proposed — pending stakeholder confirmation (OI-7) |

### Uncertainty Map

| ID | Type | Description | Impact | Validation Plan |
|----|------|-------------|--------|-----------------|
| SU-001 | Configuration | ParseAttempt expiry timeout: 24h recommended, not confirmed | Deferred ParseAttempts accumulate if too long; user confusion if too short | Start at 24h; monitor deferral rate; adjust if > 20% of ParseAttempts expire unresolved |
| SU-002 | Algorithmic | NLP confidence threshold: undefined | Core >85% data input success rate target at risk | Implement as configurable env var; tune from operational data (OI-1) |
| SU-003 | Functional | Near-duplicate metric name detection: not in scope | R-003: users accumulate duplicate metrics | Deferred; inform users in onboarding to use consistent naming |
| SU-006 | Configuration | Deferred ParseAttempt cleanup window: undefined | Unbounded accumulation of Deferred ParseAttempts | Proposed default 30 days (IS-D-003); confirm with stakeholder |
| SU-009 | Configuration | PendingPeriodicity timeout: 24h default | User may not complete periodicity selection; entry not stored | Default 24h; `periodicity_prompt_event` outcome=abandoned emitted for operator visibility |
