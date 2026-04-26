# Architecture Overview

> **Version:** v0.9
> **Status:** Revised — addresses all mandatory revisions from architecture_v0.8_review.md
> **Date:** 2026-04-12
> **Previous Version:** v0.8 (architecture_v0.8.md)

---

## 1. Document References

- **Business Version:** v0.5 (`business_analysis_v0.5.md`)
- **Context Version:** v0.7 (`system_analysis_v0.7.md`)

All architectural decisions in this document are traced to sections and decisions in the above inputs. No business goals have been added or overridden.

---

## 2. Architectural Goals

| Goal | Why it matters | Linked Business Goal | Metric |
|------|---------------|---------------------|--------|
| AG-1: Low-latency user-facing responses | Users must receive feedback ≤5 s to avoid perception of failure and duplicate re-submissions | Reduce tracking abandonment | Entry ack ≤ 5 s; disambiguation prompt ≤ 5 s (§8.1, System v0.7) |
| AG-2: Reliable entry storage | An entry that the user believes was saved must be durably stored; confirmation dispatch failure must never roll back the stored record | Enable self-insight through history | Entry storage success rate; confirmation-without-storage = 0 |
| AG-3: Strict per-user data isolation | Cross-user data visibility is a 100% non-negotiable failure (R-005) | User data privacy and trust | Zero cross-user visibility incidents |
| AG-4: Measurable success metrics | All five business success metrics must be computable from system-generated events | Portfolio demonstration | All five metrics observable via Observability Collector |
| AG-5: Operational simplicity | Single operator, AI-agent assisted (R-008). System must be operable without a dedicated team | Service continuity | ≥95% monthly uptime; operator can diagnose incidents from logs alone |
| AG-6: Graceful NLP degradation | When automatic parsing fails, the system must never silently discard user intent (D-012, R-002) | Reduce tracking abandonment | ParseAttempt creation rate; disambiguation completion rate |
| AG-7: Correct lifecycle enforcement | Account deletion (3-day grace, SD-004), alert one-shot (SD-003), and cascade deletion atomicity must be enforced without manual intervention | User data privacy and trust; service continuity | Zero partial-purge incidents; PendingDeletion → Deleted transition on schedule |

---

## 3. Architecture Summary

The system is a **single-process, component-structured monolith** deployed as a Telegram bot backend serving approximately 10 users. Given the confirmed scale ceiling of 20 concurrent users (§8.2, System v0.7) and a single operational owner, the complexity of a distributed architecture is unjustified and actively harmful to operability.

The design organises the system into **logically separated, named components** — each with a clear responsibility and well-defined inputs/outputs — without physically distributing them into separate services. Components communicate in-process. This provides a clear upgrade path if scale requires distribution in the future, without incurring the operational overhead at current scale.

The primary interaction pattern is **synchronous request/response** driven by incoming Telegram messages. A single asynchronous concern — alert evaluation after entry storage — is modelled as a **post-commit event** within the same process. A **scheduled process** handles all time-triggered responsibilities: retention enforcement, PendingDeletion purge, stale ParseAttempt cleanup, and stale PendingPeriodicity state cleanup.

Chart generation is the only flow that uses a background execution path: an immediate acknowledgment is sent to the user, and chart image delivery is completed by a post-response fire-and-forget coroutine. No shared mutable state is written during chart generation — the coroutine is a read-only data access plus outbound delivery operation. Data Repository access during chart generation is treated as a concurrent read, which is assumed safe under the chosen storage technology (see AD-7 and concurrency note in AD-1).

The Telegram Bot API is the sole external communication channel (both inbound and outbound), and there is no alternative fallback channel.

---

## 4. Component Model

### 4.1 Core Components

| Component | Responsibility | Inputs | Outputs | Key Risks |
|-----------|---------------|--------|---------|-----------|
| **Telegram Gateway** | Receives all inbound messages from Telegram Bot API; dispatches all outbound messages (text and images) to users. **Token authentication failure behavior: retry up to 3 times with exponential backoff; if all retries are exhausted, emit `token_auth_failure_event` and halt the process — process supervisor handles restart. Continuing without a valid token would silently drop all messages; halt is the correct behavior.** | Telegram Bot API (polling or webhook); outbound message payloads from other components | Normalized inbound message events (user ID, message text, timestamp) to the Message Dispatcher; delivered responses to users | Telegram API unavailability halts all I/O; rate limits under unexpected load (R-004, R-019); token failure is not recoverable without operator intervention |
| **Message Dispatcher** | Classifies inbound messages by intent and routes to the responsible handler component. **Before classifying any message, the Dispatcher must consult the User Session Guard's current conversation state (§4.3). If the user's state is non-Idle, the Dispatcher routes the message according to the non-Idle routing policy defined in §4.3, overriding standard intent-based classification.** | Normalized inbound message events; User Session Guard conversation state | Routed calls to Entry Processor, ParseAttempt Manager, Metric Manager, Account Manager, Alert Engine, or Chart Generator | Failure to consult conversation state before routing creates dead-end user states; mis-classification silently routes a data entry to a command handler or vice versa |
| **User Session Guard** | Checks the InternalUser account status before any handler is invoked (Active / PendingDeletion / Deleted); **owns and maintains the per-user conversation state machine (§4.3)**; enforces the one-active-ParseAttempt-per-user constraint and the PendingPeriodicity single-prompt constraint; contains a placeholder access-control check point for future allowlist enforcement (R-018). **Allowlist check ordering: any allowlist check fires after the idempotent InternalUser lookup (to avoid blocking returning users) but before creating a new InternalUser record for a non-allowlisted first-time user.** | Inbound message event + internal_user_id | Account status decision (allow / block / redirect to restoration flow); current conversation state for the Dispatcher | Incorrect state read under concurrent messages; conversation state corruption if state transitions are not atomic at the Data Repository layer |
| **Entry Processor** | Orchestrates the data entry flow: invokes NLP Engine, determines auto-create vs. existing metric, manages **two-step periodicity prompt for new metrics** (step 1: send prompt → User Session Guard → PendingPeriodicity; step 2: receive periodicity selection → create metric + write entry atomically → User Session Guard → Idle), writes the Entry record, triggers alert evaluation, dispatches confirmation. **Metric is NOT written to the Data Repository until periodicity is confirmed.** | Parsed message intent from Dispatcher; NLP result from NLP Engine; periodicity selection from user (via PendingPeriodicity routing); Data Repository; Alert Engine | Stored Entry record; confirmation message to user; alert evaluation trigger; parse outcome event to Observability Collector | Entry immutability means a silently incorrect auto-parse permanently pollutes the time series (R-002); PendingPeriodicity timeout (SU-009) leaves entry unstored without error unless user retries |
| **NLP Parsing Engine** | Accepts raw free-text; returns (metric_name, values, dimension_assignments, confidence_score); does not make storage decisions | Raw free-text string; user's existing metric name vocabulary (from Data Repository) | Structured parse result: metric_name (string), value(s) (numeric), dimension_assignments (map), confidence (float), outcome (auto-parse / ambiguous / unrecognized) | Confidence threshold is undefined (SU-002); too low → incorrect auto-parses; too high → excessive ParseAttempts; NLP library / service choice is deferred |
| **ParseAttempt Manager** | Creates, updates, and resolves ParseAttempt records; manages Pending → Resolved / Deferred / Expired transitions; enforces one-active-ParseAttempt-per-user constraint; delivers disambiguation prompts; **owns the atomicity compensation for ParseAttempt + Prompt creation** (see AD-9); supports late categorisation (Flow G). **Receives coordination notifications from Account Manager on PendingDeletion transition (to transition active Pending ParseAttempts to Deferred before status change completes).** | NLP Engine outcome (ambiguous); user disambiguation selection; expiry events from Scheduler; user late-categorisation commands; Account Manager coordination notifications | ParseAttempt records in Data Repository; disambiguation prompt to Telegram Gateway; late categorisation list to user; late categorisation trigger to Entry Processor; deferral / expiry events to Observability Collector | Dangling Pending ParseAttempt with no dispatched prompt is a consistency failure (§8.3, System v0.7); Deferred entries accumulate without a cleanup policy (SU-006) |
| **Alert Engine** | Post-entry: evaluates all Active alerts for the metric against the new entry value; dispatches notification with single retry; logs evaluation result. **Behavioral constraint: alert evaluation is suspended when Metric.status = Archived (AD-8). Alert evaluation is also implicitly suspended during PendingDeletion — no entries are stored during PendingDeletion (User Session Guard routes all messages to the restoration flow), so no evaluation trigger is ever generated. This guarantee is structural, not a conditional check in the Alert Engine.** | New Entry record (post-storage); Alert records from Data Repository; Telegram Gateway | Alert status update in Data Repository; alert notification to Telegram Gateway; alert evaluation event to Observability Collector | Alert evaluation failure must not roll back the entry (§8.3, System v0.7); notification dispatch failure leaves the alert Triggered but user uninformed (R-011) |
| **Chart Generator** | Retrieves entry history for a metric; generates a time-series chart image; delivers to user via Telegram Gateway in a fire-and-forget post-response coroutine | Chart request (metric_id, optional time range); Data Repository (read-only) | Chart image → Telegram Gateway; chart invocation event + chart delivery outcome event to Observability Collector; error message as second Telegram message if rendering or delivery fails | No text-summary fallback if rendering fails (R-016); background coroutine crash after acknowledgment sent leaves user with no chart and no error (see §9 and AD-10) |
| **Metric Manager** | Handles explicit metric creation (Flow 7), metric listing (Flow 8), metric archival and reactivation (Flow H), and individual metric deletion (Flow 11) with cascade atomicity (AD-7); manages MetricActivityStatus computation; enforces SU-004 behavioral default (archival suspends alert evaluation). **User-triggered alert archiving and reactivation are explicitly out of scope for this architecture version — see deferred-scope note after Flow I in §5.2.** | User commands; Data Repository | Metric records; MetricActivityStatus (lazy computed on read — see AD-4); cascade deletion confirmation events; metric archival/reactivation state transitions; Observability events | Cascade atomicity failure leaves orphaned Entries or Alerts (R-005 data isolation impact); near-duplicate metric names not detectable under exact-match deduplication (R-003, SU-003) |
| **Account Manager** | Handles user onboarding (Flow I — compound first-contact) including idempotent registration; account deletion request (Flow C); account restoration within the 3-day grace period (Flow F); onboarding message composition. **On PendingDeletion transition: notifies ParseAttempt Manager to transition any active Pending ParseAttempt to Deferred before the PendingDeletion transition completes (no-op if no active ParseAttempt exists). Re-registration of a Deleted user is treated as a new onboarding — no reactivation of the Deleted record.** | First-contact trigger; deletion / restoration commands; Data Repository | InternalUser records; onboarding message; PendingDeletion state transition; Active state restoration; registration events to Observability Collector | Concurrent first messages racing to create duplicate InternalUser records (§8.3 idempotency requirement); compound first-contact flow partial failure must not silently lose entry intent (R-015) |
| **Scheduled Process** | Time-triggered (recommended cadence: at least every 12 hours): purges accounts where PendingDeletion grace period has elapsed; cleans up stale Deferred ParseAttempts (SU-006); **cleans up stale PendingPeriodicity conversation states beyond SU-009 timeout**; enforces 1-year retention guarantee (D-013). **Run-lock mechanism: at invocation start, performs an atomic check-and-set on a `scheduler_lock` record in the Data Repository. If the lock record exists and is not expired, the new invocation aborts and emits `scheduler_overlap_event`. If the lock is acquired, invocation proceeds; the lock is explicitly released on invocation end (success or failure). A stale lock — one whose timestamp exceeds two scheduled intervals — may be overridden and is operator-detectable via Observability. Must be idempotent.** | Scheduled time triggers; Data Repository | Permanent purge of eligible user data (atomic per user — AD-7); cleanup of stale ParseAttempts and PendingPeriodicity states; `scheduler_heartbeat` and execution result events to Observability Collector | Process failure leaves PendingDeletion accounts in limbo (D-013 obligation unmet); concurrent overlap causes race conditions on cascade deletions (§9) |

### 4.2 Supporting Components

| Component | Responsibility | Notes |
|-----------|---------------|-------|
| **Data Repository** | Durable storage of all system entities (InternalUser, Metric, Entry, Alert, ParseAttempt, MetricActivityStatus, **ConversationState — per-user conversation states are persisted to survive process restarts**, **scheduler_lock record**); enforces per-user data isolation at the storage layer; provides transactional semantics for atomic cascade deletions and idempotent writes; supports concurrent reads for chart generation background coroutine. **Metric name uniqueness enforced at the database layer via a unique constraint on `(internal_user_id, metric_name)` — see AD-11.** | Per-user isolation enforced at the repository layer — not at the application filtering layer (AD-5). Technology choice deferred (AU-003). Concurrent read access during chart generation is the only multi-threaded access pattern. |
| **Observability Collector** | Captures structured event records for all five business success metrics and operational health signals. **Failure contract: event emission is fire-and-forget; if the collector is unavailable, the component logs to stderr/local log and continues — metric coverage gap becomes operator-visible via absent events.** Emits `observability_collector_health` heartbeat to enable self-health monitoring. | Structured log events only. Raw_input must not appear in any event field — enforcement is structural: event schemas reference only IDs (user_id, metric_id, entry_id), never free-text content. Schema validation gate at the emission boundary rejects non-conforming events. |
| **Configuration & Secrets** | Manages the Telegram Bot API token, scheduled process intervals, ParseAttempt expiry timeout (SU-001), NLP confidence threshold (SU-002), ParseAttempt stale cleanup window (SU-006), scheduled process cadence, **periodicity prompt expiry timeout (SU-009, default 24 h)**, **`parse_attempt_dangling_detection_window` (default 30 s — the observation window for detecting a Pending ParseAttempt with no dispatched prompt; configurable to allow operational tuning of alert sensitivity)** | Telegram Bot API token must never appear in source code or logs. System reads it from environment at startup. Token rotation is a redeploy-with-new-env-var operation. Token authentication failure emits `token_auth_failure_event` before process halt. |

### 4.3 Conversation State Model

The User Session Guard owns and maintains a per-user conversation state machine. The Message Dispatcher **must** consult this state before routing any inbound message. If the user's state is non-Idle, the Dispatcher applies the routing policy for that state rather than performing standard intent classification. Conversation states are persisted in the Data Repository and survive process restarts.

**At most one non-Idle conversation state may be active per user at any time.** Any attempt to enter a second non-Idle state while one is already active is rejected by the User Session Guard, which informs the user of the existing pending prompt.

| Conversation State | Entry Condition | Routing Behavior for New Inbound Messages | Exit Condition |
|---|---|---|---|
| **Idle** | Default state; no pending prompt awaiting user response | Dispatcher routes normally based on intent classification | Any transition to a non-Idle state below |
| **PendingDisambiguation** | ParseAttempt Manager has dispatched a disambiguation prompt; a Pending ParseAttempt record exists for this user | Dispatcher routes to ParseAttempt Manager as disambiguation response. All other intents blocked: User Session Guard informs user "resolve or defer the active disambiguation before continuing." | ParseAttempt resolved → Idle; deferred by user command → Idle; expired by Scheduled Process → Idle |
| **PendingPeriodicity** | Entry Processor has dispatched a periodicity selection prompt for a new metric; metric record has **not** yet been written to the Data Repository | Dispatcher routes to Entry Processor as periodicity selection response. Non-periodicity messages: Entry Processor informs user "please select a periodicity to complete your entry first." State times out after SU-009 (default 24 h) — Scheduled Process clears stale state. | Periodicity confirmed: metric + entry created atomically → Idle. SU-009 timeout: Scheduled Process clears state, no metric or entry created → Idle. |
| **PendingMetricDeletionConfirmation** | Metric Manager has dispatched a "confirm metric deletion?" prompt (prior to cascade delete — Flow 11) | Dispatcher routes to Metric Manager as confirmation response. Non-confirmation: Metric Manager cancels deletion and informs user → Idle. | User confirms: cascade delete executed → Idle. User cancels or non-confirmation → Idle. |
| **PendingRestorationConfirmation** | Account Manager has dispatched "your account is pending deletion — confirm restoration?" prompt (Flow F) | Dispatcher routes to Account Manager as restoration response. | User confirms: account restored → Idle. Non-confirmation: account remains PendingDeletion, user informed → Idle. |

**Collision rule — PendingPeriodicity and PendingDisambiguation:** A user cannot hold both states simultaneously. If a user sends an ambiguous message while in PendingPeriodicity state, the Dispatcher routes it to Entry Processor as a non-periodicity message (blocked with "please complete periodicity selection first"). No new ParseAttempt is created while PendingPeriodicity is active.

---

## 5. Interaction Model

### 5.1 Interaction Patterns

| Pattern | Where Applied | Rationale |
|---------|--------------|-----------|
| **Synchronous Request/Response** | All user-triggered flows (entry, disambiguation, chart request, metric management, account management, late categorisation, archival/reactivation, restoration) | Telegram is a message-driven interface; users expect a response to each message; portfolio scale makes async complexity unjustified |
| **Post-Commit Event (in-process)** | Alert evaluation after Entry storage | Alert evaluation must not block or roll back entry storage; it is a downstream consequence, not a transactional requirement |
| **Post-Response Fire-and-Forget Coroutine** | Chart generation and delivery | Immediate acknowledgment ≤5 s is required; chart generation may take up to 30 s; no shared mutable state is written during chart generation |
| **Scheduled / Batch** | Scheduled Process: PendingDeletion purge, retention enforcement, stale ParseAttempt cleanup, stale PendingPeriodicity state cleanup | Time-triggered, not user-triggered; decoupled from the request/response path |

### 5.2 Key Flows

---

#### Flow A: Standard Data Entry

- **Trigger:** Registered user sends a free-text message parseable with sufficient confidence
- **Steps:**
  1. Telegram Gateway → Message Dispatcher (consult User Session Guard: confirm Idle state and Active account)
  2. Dispatcher → Entry Processor
  3. Entry Processor → NLP Parsing Engine (parse free-text → metric_name, values, confidence)
  4. NLP result: auto-parse confidence sufficient → Entry Processor → Data Repository (metric lookup)
     - **Metric exists (returning metric):** proceed directly to step 5
     - **Metric does not exist (new metric):** Entry Processor → Telegram Gateway (periodicity selection prompt); User Session Guard transitions to **PendingPeriodicity**; flow pauses awaiting user response
  4b. *[New metric — periodicity response path]* User responds with periodicity selection → Dispatcher (consults User Session Guard: PendingPeriodicity state) → routes to Entry Processor; Entry Processor → Data Repository (**create metric with confirmed periodicity + write Entry record, atomically**); User Session Guard → Idle; proceed to step 5
  4c. *[PendingPeriodicity timeout — SU-009]* Scheduled Process detects stale PendingPeriodicity state → clears state → User Session Guard → Idle. No metric or entry created. `periodicity_prompt_event` with outcome "abandoned" emitted.
  5. Entry Processor → Alert Engine (post-storage trigger — not transactionally coupled)
  6. Alert Engine → Data Repository (evaluate Active alerts for metric; skip if Metric.status = Archived — AD-8) → optionally → Telegram Gateway (notification dispatch)
  7. Entry Processor → Observability Collector (`parse_outcome_event`: parse_success, entry_id); fire-and-forget
  8. Entry Processor → Telegram Gateway (confirmation message)
- **Failure Points:**
  - Step 4b: Data Repository write failure → user notified to re-submit; User Session Guard remains PendingPeriodicity — user may retry periodicity selection
  - Step 5: Alert evaluation failure → entry preserved; failure logged; alert evaluation event marked failed
  - Step 8: Confirmation dispatch failure → entry is preserved; user may not receive confirmation (§8.3)
- **Recovery:** Entry storage failure is surfaced to the user immediately. Alert evaluation failure is operator-visible via Observability Collector.

---

#### Flow B: Ambiguous Entry (ParseAttempt Lifecycle)

- **Trigger:** Free-text message cannot be auto-parsed with sufficient confidence
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (confirm Idle state; confirm no existing Pending ParseAttempt or PendingPeriodicity state)
  2. If non-Idle state: User Session Guard → Telegram Gateway (inform user to resolve existing pending prompt first); flow ends
  3. If Idle: Dispatcher → ParseAttempt Manager
  4. ParseAttempt Manager → Data Repository (create ParseAttempt record, status = Pending) — **atomicity compensation owned by ParseAttempt Manager (AD-9):**
     - On successful record creation: immediately attempt prompt dispatch (step 5)
     - On prompt dispatch failure: ParseAttempt Manager → Data Repository (delete the ParseAttempt record); return error to user — no dangling Pending record
     - On ParseAttempt creation failure: return error to user immediately; no cleanup needed
  5. ParseAttempt Manager → Telegram Gateway (disambiguation prompt with candidate metrics)
  6. ParseAttempt Manager → User Session Guard (transition to **PendingDisambiguation**)
  7. ParseAttempt Manager → Observability Collector (ambiguous parse event); fire-and-forget
  8. [Later] User responds → Dispatcher (PendingDisambiguation state) → ParseAttempt Manager → resolves to Entry Processor (as Flow A from step 5); User Session Guard → Idle
  9. OR [Expiry] Scheduled Process / internal timer → ParseAttempt Manager → Data Repository (status = Deferred); User Session Guard → Idle; Observability event
- **Failure Points:**
  - Step 4 (prompt dispatch fails after record creation): ParseAttempt Manager deletes record, returns error to user. If deletion also fails, operator must manually clear the dangling record (detected via Observability Collector: `parse_attempt_event` with status=Pending and no subsequent `prompt_dispatched` event within `parse_attempt_dangling_detection_window` — default 30 s, configurable).
  - Expiry timeout value (SU-001) not yet defined — 24 h is the recommended starting point
- **Recovery:** Deferred ParseAttempts are not failures; they are resting states. Late categorisation is supported (Flow G). Cleanup window governs eventual discard (SU-006).

---

#### Flow C: Account Deletion with Grace Period

- **Trigger:** User sends account deletion request
- **Steps:**
  1. Telegram Gateway → Dispatcher → Account Manager
  2. **ParseAttempt coordination (pre-transition):** Account Manager → ParseAttempt Manager: if an active Pending ParseAttempt exists for this user, transition it to Deferred. This is a no-op if no active ParseAttempt exists. On coordination failure, Account Manager logs a warning and proceeds (any remaining Pending ParseAttempt will be detectable as a dangling record via Observability within `parse_attempt_dangling_detection_window`).
  3. Account Manager → Data Repository (set InternalUser.status = PendingDeletion, record deletion_scheduled_timestamp = now + 3 days)
  4. Account Manager → Telegram Gateway (3-day notice message — SD-004)
  5. Account Manager → Observability Collector (deletion scheduled event); fire-and-forget
  6. [3 days later] Scheduled Process → Data Repository (identify accounts past deletion_scheduled_timestamp with status = PendingDeletion → atomic purge of all user data — AD-7)
  7. Scheduled Process → Observability Collector (purge completion event, including per-user cascade counts)
- **Failure Points:**
  - Step 6: Scheduled Process failure → PendingDeletion accounts linger; deletion commitment unmet (D-013); operator must investigate via Observability Collector
  - Step 6: Partial purge → data integrity failure; process must be idempotent and resumable (§8.3)
- **Recovery:** Scheduled Process must be designed to resume partial purges safely. Operator alert if `scheduler_heartbeat` has been absent for more than two scheduled intervals.

---

#### Flow D: Alert Notification During Active ParseAttempt

- **Trigger:** New Entry stored for a user who has an active Pending ParseAttempt; an Active alert for that metric's threshold is crossed
- **Steps:**
  1. Alert Engine evaluates alert condition → condition met → dispatch notification
  2. Alert Engine → Telegram Gateway (alert notification formatted as a distinct block — "Alert fired:" header, no selectable options)
  3. ParseAttempt Manager still holds the active Pending ParseAttempt → disambiguation prompt is still the active user-facing request
- **Failure Points:**
  - User may confuse the alert notification for a disambiguation option (§11.5, System v0.7)
- **Recovery:** Formatting distinction is the sole mitigation. Accepted residual UX risk at portfolio scope.

---

#### Flow E: Scheduled Retention & Cleanup

- **Trigger:** Scheduled time trigger (recommended cadence: at least every 12 hours)
- **Pre-condition — Run-lock check:** Scheduled Process performs atomic check-and-set on `scheduler_lock` record in Data Repository. If lock exists and is not expired, new invocation aborts and emits `scheduler_overlap_event`. If lock is acquired, invocation proceeds.
- **Steps:**
  1. Scheduled Process → Observability Collector (`scheduler_heartbeat` event — emitted at start of every invocation, before any work)
  2. Scheduled Process → Data Repository: identify InternalUsers with last_interaction_timestamp > 1 year ago (D-013 retention enforcement) → atomic purge per user
  3. Scheduled Process → Data Repository: identify PendingDeletion accounts past deletion_scheduled_timestamp → atomic purge (AD-7)
  4. Scheduled Process → Data Repository: identify Deferred ParseAttempts past stale cleanup window (SU-006) → transition to Expired
  5. **Scheduled Process → Data Repository: identify PendingPeriodicity conversation states past SU-009 timeout → clear stale state; emit `periodicity_prompt_event` with outcome "abandoned" per cleared state**
  6. Scheduled Process → Observability Collector (`scheduler_run_completed` or `scheduler_run_failed` event with per-step counts and any errors)
  7. Scheduled Process → Data Repository: release `scheduler_lock` record
- **Failure Points:**
  - Process not running: all retention obligations are unmet; operator monitors `scheduler_heartbeat` absence
  - Partial execution: idempotency required at each step; each step independently resumable
  - Concurrent overlap: run-lock prevents; `scheduler_overlap_event` emitted if lock acquisition fails

---

#### Flow F: Account Restoration (Within Grace Period)

> Source: System v0.7 Flow 10a

- **Trigger:** User sends any message or explicit restore command while InternalUser.account_status = PendingDeletion
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (detects PendingDeletion status)
  2. User Session Guard → Account Manager (route to restoration handler)
  3. Account Manager → Telegram Gateway (informs user that their account is scheduled for deletion; asks for explicit restoration confirmation); User Session Guard → **PendingRestorationConfirmation**
  4. User confirms restoration:
     - Account Manager → Data Repository (set InternalUser.status = Active; clear deletion_scheduled_timestamp)
     - Account Manager → Telegram Gateway (confirmation: account fully restored, all data preserved)
     - User Session Guard → Idle
     - Account Manager → Observability Collector (`account_lifecycle_event`: account_restored); fire-and-forget
  5. If user does not confirm (sends any other message or does not respond): Account Manager → Telegram Gateway (informs user account remains pending deletion; no state change); User Session Guard → Idle
- **Failure Points:**
  - Data Repository write failure during restoration: Account Manager returns error to user; account remains in PendingDeletion — no data is lost
  - Restoration requested after 3-day window has elapsed and purge has already executed: Deleted user is treated as new registration (Flow I) — restoration is impossible
- **Recovery:** Restoration failure leaves the account in PendingDeletion (safe resting state). The Scheduled Process will execute the purge on schedule regardless.

---

#### Flow G: ParseAttempt Late Categorisation

> Source: System v0.7 Flow 3b (late categorisation subprocess)

- **Trigger:** User explicitly requests a view of their Deferred ParseAttempts
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (confirm Active account; confirm Idle state)
  2. Dispatcher → ParseAttempt Manager (late categorisation view request)
  3. ParseAttempt Manager → Data Repository (retrieve all Deferred ParseAttempts for the user)
  4. ParseAttempt Manager → Telegram Gateway (present list of Deferred ParseAttempts with retained raw_input and original message timestamp)
  5. For each Deferred ParseAttempt, user may choose:
     - **(a) Categorise:** User selects a metric → ParseAttempt Manager → Entry Processor (create Entry with entry_timestamp = original message timestamp, stored_timestamp = now) → Entry created; ParseAttempt transitions to Resolved; alert evaluation proceeds (Flow A from step 5)
     - **(b) Discard:** User discards the ParseAttempt → ParseAttempt Manager → Data Repository (status = Expired; raw_input purged) → Observability Collector (`parse_attempt_event`: parse_attempt_expired via user discard)
  6. ParseAttempt Manager → Observability Collector (late categorisation outcome event per item); fire-and-forget
- **Failure Points:**
  - No Deferred ParseAttempts exist: ParseAttempt Manager → Telegram Gateway (informs user; no error)
  - Entry creation fails during categorisation (step 5a): ParseAttempt Manager returns error to user; ParseAttempt remains in Deferred — user may retry
  - Associated metric was deleted before user returns: ParseAttempt already in Expired state; will not appear in Deferred list
- **Recovery:** Late categorisation is non-destructive until the user confirms discard or Entry creation succeeds.

---

#### Flow H: Metric Archival and Reactivation

> Source: System v0.7 §6 Metric State Model (Active ↔ Archived transitions)

- **Trigger:** User sends an archive or reactivate command for a specific metric
- **Archival sub-flow:**
  1. Telegram Gateway → Dispatcher → Metric Manager (archive command, metric_name)
  2. Metric Manager → Data Repository (confirm Metric.status = Active; set Metric.status = Archived)
  3. **Behavioral consequence (AD-8):** Alert Engine will no longer evaluate Active alerts for this metric against new entries while Metric.status = Archived. Existing alerts are preserved in their current status; they are not deleted.
  4. Metric Manager → Telegram Gateway (confirmation: metric archived; historical entries and alerts preserved)
  5. Metric Manager → Observability Collector (`metric_lifecycle_event`: metric_archived); fire-and-forget
- **Reactivation sub-flow:**
  1. Telegram Gateway → Dispatcher → Metric Manager (reactivate command, metric_name)
  2. Metric Manager → Data Repository (confirm Metric.status = Archived; set Metric.status = Active)
  3. **Behavioral consequence (AD-8):** Alert Engine resumes evaluation of Active alerts for this metric against future entries.
  4. Metric Manager → Telegram Gateway (confirmation: metric reactivated; alert evaluation resumed)
  5. Metric Manager → Observability Collector (`metric_lifecycle_event`: metric_reactivated); fire-and-forget
- **Failure Points:**
  - Metric not found or already in target state: Metric Manager → Telegram Gateway (informative error; no state change)
  - Data Repository write failure: Metric Manager returns error to user; metric state unchanged
- **Recovery:** Both archival and reactivation are clean state transitions with no cascade effects.

---

#### Flow I: Compound First-Contact (Onboarding + Simultaneous Data Entry)

> Source: System v0.7 Flow 1 step 4

- **Trigger:** A new Telegram user (no InternalUser record exists) sends a message that contains parseable data entry intent (not merely a /start command)
- **Steps:**
  1. Telegram Gateway → Message Dispatcher (message received; User Session Guard: no InternalUser record found — first-contact path)
  2. Dispatcher → Account Manager (first-contact); original message text retained for subsequent entry processing
  3. Account Manager → Data Repository (create InternalUser, status = Active; idempotent upsert on Telegram user ID — database-layer unique constraint prevents duplicate records — AD-11)
  4. Account Manager → Telegram Gateway (onboarding message: retention policy, no-export notice, raw_input storage notice, one-shot alert notice)
  5. Account Manager → Entry Processor (signals that the original message should now be processed as a data entry using the newly created InternalUser context)
  6. Entry Processor → NLP Parsing Engine (parse original message text)
  7. Entry Processor proceeds as Flow A from step 4 (metric lookup → new metric periodicity prompt or existing metric → entry storage)
  8. Account Manager → Observability Collector (`registration_event`: user_registered); fire-and-forget
- **Partial Failure Semantics:**
  - **Step 3 fails (InternalUser creation fails):** Account Manager returns error to user; Entry Processor is not invoked. No registration; no entry. User retries naturally.
  - **Step 3 succeeds; steps 6–7 fail (entry processing fails after registration):** Account Manager emits `registration_event` success. Entry Processor returns explicit error to user: "Your account was created successfully. Your entry could not be processed — please send it again." No silent loss of entry intent (R-015).
  - **Step 6 yields ambiguous parse:** Entry Processor creates a ParseAttempt (Flow B path) using the new InternalUser's context. Compound onboarding and disambiguation run normally in sequence.
  - **Step 7 requires periodicity prompt (new metric):** Entry Processor sends periodicity selection prompt; User Session Guard → PendingPeriodicity. Flow I is complete; the user's next message resolves via the PendingPeriodicity routing path.
- **Failure Points:**
  - Registration success + entry failure must surface an explicit user-facing error — never silently drop the entry intent (R-015)
- **Recovery:** User re-submits the entry; since InternalUser now exists, subsequent messages follow Flow A (not Flow I)

---

> **Deferred Scope — User-Triggered Alert Archiving:**
> System v0.7 §6 Alert State Model defines an "Archived" state reachable via "User archives alert" and the inverse user-triggered reactivation. **User-triggered alert archiving and reactivation are explicitly out of scope for this architecture version.** Rationale: the current alert management surface — Flow 9 (alert listing and deletion) and AD-8 (evaluation suspension via metric archival) — covers the primary alert lifecycle without a per-alert archive command. Implementing this capability requires a new user command, a new component responsibility assignment, a new flow, and a new observability event schema. These are scoped to a future architecture revision. Until that revision, **the Alert Archived state via user-triggered action must not be implemented** by implementation teams. Any such state transition discovered in implementation must be escalated for architectural review.

---

## 6. Data Strategy (Conceptual)

| Entity / Domain Data | Owner Component | Consistency Needs | Lifecycle | Risks |
|---------------------|----------------|------------------|-----------|-------|
| InternalUser | Account Manager (write) / User Session Guard (read) / Data Repository (store) | Strong consistency on creation (idempotent, no duplicates — §8.3). **Re-registration after Deleted status creates a new record — never reactivates the deleted one** | Active → PendingDeletion → Deleted (terminal); purged by Scheduled Process | Concurrent first-message race creating duplicate records (§8.3); Deleted users who re-register must start fresh with a new InternalUser record |
| Metric | Metric Manager / Entry Processor (auto-create, after periodicity confirmed — see Flow A step 4b) | Consistent name-uniqueness per user. **Uniqueness enforced at the database layer via a unique constraint on `(internal_user_id, metric_name)` — not at the application layer (see AD-11). Application-layer query-before-insert is explicitly rejected as TOCTOU-vulnerable.** Dimension_names immutable after first entry | Active ↔ Archived (bidirectional); Active or Archived → Deleted (cascade from metric deletion or account deletion) | Near-duplicate names fragment history (R-003); dimension naming locked after first compound entry; metric record not created until periodicity is confirmed (Flow A step 4b) |
| Entry | Entry Processor / Data Repository | Immutable after storage; entry_timestamp must preserve original message time even for late-categorised entries (entry_timestamp ≠ stored_timestamp for Flow G) | Stored → Deleted (cascade from metric or account deletion only) | Incorrect auto-parse permanently pollutes time series (R-002); raw_input is residual personal data (R-017) |
| Alert | Alert Engine / Metric Manager | Status transitions must be atomic; re-arm resets status to Active; **evaluation suspended when parent Metric.status = Archived (AD-8); evaluation implicitly suspended during PendingDeletion (structural guarantee — no entries stored, therefore no evaluation trigger generated)**. **User-triggered Alert Archived state (System v0.7 §6) is out of scope for this architecture version — see §5.2 deferred-scope note.** | Active → Triggered → Active (re-arm) \| Deleted (cascade) | One-shot behavior: Triggered alert never fires again without explicit user re-arm (SD-003) |
| ParseAttempt | ParseAttempt Manager | Consistent with one-active-per-user constraint; **creation and prompt dispatch atomically compensated (AD-9)**; **active Pending ParseAttempt transitioned to Deferred before PendingDeletion transition completes (Flow C step 2)** | Pending → Resolved (terminal) \| Pending → Deferred → Expired (terminal) | Dangling Pending without dispatched prompt is a consistency failure (§8.3); resolved via AD-9 compensating delete |
| ConversationState | User Session Guard (read/write) / Data Repository (store) | **Persisted in Data Repository to survive process restarts. At most one non-Idle state per user. State transitions are atomic (single Data Repository write per transition).** | Idle ↔ PendingDisambiguation / PendingPeriodicity / PendingMetricDeletionConfirmation / PendingRestorationConfirmation; stale PendingPeriodicity states cleaned up by Scheduled Process after SU-009 timeout | State corruption under concurrent messages from the same user (mitigated by atomic state transitions at repository layer) |
| MetricActivityStatus | Metric Manager (lazy compute on read — AD-4) | Eventually consistent; computed from Entry history on demand; **`active_users_count` for Observability Collector pushed on each Entry write** | Derived — recomputed; no separate lifecycle | Stale if computation is triggered at wrong time relative to timezone boundaries (SU-007) |
| raw_input (on Entry and ParseAttempt) | Data Repository | Retained as part of parent record | Purged atomically on account deletion (Flow C) and metric deletion (Flow 11) | Residual personal data risk (R-017); no scrubbing at portfolio scope (SD-005); user informed at onboarding |
| scheduler_lock | Scheduled Process / Data Repository | Atomic check-and-set on acquisition; explicit release on completion. Stale locks (timestamp older than two scheduled intervals) may be overridden. | Created on Scheduled Process invocation start; released on invocation end | Stale lock from crashed invocation could block subsequent runs; mitigated by lock age check |

---

## 7. Non-Functional Requirements Coverage

### 7.1 NFR Mapping

| NFR Category | Requirement | Architectural Tactic | Trade-off |
|-------------|-------------|---------------------|-----------|
| Performance — Entry ack | ≤ 5 s end-to-end (§8.1, System v0.7) | NLP Engine is in-process (no network round-trip to external NLP service preferred); Data Repository on same host or low-latency connection | In-process NLP limits language model complexity; larger models may require an external service adding latency |
| Performance — Chart ack | ≤ 5 s acknowledgment; ≤ 30 s full delivery | Two-phase response: immediate acknowledgment via Telegram Gateway; chart generation in post-response fire-and-forget coroutine (AD-6, AD-10) | Adds implementation complexity for the two-phase pattern |
| Performance — Alert dispatch | ≤ 60 s from entry storage to notification | Post-commit in-process evaluation; no queue needed at 10-user scale | If evaluation blocks, the 60 s budget is consumed; at scale this would require a queue |
| Availability | ≥ 95% monthly uptime (§8.2, System v0.7) | Single-instance deployment with process supervisor / container restart-on-failure; **health check contract: a `/health` endpoint (or equivalent polling-mode heartbeat signal) returns `{status: "ok", uptime_s: <seconds>}` on success. Polling-mode health check default (AD-2 resolved): a successful Telegram API poll response is used as the health proxy — this confirms both process liveness and API connectivity. Process supervisor monitors poll success signal at configurable intervals; absence triggers restart.** | Single point of failure; no hot standby at portfolio scale |
| Scale ceiling | ≤ 20 concurrent users without architecture review | Monolithic design with internal concurrency handling; explicit ceiling documented | Exceeding ceiling requires architecture review |
| Atomicity — Registration | Idempotent; no duplicate InternalUser records | Upsert or unique-constraint-on-Telegram-ID at Data Repository layer | Requires database-level uniqueness enforcement |
| Atomicity — Cascade deletion | Atomic per user (account) and per metric — **AD-7** | Single database transaction spanning all related entities | Transaction scope increases with data volume; not a concern at ~100 time series |
| Atomicity — ParseAttempt + Prompt | ParseAttempt creation and prompt dispatch treated as a unit — **AD-9** | ParseAttempt Manager owns compensating delete: if prompt dispatch fails, ParseAttempt record is deleted before returning error to user | Compensating delete adds a second write on the failure path |
| Reliability — Backup / RPO | D-013 (1-year retention guarantee) requires data to survive a Data Repository failure | **Daily file export to operator-controlled durable storage. RPO ≤ 24 h; RTO ≤ 4 h. Mechanism must be in place before first deployment.** | A daily export is simple but means up to 24 h of data is unrecoverable |
| Reliability — Scheduled Process cadence | Worst-case delay between PendingDeletion grace expiry and actual purge must be predictable | **Recommended minimum cadence: at least every 12 hours.** Worst-case purge delay = one scheduled interval beyond the 3-day grace period. | Cadence is configurable |
| Reliability — Observability Collector failure | Event emission must not fail silently or block main flows | **Fire-and-forget contract: if collector is unavailable, component logs to stderr/local log and continues.** `observability_collector_health` heartbeat enables detection. | Individual events may be lost during collector downtime |
| UX — Periodicity prompt expiry | Pending periodicity selection must have a defined resolution when user never responds | **PendingPeriodicity expires after SU-009 (default 24 h). Scheduled Process clears stale states at each invocation. No metric or entry is created on timeout — no orphaned records accumulate. `periodicity_prompt_event` with outcome "abandoned" emitted on cleanup. User may re-initiate the entry flow after timeout.** | 24 h chosen as consistent with ParseAttempt expiry (SU-001) |
| Concurrency — Monolith chart thread model | Chart coroutine runs concurrently with the main request-handling loop | **Coroutine is read-only relative to the Data Repository. No User Session Guard state or ParseAttempt state is accessed during chart generation. Concurrent reads are assumed safe under the chosen storage technology (AU-003 must confirm).** | If concurrent reads are unsafe, chart generation must be serialized |
| Security — Token | Bot API token must never appear in logs or source | Environment variable injection at startup; never logged; rotation is operator responsibility | Operator-side risk accepted |
| Security — User isolation | Per-user data isolation 100% non-negotiable | Isolation enforced at the Data Repository layer (all queries parameterized by internal_user_id) — not at the application layer (AD-5) | Application-layer filtering creates a miss-one-call vulnerability |
| Observability | All five success metrics must be computable | Structured event emission from every component to Observability Collector; fire-and-forget with local fallback | Adds an event-emission call to every significant code path |

### 7.2 NFR Unknowns

| Missing NFR | Decision Blocked |
|-------------|-----------------|
| **Deployment platform constraints** | Blocks: polling vs. webhook choice; process supervisor technology; scheduled process implementation. **Polling-mode health check default is resolved (AD-2): successful Telegram API poll response as health proxy.** |
| **NLP parsing library or service** | Blocks: performance estimate for entry ack latency; in-process vs. external decision; affects AD-1 trade-off |
| **Chart rendering library** | Blocks: chart delivery latency estimate; image size constraints; AD-6 two-phase feasibility confirmation |
| **ParseAttempt expiry timeout (SU-001)** | Recommended starting point: 24 hours. Must be confirmed and made configurable. |
| **NLP confidence threshold (SU-002)** | Must be defined before NLP Engine can distinguish auto-parse from ParseAttempt creation. Directly impacts 85% parse success target. |
| **Stale Deferred ParseAttempt cleanup window (SU-006)** | Recommended starting point: 30 days. Must be confirmed and configurable. |
| **Data Repository technology (AU-003)** | Blocks: transaction semantics for AD-7; unique-constraint-on-Telegram-ID (AD-5); compound unique constraint for metric name (AD-11); concurrent read safety for AD-10; backup tooling. |
| **Periodicity prompt expiry timeout (SU-009)** | **Default defined: 24 h.** Must be confirmed and made configurable at implementation. Included in Configuration & Secrets and Scheduled Process cleanup scope. |

---

## 8. Scalability & Performance Reasoning

**Expected load assumptions:**
- ~10 registered users; up to 20 concurrent users before architecture review
- ~100 active metric time series at steady state
- Entry frequency: estimated 1–5 entries per user per day = ≤ 100 entries/day total
- Chart requests: occasional, non-real-time
- Alert evaluations: triggered per entry; at ≤100 entries/day, total evaluations are trivial

**Bottlenecks:**

| Bottleneck | Component | Mitigation |
|-----------|-----------|-----------|
| NLP parsing latency | NLP Parsing Engine | Keep NLP in-process if library-based; if external, latency directly consumes the 5 s entry ack budget |
| Chart generation latency | Chart Generator | Two-phase response (immediate ack + post-response fire-and-forget coroutine) prevents timeout perception |
| Telegram Bot API rate limits | Telegram Gateway | At 10-user scale, rate limits are not a practical concern |
| Cascade deletion transaction size | Data Repository | At ~100 time series per user, transaction scope is small |
| Scheduled Process overlap | Scheduled Process | Run-lock (`scheduler_lock` record in Data Repository — atomic check-and-set) prevents concurrent invocations; `scheduler_overlap_event` emitted if overlap attempted |

**Caching boundaries (conceptual):**
- User account status and active conversation state may be cached in-process per request to avoid redundant Data Repository reads within a single message-handling cycle
- MetricActivityStatus is computed lazily on read (AD-4) — no pre-computation cache needed at this scale
- Metric name vocabulary (for NLP matching) may be cached in-process and invalidated on metric creation/deletion

**Queueing needs (conceptual):**
- None required at portfolio scale
- Alert evaluation is post-commit in-process; no queue needed
- If scale exceeds the ceiling, alert evaluation should be moved to a work queue

---

## 9. Reliability & Failure Scenarios

| Scenario | Impact | Detection | Mitigation | Residual Risk |
|----------|--------|-----------|------------|---------------|
| Telegram API unavailable | All I/O halted; bot appears offline | Telegram Gateway fails to connect; `bot_health` signal absent from Observability | Process supervisor keeps bot process alive; bot resumes polling when API recovers | No fallback channel |
| **Token authentication failure** | All inbound messages unprocessable | `token_auth_failure_event` emitted before process halt; process supervisor detects process exit | **Telegram Gateway retries up to 3 times with exponential backoff; if all retries exhausted, emits `token_auth_failure_event` and halts. Process supervisor restarts. If failure persists across restarts, operator must rotate the token. Continuing without a valid token would silently drop all messages — halt is correct.** | Bot remains offline until operator performs token rotation if token has been revoked |
| Data Repository unavailable | Entry storage fails; all flows fail at persistence step | Write call errors; Observability logs storage failure events | Operator alert; user notified to re-submit | Data entered during outage is lost unless user re-submits |
| Data Repository partial outage (read available, write unavailable) | Reads (chart, metric listing) succeed; writes fail | Write failures logged | Same as above for writes; read-only operations continue | Same as above |
| NLP Parsing Engine failure | All free-text entries route to ParseAttempt; parse success rate → 0% | Parse failure rate spike in Observability | ParseAttempt flow provides manual fallback | User experience degrades significantly |
| Alert Engine failure (post-commit) | Alert notifications not dispatched; accuracy target threatened | Alert evaluation failure events in Observability | Single retry on notification dispatch; entry preserved regardless | Silent alert failures after retry exhaustion |
| **Alert notification dispatch failure after retry exhausted** | Alert in Triggered state permanently; user receives no notification | `alert_evaluation_event` with `dispatch_outcome: "failed_after_retry"` | Operator-visible via Observability; alert remains Triggered — user may re-arm | User misses threshold notification without knowing it |
| Chart Generator failure (first phase — acknowledgment) | User does not receive "generating..." message | Error response to user | User receives explicit error message | Users cannot access visual history during failure |
| **Chart generation coroutine crash (second phase — after ack sent)** | User received ack but will never receive chart; silent failure | `chart_delivery_failure_event` emitted by coroutine error handler | Coroutine must catch all exceptions; on failure: send error as second Telegram message; emit `chart_delivery_failure_event` | If coroutine crashes without being caught, user receives no chart and no error |
| Scheduled Process failure | PendingDeletion accounts not purged; stale ParseAttempts and PendingPeriodicity states accumulate | Absence of `scheduler_heartbeat` in Observability | Operator investigation; manual re-run required | Deletion commitment unmet during failure window |
| **Scheduled Process concurrent overlap** | Two invocations racing on cascade deletions | `scheduler_overlap_event` emitted when new invocation detects existing `scheduler_lock` | **Run-lock mechanism: `scheduler_lock` record in Data Repository with atomic check-and-set at start and explicit release at end. Stale locks detectable by lock age.** New invocation aborts immediately on failed lock acquisition. | If lock is not implemented atomically, concurrent deletions could corrupt data |
| Concurrent first-message race | Duplicate InternalUser records | Duplicate key violation at Data Repository | Repository-level unique constraint on Telegram user ID | If uniqueness not enforced at DB layer, cross-user data association risk |
| Cascade deletion partial failure | Some Entries or Alerts survive after deletion; orphaned data | Purge completion event missing or cascade counts mismatched | Atomic transaction required (AD-7); idempotent and resumable | Data integrity failure if not atomic |
| Alert notification during ParseAttempt session | User confuses alert notification for a disambiguation selection | User provides unexpected input to ParseAttempt Manager | Formatting distinction between alert blocks and selection prompts | Residual UX confusion; accepted at portfolio scope |
| **Observability Collector unavailable** | All structured events lost; all five business metrics uncomputable | Absence of `observability_collector_health` heartbeat | Fire-and-forget: main flows continue; events written to stderr/local log | All five business metrics unmeasurable during outage |
| **Re-registration of a Deleted user** | Purged user sends new message; must start fresh | Account Manager detects Telegram user ID maps to Deleted InternalUser | Account Manager treats message as first-contact (Flow I); new InternalUser created with new internal_user_id | Repository must filter by non-Deleted status on lookup — correctness requirement |
| ParseAttempt + Prompt atomicity failure | Pending ParseAttempt created but no prompt delivered; user stuck | `parse_attempt_event` Pending with no prompt_dispatched within `parse_attempt_dangling_detection_window` | ParseAttempt Manager compensating delete (AD-9) | If compensating delete also fails, operator must manually clear; detectable via Observability |
| **PendingPeriodicity prompt abandoned by user** | User started new metric data entry, received periodicity prompt, never responded; state accumulates | `periodicity_prompt_event` with outcome "abandoned" emitted by Scheduled Process on SU-009 timeout cleanup | Scheduled Process clears stale PendingPeriodicity states after SU-009 (default 24 h); no metric or entry created on timeout | User must re-initiate entry flow; no data loss |
| **Compound first-contact partial failure (Flow I)** | InternalUser created but entry processing fails; user intent lost without explicit error | Co-occurrence of `registration_event` success and `error_event` in same session | Entry Processor returns explicit error: "account created, entry failed — please resubmit"; `registration_event` emitted on registration success regardless | No dedicated event for compound-failure type; detectable via event co-occurrence |

---

## 10. Security & Compliance Baseline

| Area | Threat / Risk | Control | Notes |
|------|--------------|---------|-------|
| **Telegram Bot API token** | Token exposure → full bot impersonation | Token injected via environment variable at startup; never logged, never in source code; rotation is operator responsibility. **Token failure behavior: retry up to 3 times with exponential backoff; if all retries fail, emit `token_auth_failure_event` and halt. Process supervisor handles restart.** | No in-scope token management infrastructure; operator risk accepted |
| **Per-user data isolation** | Implementation error leaks one user's data to another | All Data Repository queries parameterized by internal_user_id at the repository layer; never filtered at the application layer (AD-5). **Testability: repository interface must support injection of a test-controlled backend. Integration tests must verify that every read operation with a mismatched user_id returns empty or not-found.** | 100% non-negotiable target (R-005) |
| **Metric name uniqueness — TOCTOU protection** | Two concurrent messages from same user pass application-layer existence check before either insert completes → duplicate metric names | **Uniqueness enforced at the database layer via a unique constraint on `(internal_user_id, metric_name)` (AD-11). Application-layer query-before-insert is explicitly rejected. Constraint violation → Data Repository returns "metric name already exists" error → user-friendly message.** | At 10-user scale TOCTOU risk is low but non-zero. Database-layer enforcement eliminates it regardless of concurrency. |
| **User identity** | Identity linkage between Telegram user and stored data | Only an opaque internal_user_id is stored; Telegram identity fields (name, username, phone) are never persisted (D-007) | Residual risk accepted (R-007) |
| **raw_input personal data** | Free-text messages may contain personal or special-category data | User informed at onboarding; raw_input purged on account and metric deletion; no scrubbing at portfolio scope (SD-005) | Residual personal data risk elevated to Medium (R-017) |
| **raw_input in Observability events** | Accidental inclusion of raw_input in events → PII leakage into logs | **Structural enforcement: all event schemas reference only opaque IDs. Free-text fields are structurally absent. Schema validation gate at Observability Collector emission boundary rejects non-conforming events.** | Schema must be reviewed before deployment |
| **Open bot registration** | Any Telegram user can register; user count may exceed designed cohort | No access control enforced at this stage (R-018). **The User Session Guard contains a named placeholder check point for an allowlist gate. Allowlist check ordering: fires after idempotent InternalUser lookup (to avoid blocking returning users) but before creating a new InternalUser record for a non-allowlisted first-time user.** Single extension point for future access control. | Risk accepted at current scale |
| **PendingDeletion user — alert and entry residuals** | Alert notifications might fire for a user who has requested deletion | **Structural guarantee: no entries are stored during PendingDeletion (User Session Guard routes all messages to the restoration flow — Flow F). Since alert evaluation is triggered exclusively by Entry storage (AD-3), no alert evaluation trigger is ever generated during PendingDeletion. This guarantee is a structural consequence of routing, not a conditional check in the Alert Engine.** | Any code path that bypasses User Session Guard routing breaks this guarantee — User Session Guard is the single enforcement point |
| **Rate limiting** | Message flooding from a single user or public exposure | No rate limiting defined at portfolio scale; risk accepted (R-019) | Must be added before any public release |
| **Auditability** | Inability to trace a stored entry back to its source input | raw_input retained on Entry records; Observability Collector captures all significant events; cascade deletion counts logged | Observability Collector is the primary audit tool |

---

## 11. Observability Baseline

### 11.1 Signals

**Metrics (SLO candidates):**
- `entry_ack_latency_ms` — end-to-end from message received to confirmation dispatched (target ≤ 5,000 ms)
- `chart_ack_latency_ms` — from chart request received to "generating..." acknowledgment (target ≤ 5,000 ms)
- `chart_delivery_latency_ms` — from chart request received to image delivered (target ≤ 30,000 ms)
- `alert_dispatch_latency_ms` — from entry stored to alert notification delivered (target ≤ 60,000 ms)
- `parse_success_rate` — auto-parsed entries / total entries received (target > 85%)
- `bot_uptime` — % of scheduled health-check intervals with successful bot response (target ≥ 95% monthly)
- `active_users_count` — count of users with at least one active metric. **Freshness mechanism: pushed to Observability Collector on every successful Entry write by Entry Processor after Data Repository commit. At ≤100 entries/day, this is negligible overhead.**
- `chart_invocation_rate` — chart requests / active users (target > 25%); **counts only successfully delivered charts (uses `chart_delivery_success` event, not `chart_invocation_event`)**
- `alert_delivery_accuracy_rate` — alerts correctly fired and dispatched / alerts expected to fire (target > 95%)
- `cross_user_isolation_incidents` — count of cross-user data visibility events (target = 0, non-negotiable). **Detection: populated only by integration tests. No runtime detection mechanism — architectural control (AD-5) makes violations structurally impossible if correctly implemented.**

**Logs (structured):**
- `registration_event` — {event: "user_registered", internal_user_id, timestamp}
- `parse_outcome_event` — {event: "parse_success" | "parse_ambiguous" | "parse_failed", internal_user_id, metric_id (if resolved), confidence_score, entry_id (if stored), timestamp}
- `parse_attempt_event` — {event: "parse_attempt_created" | "parse_attempt_resolved" | "parse_attempt_deferred" | "parse_attempt_expired" | "parse_attempt_late_categorised", parse_attempt_id, internal_user_id, timestamp}
- **`periodicity_prompt_event`** — {event: "periodicity_prompt_dispatched" | "periodicity_confirmed" | "periodicity_abandoned", internal_user_id, metric_id (if confirmed), timestamp} — "periodicity_abandoned" is emitted by the Scheduled Process on SU-009 timeout cleanup
- `alert_evaluation_event` — {event: "alert_evaluated", alert_id, metric_id, internal_user_id, condition_met: bool, dispatch_outcome: "delivered" | "failed" | "retried" | "failed_after_retry", timestamp}
- `chart_invocation_event` — {event: "chart_requested", internal_user_id, metric_id, timestamp}
- `chart_delivery_event` — {event: "chart_delivered" | "chart_delivery_failed", internal_user_id, metric_id, failure_reason (if failed), timestamp}
- `account_lifecycle_event` — {event: "pending_deletion_scheduled" | "account_restored" | "account_purged" | "user_registered_post_deletion", internal_user_id, timestamp}
- `cascade_deletion_event` — {event: "metric_deleted" | "account_purged_cascade", metric_id (if metric deletion), internal_user_id, entry_count_deleted, alert_count_deleted, parse_attempt_count_expired, timestamp}
- `metric_lifecycle_event` — {event: "metric_archived" | "metric_reactivated", internal_user_id, metric_id, timestamp}
- `scheduled_process_event` — {event: "scheduler_run_completed" | "scheduler_run_failed" | "scheduler_overlap_detected", accounts_purged, parse_attempts_cleaned, **periodicity_states_cleared**, errors, timestamp}
- **`scheduler_heartbeat`** — {event: "scheduler_heartbeat", timestamp} — emitted at the **start** of every invocation, before any work; absence within two scheduled intervals is the operator alert trigger
- **`observability_collector_health`** — {event: "collector_heartbeat", timestamp} — emitted by the Observability Collector itself on a regular interval (e.g., every 5 minutes)
- `active_users_event` — {event: "active_users_count_updated", count, timestamp} — pushed by Entry Processor after each successful Entry write
- **`conversation_state_event`** — {event: "state_transition", internal_user_id, from_state, to_state, timestamp} — emitted by User Session Guard on every state transition; enables operator visibility into stuck or unexpected conversation states
- `error_event` — {event: "error", component, error_type, internal_user_id (if applicable), timestamp}
- `token_auth_failure_event` — {event: "token_auth_failure", component: "telegram_gateway", retry_count, timestamp}

> **Alert Archiving Observability note:** An `alert_lifecycle_event` schema for user-triggered alert archival/reactivation is not defined in this architecture version, consistent with the out-of-scope decision (§5.2 deferred-scope note). If alert archiving is added in a future revision, a new event schema must be defined and the `alert_delivery_accuracy_rate` metric definition updated to account for user-archived alerts.

**Traces (critical paths):**
- End-to-end: Telegram Gateway → Entry Processor → NLP Engine → Data Repository → Alert Engine → Telegram Gateway
- End-to-end: ParseAttempt Manager → Data Repository → Telegram Gateway (disambiguation and AD-9 compensation path)
- Background: Chart Generator coroutine → Data Repository (read) → Telegram Gateway (async chart delivery)
- **Compound onboarding: Account Manager → Data Repository → Entry Processor → NLP Engine → Data Repository**

### 11.2 Operational Dashboards (Conceptual)

| Dashboard | What to Monitor |
|-----------|----------------|
| **Bot health** | `bot_uptime` heartbeat; Telegram API connectivity; process restarts; `token_auth_failure_event` presence; `observability_collector_health` heartbeat presence |
| **Parse quality** | Rolling parse success rate (7-day window); ParseAttempt creation rate; disambiguation completion rate; late categorisation rate; **`periodicity_prompt_event` abandonment rate** |
| **Alert reliability** | Alert evaluation count; dispatch success vs. failure rate; retry rate; `failed_after_retry` count |
| **User activity** | `active_users_count` (near-real-time via `active_users_event`); entries per day; chart request count vs. `chart_delivery_event` success count |
| **Data lifecycle** | PendingDeletion accounts count and age; Deferred ParseAttempt count and age; **stale PendingPeriodicity state count**; `scheduler_heartbeat` last timestamp; `scheduler_run_completed` last timestamp and outcome |
| **Errors** | Error event count by component; cascade deletion failures; Data Repository write failure rate; `chart_delivery_failed` count |
| **Conversation state** | `conversation_state_event` transitions; count of users in non-Idle states; users in PendingPeriodicity or PendingDisambiguation for longer than SU-009 threshold |

---

## 12. Architectural Decisions (ADR-style)

### AD-1: Single-Process Monolith Architecture

- **Decision:** Deploy the system as a single process with logically separated, named components communicating in-process.
- **Alternatives considered:** (a) Microservices — each component as a separate deployable service; (b) Serverless functions — each flow as an independent function invocation.
- **Rationale:** The confirmed scale ceiling is 10 users (~100 metric time series). Distribution adds infrastructure complexity, network failure modes, and operational overhead that is disproportionate to the scale.
- **Trade-offs:** Single process = coupled failure modes. Offset by: component separation enables future extraction; process supervisor provides restart-on-failure.
- **Consequences:** Clear component interfaces must be enforced in code. No shared mutable state between components except through the Data Repository. **Concurrency note: the single process contains one asynchronous execution path — the chart generation coroutine (AD-6). Shared resources during coroutine execution are limited to the Data Repository (read path only). Concurrent reads are assumed safe under the chosen storage technology (AU-003 must confirm).**
- **Linked NFR/Business Goal:** AG-5 (operational simplicity); §8.2 scale ceiling; R-008 (single operator)

---

### AD-2: Telegram Gateway — Polling vs. Webhook

- **Decision:** Architecture is neutral between polling and webhook; the choice is deferred to deployment context. Webhook is preferred if the deployment platform supports a public HTTPS endpoint; polling is acceptable as a fallback. **Polling-mode health check default (resolved in v0.9): if polling mode is chosen, the health check uses a successful Telegram API poll response as the health proxy.** Rationale: a successful poll response confirms both process liveness and API connectivity. A local health file (the alternative considered in v0.8) would confirm only process liveness and would not detect API connectivity failures. The process supervisor monitors poll success signal at configurable intervals; absence triggers restart.
- **Alternatives considered:** Long-polling (simpler, no public endpoint required); webhook (lower latency, more efficient, requires HTTPS endpoint).
- **Rationale:** Both approaches are functionally equivalent for the Telegram Bot API. Webhook eliminates polling interval latency (up to ~1 s) and is more efficient, but requires a stable public HTTPS endpoint. Polling is a clean fallback with no additional latency concern at 10-user scale.
- **Trade-offs:** Polling adds ~1 s average latency to the entry ack budget; this is within the 5 s target.
- **Consequences:** The Telegram Gateway must support both modes behind the same interface. **In polling mode: health check is a successful poll response signal, not an externally callable HTTP endpoint. Process supervisor must be configured accordingly.**
- **Linked NFR/Business Goal:** AG-1 (≤ 5 s entry ack); NFR Unknown: deployment platform constraints

---

### AD-3: Post-Commit In-Process Alert Evaluation

- **Decision:** Alert evaluation is triggered immediately after successful entry storage, within the same request-handling cycle, but decoupled from the entry storage transaction.
- **Alternatives considered:** (a) Synchronous within the same transaction; (b) Asynchronous via a work queue.
- **Rationale:** At 10-user scale, synchronous in-process evaluation after commit satisfies the ≤ 60 s target. A work queue adds infrastructure without benefit. Including alert evaluation inside the entry storage transaction risks rolling back a valid entry on alert failure (§8.3 explicitly prohibits this).
- **Trade-offs:** A slow or failing alert evaluation delays the confirmation message to the user (though entry is already stored). Acceptable at portfolio scale.
- **Consequences:** Entry Processor must explicitly catch and log alert evaluation failures without propagating them as entry storage failures.
- **Linked NFR/Business Goal:** AG-2 (entry storage reliability); §8.3 atomicity; NFR: alert dispatch ≤ 60 s

---

### AD-4: MetricActivityStatus — Lazy Computation on Read

- **Decision:** MetricActivityStatus is computed on-demand when requested. However, `active_users_count` for the Observability Collector is pushed on each Entry write to maintain dashboard freshness.
- **Alternatives considered:** (a) Event-driven: recompute on every Entry write; (b) Scheduled: recompute on periodicity boundary; (c) Lazy: compute on read.
- **Rationale:** At ~100 time series, computation cost is negligible. Lazy computation is the lowest-complexity starting point. The Observability push on Entry write is a targeted read of the current computed value, not a full event-driven recomputation.
- **Trade-offs:** Observability push on Entry write adds minor overhead per entry (one read + one event emit). At 100 entries/day, negligible.
- **Consequences:** MetricActivityStatus is not a stored entity — derived on every read. Metric Manager owns this computation. Entry Processor must call the MetricActivityStatus read and emit `active_users_event` after successful entry storage.
- **Linked NFR/Business Goal:** AG-4 (success metrics measurable); business success metric: tracking retention >40%

---

### AD-5: Repository-Layer User Isolation

- **Decision:** Per-user data isolation is enforced at the Data Repository layer by including internal_user_id as a mandatory parameter in all data access operations, not at the application layer via result filtering.
- **Alternatives considered:** Application-layer filtering: components retrieve data and filter by user_id before returning.
- **Rationale:** Application-layer filtering is vulnerable to a "miss one call" failure mode — a single missing filter clause exposes all users' data. Repository-layer enforcement means the query itself is scoped to a single user_id.
- **Trade-offs:** Requires all repository access functions to include user_id as a mandatory typed parameter.
- **Consequences:** No "get all" operations may exist in the public repository interface that are not scoped by user_id. **Testability: interface must support injection of a test-controlled backend. Integration tests must call every read operation with a mismatched user_id and assert no data is returned.**
- **Linked NFR/Business Goal:** AG-3 (user data isolation); R-005 (cross-user leak — critical)

---

### AD-6: Two-Phase Chart Response

- **Decision:** Chart requests receive an immediate acknowledgment message (≤ 5 s) followed by the actual chart image delivered asynchronously (≤ 30 s from request).
- **Alternatives considered:** Single-phase: block the response until chart is generated.
- **Rationale:** Chart generation may take up to 30 s. Blocking risks user re-submission and Telegram bot timeout behavior.
- **Trade-offs:** Two-phase requires coordination between Telegram Gateway and Chart Generator for the two-step dispatch. Adds implementation complexity.
- **Consequences:** Chart Generator must support asynchronous execution (AD-10). Error message sent as the second Telegram message on failure. Delivery outcome emitted as `chart_delivery_event`.
- **Linked NFR/Business Goal:** AG-1 (response latency); §8.1 chart ack ≤ 5 s; chart delivery ≤ 30 s

---

### AD-7: Cascade Deletion Atomicity

- **Decision:** All cascade deletions are implemented as a **single database transaction** spanning all entities belonging to the deleted user or metric. The transaction commits only when all related entities have been successfully deleted. If any delete step fails, the transaction is rolled back and the deletion is retried on the next scheduled process run.
- **Alternatives considered:**
  - **(a) Single database transaction (chosen)**
  - **(b) Soft-delete with background vacuum worker:** PII (raw_input) remains physically present until vacuum runs — unacceptable given D-013 and R-005.
  - **(c) Application-level multi-step deletion with compensating writes:** Complex; inconsistent state possible if compensation also fails.
- **Rationale:** Option (a) is the simplest correct approach at this scale. Option (b) creates a PII exposure window. Option (c) adds coordination complexity without benefit.
- **Trade-offs:** Requires transaction support from the Data Repository (AU-003 must confirm).
- **Consequences:** Scheduled Process and Metric Manager must use a transactional delete pattern. Data Repository must expose a transactional cascade delete operation as a first-class method. Idempotency: rollback semantics ensure no partial state persists after a crash.
- **Linked NFR/Business Goal:** AG-7 (lifecycle enforcement); R-005 (data isolation); D-013 (retention guarantee)

---

### AD-8: Alert Evaluation Suspended for Archived Metrics (SU-004 Resolution)

- **Decision:** When Metric.status = Archived, the Alert Engine does not evaluate any Active alerts for that metric against new entries. Alert records are preserved in their current status. If the metric is reactivated, the Alert Engine resumes evaluating Active alerts.
- **Alternatives considered:**
  - **(a) Suspend evaluation on archival (chosen)**
  - **(b) Continue evaluation on archival:** Semantically unexpected — user would receive alerts for a metric they consider dormant.
  - **(c) Auto-archive or auto-delete associated alerts on metric archival:** Destructive; irreversibly loses alert configuration on reactivation.
- **Rationale:** Option (a) matches the semantic intent of archival: the metric is paused, not deleted. Alert configuration is preserved for reactivation.
- **Trade-offs:** Adds a status check to the Alert Engine's evaluation path — a trivially cheap check.
- **Consequences:** Alert Engine must include a guard: `if Metric.status == Archived: skip evaluation`. Flow H confirmation message must inform the user that alert notifications are paused while the metric is archived.
- **Linked NFR/Business Goal:** AG-7 (lifecycle enforcement); SU-004 resolution

---

### AD-9: ParseAttempt + Prompt Atomicity — Compensating Delete

- **Decision:** ParseAttempt creation and prompt dispatch are treated as an atomic unit via a **compensating delete** pattern owned by the ParseAttempt Manager. On prompt dispatch failure, the ParseAttempt Manager deletes the created ParseAttempt record before returning an error to the user.
- **Alternatives considered:**
  - **(a) Compensating delete on dispatch failure (chosen)**
  - **(b) Transactional create + dispatch:** Not feasible — Telegram Gateway dispatch is external I/O and cannot participate in a database transaction.
  - **(c) Retry dispatch on failure:** Adds latency without resolving the fundamental cleanup decision.
- **Rationale:** Option (a) is the simplest correct approach. The compensating delete must succeed; if it also fails, the dangling record is detected via Observability and operator manual cleanup is the resolution path.
- **Trade-offs:** Two write operations on the failure path (create + delete). Acceptable: the failure path is exceptional.
- **Consequences:** ParseAttempt Manager must implement the compensating delete in a try/finally or equivalent pattern. If the compensating delete fails: emit `error_event` with `error_type: "compensation_delete_failed"`. The dangling record is detectable via `parse_attempt_event` (Pending, no prompt dispatched) within `parse_attempt_dangling_detection_window` (default 30 s, configurable — see §4.2). **The 30 s default is chosen as sufficient to distinguish "dispatch in progress" from "dispatch genuinely failed" while being short enough for prompt operator detection. This value is configurable for operational tuning.**
- **Linked NFR/Business Goal:** AG-6 (graceful NLP degradation); §8.3 System v0.7 (ParseAttempt atomicity)

---

### AD-10: Async Chart Execution Model — Post-Response Fire-and-Forget Coroutine

- **Decision:** Chart generation is implemented as a **post-response fire-and-forget coroutine** launched after the acknowledgment message is sent to the user. The coroutine must: (a) catch all exceptions; (b) on failure, send an error message to the user as the second Telegram message; (c) emit `chart_delivery_event` with outcome "delivered" or "chart_delivery_failed" regardless of success or failure.
- **Alternatives considered:**
  - **(a) Post-response fire-and-forget coroutine (chosen)**
  - **(b) Dedicated background thread pool:** More controllable; adds thread management overhead; not justified at portfolio scale.
  - **(c) In-process task queue:** More formal; overkill for a single async concern.
- **Rationale:** Option (a) is the minimum viable implementation for a single async concern in a single-process monolith serving ≤10 users.
- **Trade-offs:** Fire-and-forget means no formal back-pressure. At 10-user scale with occasional chart requests, not a concern.
- **Consequences:** Chart Generator must include a top-level exception handler covering the full coroutine body. The coroutine accesses Data Repository in read-only mode. Telegram Gateway must support sending a follow-up message outside the request/response cycle.
- **Linked NFR/Business Goal:** AG-1 (chart ack ≤ 5 s); AG-5 (operational simplicity); AD-6 (two-phase chart response)

---

### AD-11: Metric Name Uniqueness Enforcement Layer

- **Decision:** Metric name uniqueness per user is enforced at the **database layer** via a unique constraint on `(internal_user_id, metric_name)`. Application-layer query-before-insert uniqueness checks are explicitly rejected.
- **Alternatives considered:**
  - **(a) Database-layer unique constraint (chosen):** Enforced atomically at insert time. Concurrent inserts with the same pair fail with a constraint violation.
  - **(b) Application-layer query-before-insert:** Rejected — vulnerable to TOCTOU race conditions. Two concurrent messages from the same user could both pass the existence check before either insert completes, creating duplicate metric names.
- **Rationale:** Option (b) is vulnerable to concurrent insertion races. Even at 10-user scale, the race is non-zero — and the consequence (duplicate metric names) breaks the invariant that metric names are user-unique identifiers for all time-series history. Option (a) eliminates the race by delegating uniqueness to the database transaction layer. This parallels AD-5 (database boundary is safer than application-layer check).
- **Trade-offs:** Requires AU-003 to confirm support for compound unique constraints (expected for any relational or document store with unique index support). Application must handle constraint violation errors gracefully — these are user-facing errors, not system errors.
- **Consequences:** Data Repository interface must expose a metric-create operation that relies on the database constraint for uniqueness. Metric Manager and Entry Processor must handle constraint violation errors from the Data Repository as a user-notification path. Near-duplicate metric names (e.g., "weight" vs. "Weight") are not covered — exact-match uniqueness only (SU-003).
- **Linked NFR/Business Goal:** AG-3 (user data isolation); R-003 (metric fragmentation risk); §10 security control (TOCTOU protection)

---

## 13. Risks & Open Questions

### 13.1 Architecture Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| NLP parsing latency exceeds the 5 s entry ack budget if an external service is required | High — core UX proposition undermined | Medium — depends on NLP library/service choice | Prefer in-process NLP library; if external, measure latency early. **A structured `/log` command fallback is NOT currently modelled — if NLP latency is persistently unacceptable, a future ADR will be required.** |
| Data Repository backup gap | Medium — data loss on Repository failure; D-013 unmet without backup | Medium — backup mechanism must be in place before first deployment | **Mitigated by §7.1 backup intent: daily file export; RPO ≤ 24 h; RTO ≤ 4 h. Risk reduced from High to Medium.** |
| Scheduled Process is a single point of failure for all time-triggered obligations | High — PendingDeletion purges never happen; stale states accumulate | Medium — failure is silent unless heartbeat monitored | `scheduler_heartbeat` event in Observability; operator alert if absent for more than two scheduled intervals; idempotent and re-runnable manually |
| Open bot registration (R-018) causes user count to exceed the 20-user architecture ceiling | Medium — system degrades without warning above ceiling | Low–Medium (if bot address leaks publicly) | Document the ceiling explicitly; User Session Guard contains a named access-control placeholder check point; allowlist mechanism can be added without structural changes |
| PII in Observability logs (raw_input accidentally logged) | Medium — privacy breach via log access | Low — if schema validation gate is enforced at design time | Structural schema enforcement: all event schemas reference only IDs; validation gate rejects non-conforming events |
| Async chart coroutine unhandled exception | Medium — user receives acknowledgment but no chart or error; silent failure | Low — if AD-10 exception handling contract is implemented | AD-10 mandates top-level exception handler; `chart_delivery_failed` event emitted; second Telegram message sent on failure |
| Observability Collector failure cascading to all five business metrics | High — all success metrics uncomputable | Low — collector is a simple structured log emitter | Fire-and-forget with stderr fallback; `observability_collector_health` heartbeat enables detection |
| Token authentication failure with unavailable operator | High — bot remains offline until manual token rotation | Low — token revocation is exceptional | Defined halt-and-restart behavior (AD-2, §9); `token_auth_failure_event` is the primary signal; operator must be reachable for token rotation |

### 13.2 Open Questions

1. **NLP library or service choice** — Blocks: in-process vs. external decision; entry ack latency estimate; AD-1 monolith trade-off confirmation. *Impact: High.*
2. **Deployment platform** — Blocks: polling vs. webhook decision (AD-2); process supervisor choice; scheduled process implementation. Polling-mode health check default is resolved (successful poll response as health proxy). *Impact: Medium.*
3. **Data Repository technology (AU-003)** — Blocks: transaction semantics for AD-7; unique-constraint-on-Telegram-ID (AD-5); compound unique constraint for metric name (AD-11); concurrent read safety for AD-10; backup tooling. *Impact: High.*
4. **ParseAttempt expiry timeout (SU-001)** — Recommended starting value: 24 hours. Must be confirmed and made configurable. *Impact: Medium.*
5. **NLP confidence threshold (SU-002)** — Must be defined before NLP Engine can distinguish auto-parse from ParseAttempt creation. Directly impacts the 85% parse success target. *Impact: High.*
6. **Stale Deferred ParseAttempt cleanup window (SU-006)** — Recommended starting value: 30 days. Must be confirmed and configurable. *Impact: Low.*
7. **Scheduled Process cadence confirmation** — Recommended minimum: at least every 12 hours. Final value is a deployment decision. *Impact: Medium.*
8. **Chart rendering library** — Blocks: chart delivery latency estimate; image size constraints; AD-6 two-phase feasibility. *Impact: Medium.*
9. **Timezone handling for MetricActivityStatus (SU-007)** — UTC as default is confirmed in System v0.7. Per-user timezone is a future enhancement. No blocking decision required for v1. *Impact: Low.*
10. **Data Repository concurrent read safety** — Must be confirmed at AU-003 resolution: does the chosen storage technology support concurrent reads from the chart generation coroutine without locks? *Impact: Medium.*
11. **Periodicity prompt expiry timeout (SU-009)** — **Default defined: 24 h** (consistent with SU-001). Must be confirmed and made configurable at implementation. Added to Configuration & Secrets and Scheduled Process cleanup scope. *Impact: Low.*

---

## 14. Traceability Matrix

| Business Goal | Architectural Goal | Component | Key Decision | Risk |
|--------------|-------------------|-----------|-------------|------|
| Reduce tracking abandonment (retention >40%) | AG-1 (≤5 s ack); AG-6 (graceful NLP degradation) | Telegram Gateway; NLP Parsing Engine; Entry Processor; ParseAttempt Manager; **User Session Guard (§4.3 conversation state model — ensures correct routing for periodicity, disambiguation, and confirmation flows)** | AD-1 (monolith); AD-3 (post-commit alert eval); AD-6 (two-phase chart); AD-9 (ParseAttempt atomicity); **AD-11 (metric name uniqueness — prevents fragmentation that would fragment history)** | R-002 (parse failures); R-009 (NLP accuracy); R-014 (ParseAttempt expiry); **SU-009 (periodicity prompt expiry)** |
| Enable self-insight through history | AG-2 (reliable entry storage); AG-4 (measurable metrics) | Data Repository; Chart Generator; Alert Engine; Metric Manager; **Scheduled Process (D-013 retention enforcement)** | AD-4 (lazy MetricActivityStatus + Observability push); AD-5 (repository-layer isolation); AD-6 (two-phase chart); D-013 backup intent (§7.1) | R-002 (immutable wrong entry); R-006 (no export); R-016 (chart failure) |
| User data privacy and trust | AG-3 (user isolation); AG-7 (lifecycle enforcement) | Data Repository; Account Manager; Scheduled Process; Metric Manager (cascade) | AD-5 (repository-layer isolation); **AD-7 (cascade deletion atomicity — single DB transaction)**; **AD-11 (metric name uniqueness — database layer)** | R-005 (cross-user leak — critical); R-007 (raw_input residual); R-017 (raw_input PII); R-018 (open registration) |
| Service continuity | AG-5 (operational simplicity); AG-7 (lifecycle enforcement) | Scheduled Process; Observability Collector; Configuration & Secrets | AD-1 (monolith + process supervisor); **AD-2 (polling/webhook — polling health check default selected)** | R-008 (single operator); R-013 (persistence failure); scheduled process failure; token auth failure |
| Portfolio demonstration (all success metrics at target) | AG-4 (all metrics measurable) | Observability Collector; all components emitting structured events | All ADs — observability is a cross-cutting concern; AD-4 Observability push for `active_users_count` freshness; AD-8 (SU-004 alert-on-Archived resolved); **§4.3 conversation state model (enables `conversation_state_event` for operator visibility into routing behavior)** | R-009 (parse accuracy unmeasurable without observability); R-012 (MetricActivityStatus stale); R-018 (inflated user count) |

---

## Governance Block

### Version
v0.9

### Based On
Business v0.5 + Context v0.7

### Changes Introduced

All changes are in response to mandatory and recommended revisions from `architecture_v0.8_review.md`:

1. **§4.3 NEW — Conversation State Model** (Mandatory Revision 1). Full conversation state machine defined for User Session Guard: Idle, PendingDisambiguation, PendingPeriodicity, PendingMetricDeletionConfirmation, PendingRestorationConfirmation. Named states, entry conditions, routing behaviors, and exit conditions all specified. Message Dispatcher routing rule defined: consult User Session Guard state before intent classification. PendingPeriodicity + PendingDisambiguation collision behavior specified. ConversationState added to §6 Data Strategy as a persisted entity.

2. **Alert Archived state — explicit out-of-scope declaration** (Mandatory Revision 2). Deferred-scope note added after Flow I in §5.2. User-triggered alert archiving and reactivation are explicitly out of scope for v0.9. Rationale provided. Metric Manager component note updated. Alert entity in §6 updated. Alert archiving observability note added to §11.1.

3. **Scheduled Process run-lock mechanism specified** (Mandatory Revision 3). Named approach: `scheduler_lock` record in Data Repository with atomic check-and-set at invocation start, explicit release at invocation end, stale lock handling defined. Updated in §4.1 Scheduled Process, §4.2 Data Repository, Flow E, §8 Bottlenecks, §9 Failure Scenarios. scheduler_lock added to §6 Data Strategy.

4. **Flow C updated — ParseAttempt coordination step** (Mandatory Revision 4). New step 2 in Flow C: Account Manager notifies ParseAttempt Manager to transition any active Pending ParseAttempt to Deferred before PendingDeletion transition completes. No-op if no active ParseAttempt. Coordination failure behavior defined. ParseAttempt Manager Inputs column updated.

5. **Periodicity prompt expiry defined — SU-009** (Mandatory Revision 5). PendingPeriodicity expires after SU-009 (default 24 h). Metric NOT written until periodicity confirmed — no orphaned records on timeout. Scheduled Process cleanup scope updated (step 5 added to Flow E). Flow A updated (steps 4b, 4c). Configuration & Secrets updated. §7.1 NFR row added. §9 failure scenario added.

6. **Flow A expanded — two-step periodicity sub-path** (additional gap). Step 5 from v0.8 expanded into steps 4, 4b, 4c: (a) periodicity prompt + PendingPeriodicity transition, (b) periodicity selection → metric + entry created atomically → Idle, (c) SU-009 timeout cleanup.

7. **Flow I NEW — Compound First-Contact** (additional gap; Q4: full named flow). Full named flow for new users whose first message contains data entry intent. Account Manager → Entry Processor compound interaction modeled. Partial failure semantics defined: registration success + entry failure must surface explicit user error. NLP ambiguous result and new metric periodicity prompt paths within compound flow noted. Recovery: subsequent messages follow Flow A.

8. **AD-2 updated — polling-mode health check option selected** (additional gap). Successful Telegram API poll response selected as polling-mode health proxy. Rationale: confirms both process liveness and API connectivity. Local health file option rejected. §7.1 NFR Mapping updated. §7.2 NFR Unknowns updated.

9. **AD-11 NEW — Metric Name Uniqueness Enforcement Layer** (additional gap). Database-layer unique constraint on `(internal_user_id, metric_name)` selected. Application-layer query-before-insert explicitly rejected (TOCTOU-vulnerable). §6 Data Strategy Metric row updated. §10 Security row added.

10. **Token auth failure behavior defined** (additional gap; Q3: halt after retries). Telegram Gateway retries up to 3 times with exponential backoff; if all retries fail, emits `token_auth_failure_event` and halts. Process supervisor handles restart. §4.1 Telegram Gateway updated. §9 token auth failure row updated. §10 Security token row updated. §13.1 risk added.

11. **AD-9 detection window made configurable** (additional gap). 30-second dangling ParseAttempt detection window extracted to `parse_attempt_dangling_detection_window` configurable parameter (default 30 s). Rationale for default stated. §4.2 Configuration & Secrets updated. Flow B updated. AD-9 updated.

12. **User Session Guard — allowlist check ordering clarified** (additional gap). Allowlist check fires after idempotent InternalUser lookup but before creating a new InternalUser record for first-time non-allowlisted users. §4.1 User Session Guard updated. §10 Security open bot registration row updated.

13. **PendingDeletion alert guarantee made explicit** (additional gap). Structural guarantee documented: no entries stored during PendingDeletion → no alert evaluation trigger generated. This is a structural consequence of User Session Guard routing, not a conditional check in Alert Engine. §4.1 Alert Engine updated. §6 Alert entity updated. §10 Security row added.

14. **`periodicity_prompt_event` added** (additional gap). New event schema in §11.1: dispatched | confirmed | abandoned. Scheduled Process emits "abandoned" on SU-009 timeout cleanup. `scheduled_process_event` schema updated to include `periodicity_states_cleared`. Parse quality and conversation state dashboards updated.

15. **`conversation_state_event` added** (additional gap). New event schema in §11.1 for User Session Guard state transitions. Enables operator visibility into stuck conversation states. Conversation state dashboard added to §11.2.

16. **Compound first-contact partial failure observability** (additional gap). §9 failure scenario added for Flow I partial failure. No dedicated event defined (detectable via co-occurrence of `registration_event` + `error_event`). Noted in §11.1 Traces.

17. **§13.2 Open Questions updated**. SU-009 added with default defined. AD-2 polling health check noted as resolved. Item 11 added.

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|----|----------|-----------|---------|--------|
| AD-1 | Single-process monolith + concurrency note for chart coroutine | ~10-user scale; operational simplicity; chart coroutine is read-only | v0.8 | Confirmed (unchanged) |
| AD-2 | Polling vs. webhook — deferred; **polling-mode health check default selected: successful Telegram API poll response as health proxy** | Successful poll confirms both process liveness and API connectivity; local health file option rejected | v0.9 | Partially resolved — polling health check default selected; final polling vs. webhook choice pending deployment platform |
| AD-3 | Post-commit in-process alert evaluation | Entry storage must not be rolled back on alert failure | v0.8 | Confirmed (unchanged) |
| AD-4 | MetricActivityStatus lazy computation + Observability push on Entry write | Lowest complexity; Observability push maintains `active_users_count` freshness | v0.8 | Confirmed (unchanged) |
| AD-5 | Repository-layer user isolation + testability strategy | Security boundary; miss-one-call vulnerability eliminated | v0.8 | Confirmed (unchanged) |
| AD-6 | Two-phase chart response | Immediate acknowledgment ≤5 s required; chart generation may take up to 30 s | v0.8 | Confirmed (unchanged) |
| AD-7 | Cascade deletion atomicity — single database transaction | Simplest correct approach; soft-delete alternatives rejected due to PII window | v0.8 | Confirmed (unchanged) |
| AD-8 | Alert evaluation suspended for Archived metrics (SU-004 resolution) | Archiving implies dormant tracking; alert configuration preserved for reactivation | v0.8 | Confirmed (unchanged) |
| AD-9 | ParseAttempt + Prompt atomicity via compensating delete; **dangling detection window made configurable (`parse_attempt_dangling_detection_window`, default 30 s)** | 30 s default distinguishes in-progress dispatch from genuine failure; configurable for operational tuning | v0.9 | Confirmed (updated) |
| AD-10 | Async chart execution — post-response fire-and-forget coroutine | Minimum viable async implementation; top-level exception handler mandatory | v0.8 | Confirmed (unchanged) |
| AD-11 | Metric name uniqueness — database-layer unique constraint on `(internal_user_id, metric_name)` | Application-layer query-before-insert is TOCTOU-vulnerable; database constraint is atomically safe; parallels AD-5 | v0.9 | Confirmed (new) |

### Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|----|------|-------------|--------|-----------------|
| AU-001 | Architecture | NLP library/service not chosen — affects in-process vs. external decision and entry ack latency budget | High | Evaluate candidate NLP libraries early; benchmark latency before committing |
| AU-002 | Architecture | Deployment platform not specified — affects polling vs. webhook (AD-2), process supervisor, scheduled process implementation | Medium | Determine before implementation begins |
| AU-003 | Architecture | Data Repository technology not chosen — affects transaction semantics (AD-7), unique constraints (AD-5, AD-11), concurrent read safety (AD-10), backup tooling | High | Choose before any implementation of flows with atomicity requirements |
| SU-001 | System (carried) | ParseAttempt expiry timeout — recommended 24 h | Medium | Confirm at implementation; make configurable |
| SU-002 | System (carried) | NLP confidence threshold — undefined | High | Define at NLP library/service selection time |
| SU-006 | System (carried) | Stale Deferred ParseAttempt cleanup window — recommended 30 days | Low | Confirm at implementation; make configurable |
| SU-007 | System (carried) | Timezone handling — UTC default confirmed; per-user timezone deferred | Low | No action required for v1 |
| SU-008 | Business (carried) | raw_input GDPR classification not formally assessed | Medium | Accept for portfolio scope; review before scaling |
| SU-009 | System (new) | Periodicity prompt expiry timeout — **default defined: 24 h** (consistent with SU-001). Configurable parameter in Configuration & Secrets. Scheduled Process cleans up stale PendingPeriodicity states at each invocation. | Low | Confirm at implementation; make configurable |
