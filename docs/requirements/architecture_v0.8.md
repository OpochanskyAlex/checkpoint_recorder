# Architecture Overview

> **Version:** v0.8
> **Status:** Revised — addresses all mandatory revisions from architecture_v0.7_review.md
> **Date:** 2026-04-05
> **Previous Version:** v0.7 (architecture_v0.7.md, internally versioned v0.1)

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

The primary interaction pattern is **synchronous request/response** driven by incoming Telegram messages. A single asynchronous concern — alert evaluation after entry storage — is modelled as a **post-commit event** within the same process. A **scheduled process** handles all time-triggered responsibilities: retention enforcement, PendingDeletion purge, and stale ParseAttempt cleanup.

Chart generation is the only flow that uses a background execution path: an immediate acknowledgment is sent to the user, and chart image delivery is completed by a post-response fire-and-forget coroutine. No shared mutable state is written during chart generation — the coroutine is a read-only data access plus outbound delivery operation. Data Repository access during chart generation is treated as a concurrent read, which is assumed safe under the chosen storage technology (see AD-7 and concurrency note in AD-1).

The Telegram Bot API is the sole external communication channel (both inbound and outbound), and there is no alternative fallback channel.

---

## 4. Component Model

### 4.1 Core Components

| Component | Responsibility | Inputs | Outputs | Key Risks |
|-----------|---------------|--------|---------|-----------|
| **Telegram Gateway** | Receives all inbound messages from Telegram Bot API; dispatches all outbound messages (text and images) to users | Telegram Bot API (polling or webhook); outbound message payloads from other components | Normalized inbound message events (user ID, message text, timestamp) to the Message Dispatcher; delivered responses to users | Telegram API unavailability halts all I/O; rate limits under unexpected load (R-004, R-019) |
| **Message Dispatcher** | Classifies inbound messages by intent (data entry, command, disambiguation response, periodicity selection, alert re-arm, account deletion, late categorisation view, metric archival/reactivation, etc.) and routes to the responsible handler component | Normalized inbound message events | Routed calls to Entry Processor, ParseAttempt Manager, Metric Manager, Account Manager, Alert Engine, or Chart Generator | Mis-classification silently routes a data entry to a command handler or vice versa; edge cases in classification create dead-end user states |
| **User Session Guard** | Checks the InternalUser account status before any handler is invoked (Active / PendingDeletion / Deleted); enforces the one-active-ParseAttempt-per-user constraint; provides a uniform access point for per-user conversation state; contains a placeholder access-control check point for future allowlist enforcement (R-018) | Inbound message event + internal_user_id | Account status decision (allow / block with message / redirect to restoration flow); current ParseAttempt state for the user | Incorrect state read under concurrent messages from the same user (race to create duplicate InternalUser records — §8.3, System v0.7) |
| **Entry Processor** | Orchestrates the data entry flow: invokes NLP Engine, determines auto-create vs. existing metric, manages periodicity prompt, writes the Entry record, triggers alert evaluation, dispatches confirmation | Parsed message intent from Dispatcher; NLP result from NLP Engine; Data Repository; Alert Engine | Stored Entry record; confirmation message to user; alert evaluation trigger; parse outcome event to Observability Collector | Entry immutability means a silently incorrect auto-parse permanently pollutes the time series (R-002); periodicity prompt non-completion leaves entry unstored without error (SD-002) |
| **NLP Parsing Engine** | Accepts raw free-text; returns (metric_name, values, dimension_assignments, confidence_score); does not make storage decisions | Raw free-text string; user's existing metric name vocabulary (from Data Repository) | Structured parse result: metric_name (string), value(s) (numeric), dimension_assignments (map), confidence (float), outcome (auto-parse / ambiguous / unrecognized) | Confidence threshold is undefined (SU-002); too low → incorrect auto-parses; too high → excessive ParseAttempts; NLP library / service choice is deferred |
| **ParseAttempt Manager** | Creates, updates, and resolves ParseAttempt records; manages Pending → Resolved / Deferred / Expired transitions; enforces one-active-ParseAttempt-per-user constraint; delivers disambiguation prompts; **owns the atomicity compensation for ParseAttempt + Prompt creation** (see AD-9); supports late categorisation (Flow G) | NLP Engine outcome (ambiguous); user disambiguation selection; expiry events from Scheduler; user late-categorisation commands | ParseAttempt records in Data Repository; disambiguation prompt to Telegram Gateway; late categorisation list to user; late categorisation trigger to Entry Processor; deferral / expiry events to Observability Collector | Dangling Pending ParseAttempt with no dispatched prompt is a consistency failure (§8.3, System v0.7); Deferred entries accumulate without a cleanup policy (SU-006) |
| **Alert Engine** | Post-entry: evaluates all Active alerts for the metric against the new entry value; transitions Triggered alerts to Triggered state; dispatches notification with single retry; logs evaluation result. **Behavioral constraint: alert evaluation is suspended when Metric.status = Archived (AD-8)** | New Entry record (post-storage); Alert records from Data Repository; Telegram Gateway | Alert status update in Data Repository; alert notification to Telegram Gateway; alert evaluation event to Observability Collector | Alert evaluation failure must not roll back the entry (§8.3, System v0.7); notification dispatch failure leaves the alert Triggered but the user uninformed (R-011); conversation state collision with active ParseAttempt session (§11.5, System v0.7) |
| **Chart Generator** | Retrieves entry history for a metric; generates a time-series chart image; delivers to user via Telegram Gateway in a fire-and-forget post-response coroutine | Chart request (metric_id, optional time range); Data Repository (read-only) | Chart image → Telegram Gateway; chart invocation event + chart delivery outcome event to Observability Collector; error message as second Telegram message if rendering or delivery fails | No text-summary fallback if rendering fails (R-016); large time ranges may produce oversized images failing Telegram delivery; background coroutine crash after acknowledgment sent leaves user with no chart and no error (see §9 and AD-10) |
| **Metric Manager** | Handles explicit metric creation (Flow 7), metric listing (Flow 8), metric archival and reactivation (Flow H), and individual metric deletion (Flow 11) with cascade atomicity (AD-7); manages MetricActivityStatus computation; enforces SU-004 behavioral default (archival suspends alert evaluation) | User commands; Data Repository | Metric records; MetricActivityStatus (lazy computed on read — see AD-4); cascade deletion confirmation events; metric archival/reactivation state transitions; Observability events | Cascade atomicity failure leaves orphaned Entries or Alerts (R-005 data isolation impact); near-duplicate metric names not detectable under exact-match deduplication (R-003, SU-003) |
| **Account Manager** | Handles user onboarding (Flow 1) including idempotent registration; account deletion request (Flow 10); account restoration within the 3-day grace period (Flow F); onboarding message composition (retention policy, no-export notice, raw_input storage notice, one-shot alert notice). **Re-registration of a Deleted user is treated as a new onboarding (Flow 1) — no reactivation of the Deleted record** | First-contact trigger; deletion / restoration commands; Data Repository | InternalUser records; onboarding message; PendingDeletion state transition; Active state restoration; registration events to Observability Collector | Concurrent first messages racing to create duplicate InternalUser records (§8.3 idempotency requirement); compound first-contact flow partial failure must not silently lose entry intent (R-015); Deleted user re-registration must never reactivate the deleted record (must create fresh) |
| **Scheduled Process** | Time-triggered (recommended cadence: at least every 12 hours — see §7.1): purges accounts where PendingDeletion grace period has elapsed (3-day, SD-004); cleans up stale Deferred ParseAttempts beyond the cleanup window (SU-006); enforces 1-year retention guarantee (D-013). **Must be idempotent and must prevent concurrent overlap via a run-lock mechanism** | Scheduled time triggers; Data Repository | Permanent purge of eligible user data (atomic per user — AD-7); cleanup of stale ParseAttempts; `scheduler_heartbeat` and execution result events to Observability Collector | Process failure leaves PendingDeletion accounts in limbo (D-013 obligation unmet); partial purge is a data integrity failure — process must be idempotent and resumable (§8.3, System v0.7); concurrent overlap causes race conditions on cascade deletions (§9) |

### 4.2 Supporting Components

| Component | Responsibility | Notes |
|-----------|---------------|-------|
| **Data Repository** | Durable storage of all system entities (InternalUser, Metric, Entry, Alert, ParseAttempt, MetricActivityStatus); enforces per-user data isolation at the storage layer; provides transactional semantics for atomic cascade deletions and idempotent writes; supports concurrent reads for chart generation background coroutine | Per-user isolation enforced at the repository layer — not at the application filtering layer. This is a security boundary, not a convenience abstraction (AD-5). Technology choice deferred. Concurrent read access during chart generation is the only multi-threaded access pattern and is treated as a shared-nothing read operation. |
| **Observability Collector** | Captures structured event records for all five business success metrics and operational health signals; the sole means by which success metrics are computable (§7, System v0.7). **Failure contract: event emission is fire-and-forget; if the collector is unavailable, the component logs to stderr/local log and continues — metric coverage gap becomes operator-visible via absent events (AD-10 failure contract note).** Emits a `observability_collector_health` heartbeat to enable self-health monitoring | Structured log events (not free-text). All components emit to this collector. Technology choice deferred. Raw_input must not appear in any event field — enforcement is structural: event schemas reference only IDs (user_id, metric_id, entry_id), never free-text content. |
| **Configuration & Secrets** | Manages the Telegram Bot API token, scheduled process intervals, ParseAttempt expiry timeout (SU-001), NLP confidence threshold (SU-002), ParseAttempt stale cleanup window (SU-006), scheduled process cadence | Telegram Bot API token must never appear in source code or logs. Its storage and rotation are the Bot Operator's responsibility. System reads it from environment at startup. Token rotation is a redeploy-with-new-env-var operation; no downtime is expected. A token authentication failure at startup or during operation emits a specific `token_auth_failure_event` to the Observability Collector. |

---

## 5. Interaction Model

### 5.1 Interaction Patterns

| Pattern | Where Applied | Rationale |
|---------|--------------|-----------|
| **Synchronous Request/Response** | All user-triggered flows (entry, disambiguation, chart request, metric management, account management, late categorisation, archival/reactivation, restoration) | Telegram is a message-driven interface; users expect a response to each message; portfolio scale makes async complexity unjustified |
| **Post-Commit Event (in-process)** | Alert evaluation after Entry storage (Flow 2, step 5; Flow 3a, step 5) | Alert evaluation must not block or roll back entry storage; it is a downstream consequence, not a transactional requirement |
| **Post-Response Fire-and-Forget Coroutine** | Chart generation and delivery (Flow D — chart) | Immediate acknowledgment ≤5 s is required; chart generation may take up to 30 s; no shared mutable state is written during chart generation |
| **Scheduled / Batch** | Scheduled Process: PendingDeletion purge, retention enforcement, stale ParseAttempt cleanup | These are time-triggered, not user-triggered; decoupled from the request/response path |

### 5.2 Key Flows

---

#### Flow A: Standard Data Entry

- **Trigger:** Registered user sends a free-text message parseable with sufficient confidence
- **Steps:**
  1. Telegram Gateway → Message Dispatcher (classify as data entry intent)
  2. Dispatcher → User Session Guard (confirm Active account; check no blocking ParseAttempt)
  3. Dispatcher → Entry Processor
  4. Entry Processor → NLP Parsing Engine (parse free-text → metric_name, values, confidence)
  5. NLP result: auto-parse confidence sufficient → Entry Processor → Data Repository (metric lookup or auto-create with periodicity prompt → Entry record write)
  6. Entry Processor → Alert Engine (post-storage trigger — not transactionally coupled)
  7. Alert Engine → Data Repository (evaluate Active alerts for metric; skip evaluation if Metric.status = Archived — AD-8) → optionally → Telegram Gateway (notification dispatch)
  8. Entry Processor → Observability Collector (parse success event, entry_id); fire-and-forget
  9. Entry Processor → Telegram Gateway (confirmation message)
- **Failure Points:**
  - Step 5: Data Repository write failure → user notified to re-submit; no confirmation sent; entry not stored (AG-2)
  - Step 6: Alert evaluation failure → entry preserved; failure logged; alert evaluation event marked failed
  - Step 9: Confirmation dispatch failure → entry is preserved; user may not receive confirmation (§8.3)
- **Recovery:** Entry storage failure is surfaced to the user immediately. Alert evaluation failure is operator-visible via Observability Collector.

---

#### Flow B: Ambiguous Entry (ParseAttempt Lifecycle)

- **Trigger:** Free-text message cannot be auto-parsed with sufficient confidence
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (check no existing Pending ParseAttempt)
  2. If existing Pending ParseAttempt: User Session Guard → Telegram Gateway (ask user to resolve/defer existing first)
  3. If no existing Pending ParseAttempt: Dispatcher → ParseAttempt Manager
  4. ParseAttempt Manager → Data Repository (create ParseAttempt record, status = Pending) — **atomicity compensation owned by ParseAttempt Manager (AD-9):**
     - On successful record creation: immediately attempt prompt dispatch (step 5)
     - On prompt dispatch failure: ParseAttempt Manager → Data Repository (delete the ParseAttempt record); return error to user — no dangling Pending record
     - On ParseAttempt creation failure: return error to user immediately; no cleanup needed
  5. ParseAttempt Manager → Telegram Gateway (disambiguation prompt with candidate metrics)
  6. ParseAttempt Manager → Observability Collector (ambiguous parse event); fire-and-forget
  7. [Later] User responds → Dispatcher → ParseAttempt Manager → resolves to Entry Processor (as Flow A from step 5)
  8. OR: [Expiry] Scheduled Process / internal timer → ParseAttempt Manager → Data Repository (status = Deferred); Observability event
- **Failure Points:**
  - Step 4 (prompt dispatch fails after record creation): ParseAttempt Manager deletes the record and returns an error to the user. If deletion also fails, operator must manually clear the dangling record (detected via Observability Collector: `parse_attempt_event` with status=Pending and no subsequent `prompt_dispatched` event within 30 s).
  - Expiry timeout value (SU-001) not yet defined — 24 h is the recommended starting point
- **Recovery:** Deferred ParseAttempts are not failures; they are resting states. Late categorisation is supported (Flow G). Cleanup window governs eventual discard (SU-006).

---

#### Flow C: Account Deletion with Grace Period

- **Trigger:** User sends account deletion request
- **Steps:**
  1. Telegram Gateway → Dispatcher → Account Manager
  2. Account Manager → Data Repository (set InternalUser.status = PendingDeletion, record deletion_scheduled_timestamp = now + 3 days)
  3. Account Manager → Telegram Gateway (3-day notice message — SD-004)
  4. Account Manager → Observability Collector (deletion scheduled event); fire-and-forget
  5. [3 days later] Scheduled Process → Data Repository (identify accounts past deletion_scheduled_timestamp with status = PendingDeletion → atomic purge of all user data — AD-7)
  6. Scheduled Process → Observability Collector (purge completion event, including per-user cascade counts)
- **Failure Points:**
  - Step 5: Scheduled Process failure → PendingDeletion accounts linger; deletion commitment unmet (D-013); operator must investigate via Observability Collector
  - Step 5: Partial purge → data integrity failure; process must be idempotent and resumable (§8.3)
- **Recovery:** Scheduled Process must be designed to resume partial purges safely. Operator alert if the `scheduler_heartbeat` event has been absent for longer than two scheduled intervals.

---

#### Flow D: Alert Notification During Active ParseAttempt

- **Trigger:** New Entry stored for a user who has an active Pending ParseAttempt; an Active alert for that metric's threshold is crossed
- **Steps:**
  1. Alert Engine evaluates alert condition → condition met → dispatch notification
  2. Alert Engine → Telegram Gateway (alert notification formatted as a distinct block — "Alert fired:" header, no selectable options)
  3. ParseAttempt Manager still holds the active Pending ParseAttempt → disambiguation prompt is still the active user-facing request
- **Failure Points:**
  - User may confuse the alert notification for a disambiguation option (§11.5, System v0.7)
- **Recovery:** Formatting distinction is the sole mitigation. This is an accepted residual UX risk at portfolio scope.

---

#### Flow E: Scheduled Retention & Cleanup

- **Trigger:** Scheduled time trigger (recommended cadence: at least every 12 hours — see §7.1)
- **Pre-condition:** Run-lock check — if a prior instance is still running, new invocation aborts and emits a `scheduler_overlap_event` to Observability Collector
- **Steps:**
  1. Scheduled Process → Observability Collector (`scheduler_heartbeat` event — emitted at start of every invocation, before any work)
  2. Scheduled Process → Data Repository: identify InternalUsers with last_interaction_timestamp > 1 year ago (D-013 retention enforcement) → atomic purge per user
  3. Scheduled Process → Data Repository: identify PendingDeletion accounts past deletion_scheduled_timestamp → atomic purge (AD-7)
  4. Scheduled Process → Data Repository: identify Deferred ParseAttempts past stale cleanup window (SU-006) → transition to Expired
  5. Scheduled Process → Observability Collector (`scheduler_run_completed` or `scheduler_run_failed` event with per-step counts and any errors)
- **Failure Points:**
  - Process not running: all three retention obligations are unmet; operator must monitor `scheduler_heartbeat` absence (distinct from `scheduler_run_completed` — heartbeat is emitted even if work steps fail)
  - Partial execution: idempotency required at each step; each step independently resumable
  - Concurrent overlap: run-lock prevents; if lock acquisition fails, `scheduler_overlap_event` emitted

---

#### Flow F: Account Restoration (Within Grace Period)

> Source: System v0.7 Flow 10a

- **Trigger:** User sends any message or explicit restore command while InternalUser.account_status = PendingDeletion
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (detects PendingDeletion status)
  2. User Session Guard → Account Manager (route to restoration handler)
  3. Account Manager → Telegram Gateway (informs user that their account is scheduled for deletion; asks for explicit restoration confirmation)
  4. User confirms restoration:
     - Account Manager → Data Repository (set InternalUser.status = Active; clear deletion_scheduled_timestamp)
     - Account Manager → Telegram Gateway (confirmation: account fully restored, all data preserved)
     - Account Manager → Observability Collector (`account_lifecycle_event`: account_restored); fire-and-forget
  5. If user does not confirm (sends any other message or does not respond): Account Manager → Telegram Gateway (informs user that the account remains pending deletion; no state change)
- **Failure Points:**
  - Data Repository write failure during restoration: Account Manager returns an error to the user; the account remains in PendingDeletion — no data is lost
  - Restoration requested after the 3-day window has elapsed and the purge has already executed: the Deleted user is treated as a new registration (Flow 1) — restoration is impossible
- **Recovery:** Restoration failure leaves the account in PendingDeletion (safe resting state). The Scheduled Process will execute the purge on schedule regardless.

---

#### Flow G: ParseAttempt Late Categorisation

> Source: System v0.7 Flow 3b (late categorisation subprocess)

- **Trigger:** User explicitly requests a view of their Deferred ParseAttempts
- **Steps:**
  1. Telegram Gateway → Dispatcher → User Session Guard (confirm Active account)
  2. Dispatcher → ParseAttempt Manager (late categorisation view request)
  3. ParseAttempt Manager → Data Repository (retrieve all Deferred ParseAttempts for the user)
  4. ParseAttempt Manager → Telegram Gateway (present list of Deferred ParseAttempts with retained raw_input and original message timestamp)
  5. For each Deferred ParseAttempt, user may choose:
     - **(a) Categorise:** User selects a metric → ParseAttempt Manager → Entry Processor (create Entry with entry_timestamp = original message timestamp, stored_timestamp = now) → Entry created; ParseAttempt transitions to Resolved; alert evaluation proceeds (Flow A from step 6)
     - **(b) Discard:** User discards the ParseAttempt → ParseAttempt Manager → Data Repository (status = Expired; raw_input purged) → Observability Collector (`parse_attempt_event`: parse_attempt_expired via user discard)
  6. ParseAttempt Manager → Observability Collector (late categorisation outcome event per item — resolved or expired); fire-and-forget
- **Failure Points:**
  - No Deferred ParseAttempts exist: ParseAttempt Manager → Telegram Gateway (informs user; no error)
  - Entry creation fails during categorisation (step 5a): ParseAttempt Manager returns an error to the user; the ParseAttempt remains in Deferred — user may retry
  - If the associated metric was deleted (Flow 11 cascade) before the user returns: the ParseAttempt will already be in Expired state; it will not appear in the Deferred list
- **Recovery:** Late categorisation is non-destructive until the user confirms discard or Entry creation succeeds. Deferred ParseAttempts remain available until explicitly resolved, discarded, or auto-expired by the Scheduled Process (SU-006).

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
- **Recovery:** Both archival and reactivation are clean state transitions with no cascade effects (archive does not delete or alter associated Entries, Alerts, or ParseAttempts).

---

## 6. Data Strategy (Conceptual)

| Entity / Domain Data | Owner Component | Consistency Needs | Lifecycle | Risks |
|---------------------|----------------|------------------|-----------|-------|
| InternalUser | Account Manager (write) / User Session Guard (read) / Data Repository (store) | Strong consistency on creation (idempotent, no duplicates — §8.3). **Re-registration after Deleted status creates a new record — never reactivates the deleted one** | Active → PendingDeletion → Deleted (terminal); purged by Scheduled Process | Concurrent first-message race creating duplicate records (§8.3); Deleted users who re-register must start fresh with a new InternalUser record |
| Metric | Metric Manager / Entry Processor (auto-create) | Consistent name-uniqueness per user; dimension_names immutable after first entry | Active ↔ Archived (bidirectional); Active or Archived → Deleted (cascade from metric deletion or account deletion) | Near-duplicate names fragment history (R-003); dimension naming locked after first compound entry |
| Entry | Entry Processor / Data Repository | Immutable after storage; entry_timestamp must preserve original message time even for late-categorised entries (entry_timestamp ≠ stored_timestamp for Flow G) | Stored → Deleted (cascade from metric or account deletion only) | Incorrect auto-parse permanently pollutes time series (R-002); raw_input is residual personal data (R-017) |
| Alert | Alert Engine / Metric Manager | Status transitions must be atomic; re-arm resets status to Active; **evaluation suspended when parent Metric.status = Archived (AD-8)** | Active → Triggered → Active (re-arm) | Archived ↔ Active | Deleted (cascade) | One-shot behavior: Triggered alert never fires again without explicit user re-arm (SD-003); alert on undefined dimension rejected (Flow 6, step 3) |
| ParseAttempt | ParseAttempt Manager | Consistent with one-active-per-user constraint; **creation and prompt dispatch atomically compensated (AD-9)** | Pending → Resolved (terminal) | Pending → Deferred → Expired (terminal) | Dangling Pending without dispatched prompt is a consistency failure (§8.3); resolved via AD-9 compensating delete |
| MetricActivityStatus | Metric Manager (lazy compute on read — AD-4) | Eventually consistent; computed from Entry history on demand; **`active_users_count` for Observability Collector pushed on each Entry write (see §11.1 freshness mechanism)** | Derived — recomputed; no separate lifecycle | Stale if computation is triggered at wrong time relative to timezone boundaries (SU-007) |
| raw_input (on Entry and ParseAttempt) | Data Repository | Retained as part of parent record | Purged atomically on account deletion (Flow 10) and metric deletion (Flow 11) | Residual personal data risk (R-017); no scrubbing at portfolio scope (SD-005); user informed at onboarding |

---

## 7. Non-Functional Requirements Coverage

### 7.1 NFR Mapping

| NFR Category | Requirement | Architectural Tactic | Trade-off |
|-------------|-------------|---------------------|-----------|
| Performance — Entry ack | ≤ 5 s end-to-end (§8.1, System v0.7) | NLP Engine is in-process (no network round-trip to external NLP service preferred); Data Repository on same host or low-latency connection | In-process NLP limits language model complexity; larger models may require an external service adding latency |
| Performance — Chart ack | ≤ 5 s acknowledgment; ≤ 30 s full delivery | Two-phase response: immediate acknowledgment via Telegram Gateway; chart generation in post-response fire-and-forget coroutine (AD-6, AD-10); deliver when ready | Adds implementation complexity for the two-phase pattern; simplest single-threaded alternative risks Telegram "bot not responding" perception |
| Performance — Alert dispatch | ≤ 60 s from entry storage to notification | Post-commit in-process evaluation; no queue needed at 10-user scale | If evaluation blocks for any reason, the 60 s budget is consumed; at scale this would require a queue |
| Availability | ≥ 95% monthly uptime (§8.2, System v0.7) | Single-instance deployment with process supervisor / container restart-on-failure; **health check contract: a `/health` endpoint (or equivalent polling-mode heartbeat signal) returns `{status: "ok", uptime_s: <seconds>}` on success; called by the process supervisor at configurable intervals; failure triggers restart** | Single point of failure for the process; no hot standby at portfolio scale; operator accepts downtime risk (R-008) |
| Scale ceiling | ≤ 20 concurrent users without architecture review | Monolithic design with internal concurrency handling; explicit ceiling documented | Exceeding ceiling requires architecture review — no graceful degradation designed beyond this point |
| Atomicity — Registration | Idempotent; no duplicate InternalUser records | Upsert or unique-constraint-on-Telegram-ID at Data Repository layer | Requires database-level uniqueness enforcement, not application-level deduplication |
| Atomicity — Cascade deletion | Atomic per user (account) and per metric (metric deletion) — **AD-7** | Single database transaction spanning all related entities; explicit choice over alternatives (see AD-7) | Transaction scope increases with data volume; at ~100 time series, this is not a concern |
| Atomicity — ParseAttempt + Prompt | ParseAttempt creation and prompt dispatch treated as a unit — **AD-9** | ParseAttempt Manager owns compensating delete: if prompt dispatch fails, ParseAttempt record is deleted before returning error to user | Compensating delete adds a second write on the failure path; if the compensating delete also fails, operator must clear the record manually (detectable via Observability) |
| Reliability — Backup / RPO | D-013 (1-year retention guarantee) requires data to survive a Data Repository failure | **Architectural intent: periodic serialized export of the Data Repository to durable, separate storage at a cadence ≤ half the RTO target. At portfolio scale, a daily file export to operator-controlled durable storage is the minimum acceptable approach.** RTO and RPO are informal at this scale: RPO ≤ 24 h (max data loss = last 24 h of entries), RTO ≤ 4 h (operator manually restores from latest export). Final frequency and tooling are deployment decisions, not architecture decisions — but the mechanism must be in place before first deployment. | A daily export is simple but means up to 24 h of data is unrecoverable. Acceptable for a 10-user portfolio system. For higher-value data, WAL streaming or continuous replication would be required. |
| Reliability — Scheduled Process cadence | Worst-case delay between PendingDeletion grace expiry and actual purge must be predictable | **Recommended minimum cadence: at least every 12 hours.** Worst-case purge delay = one scheduled interval (≤12 h) beyond the 3-day grace period. This must be communicated to users as "your account will be deleted within 3 days" — not "at exactly 72 hours" | Cadence is configurable; operator may set it more frequently. Daily cadence would give a worst-case 24 h overhang, which may be acceptable depending on deployment context. |
| Reliability — Observability Collector failure | Event emission must not fail silently or block main flows | **Fire-and-forget contract: if Observability Collector is unavailable, each component logs the event to stderr/local log and continues processing. Metric coverage gap becomes visible to the operator via absent events in the dashboard.** A separate `observability_collector_health` heartbeat enables detection of collector-down state (§11.1). | Fire-and-forget means individual events may be lost during collector downtime. This is acceptable for a portfolio system. Blocking on collector availability would convert an observability failure into a user-facing failure. |
| Concurrency — Monolith chart thread model | The two-phase chart coroutine runs concurrently with the main request-handling loop within the single process | **Chart generation coroutine is read-only relative to the Data Repository — it reads entry history and generates an image. It does not write to the Data Repository. User Session Guard state and ParseAttempt state are not accessed during chart generation. Therefore, the only shared resource is the Data Repository read path, which is assumed to support concurrent reads under the chosen storage technology (see AU-003).** | If the storage technology does not support concurrent reads safely, chart generation must be serialized (post all pending writes complete). This should be confirmed at Data Repository technology selection. |
| Security — Token | Bot API token must never appear in logs or source | Environment variable injection at startup; never logged, never in source code; rotation is operator responsibility | Operator-side risk accepted (§8.4, System v0.7) |
| Security — User isolation | Per-user data isolation 100% non-negotiable | Isolation enforced at the Data Repository layer (all queries parameterized by internal_user_id) — not at the application filtering layer (AD-5) | Application-layer filtering creates a miss-one-call vulnerability; repository-layer enforcement is the safer default |
| Observability | All five success metrics must be computable | Structured event emission from every component to Observability Collector; no free-text log-parsing required; fire-and-forget with local fallback | Adds an event-emission call to every significant code path; failure is gracefully degraded (local log fallback) |

### 7.2 NFR Unknowns

| Missing NFR | Decision Blocked |
|-------------|-----------------|
| **Deployment platform constraints** | Blocks: choice of Telegram polling vs. webhook (webhook requires a public HTTPS endpoint); process supervisor technology; scheduled process implementation (cron vs. in-process scheduler). **Note: if polling is chosen (no public HTTPS endpoint), the health check contract from §7.1 must use an internal polling-mode heartbeat mechanism rather than an external HTTP endpoint, since no public endpoint exists.** |
| **NLP parsing library or service** | Blocks: performance estimate for entry ack latency; whether in-process NLP is viable or an external service call is required; affects AD-1 (monolith) trade-off |
| **Chart rendering library** | Blocks: chart delivery latency estimate; image size constraints (Telegram file size limits); AD-6 two-phase feasibility confirmation |
| **ParseAttempt expiry timeout value (SU-001)** | Blocks: Scheduled Process configuration; user-facing disambiguation session UX. Recommended starting point: 24 hours |
| **NLP confidence threshold (SU-002)** | Blocks: ParseAttempt creation rate; directly impacts the 85% parse success target |
| **Stale Deferred ParseAttempt cleanup window (SU-006)** | Blocks: Scheduled Process configuration; storage growth estimate. Recommended starting point: 30 days |
| **Data Repository technology (AU-003)** | Blocks: transaction semantics for cascade deletion atomicity (AD-7); unique-constraint-on-Telegram-ID implementation (AD-5); concurrent read safety for chart generation coroutine; backup tooling |

---

## 8. Scalability & Performance Reasoning

**Expected load assumptions:**
- ~10 registered users; up to 20 concurrent users before architecture review
- ~100 active metric time series at steady state
- Entry frequency: estimated 1–5 entries per user per day = ≤ 100 entries/day total across all users
- Chart requests: occasional, non-real-time
- Alert evaluations: triggered per entry; at ≤100 entries/day, total evaluations are trivial

**Bottlenecks:**

| Bottleneck | Component | Mitigation |
|-----------|-----------|-----------|
| NLP parsing latency | NLP Parsing Engine | Keep NLP in-process if library-based; if an external service is required, its latency directly consumes the 5 s entry ack budget |
| Chart generation latency | Chart Generator | Two-phase response (immediate ack + post-response fire-and-forget coroutine) prevents timeout perception; rendering budget is 25 s of the 30 s total |
| Telegram Bot API rate limits | Telegram Gateway | At 10-user scale, rate limits are not a practical concern; would become relevant if bot is made public (R-019) |
| Cascade deletion transaction size | Data Repository | At ~100 time series per user, transaction scope is small; not a performance concern at current scale |
| Scheduled Process overlap | Scheduled Process | Run-lock prevents concurrent invocations; `scheduler_overlap_event` emitted if overlap attempted |

**Caching boundaries (conceptual):**
- User account status and active ParseAttempt state may be cached in-process per request to avoid redundant Data Repository reads within a single message-handling cycle
- MetricActivityStatus is computed lazily on read (AD-4) — no pre-computation cache needed at this scale
- Metric name vocabulary (for NLP matching) may be cached in-process and invalidated on metric creation/deletion

**Queueing needs (conceptual):**
- None required at portfolio scale
- Alert evaluation is post-commit in-process; no queue needed
- If scale exceeds the ceiling, alert evaluation should be moved to a work queue to decouple it from the entry storage path

---

## 9. Reliability & Failure Scenarios

| Scenario | Impact | Detection | Mitigation | Residual Risk |
|----------|--------|-----------|------------|---------------|
| Telegram API unavailable | All I/O halted; no messages received or sent; bot appears offline to users | Telegram Gateway fails to connect; `bot_health` signal absent from Observability Collector | Process supervisor keeps bot process alive; bot resumes polling / reconnects when API recovers; operator alert via Observability | No fallback channel; users cannot log entries during outage |
| Data Repository unavailable | Entry storage fails; all flows fail at the persistence step; user receives error and is asked to re-submit | Entry Processor / Repository calls throw errors; Observability Collector logs storage failure events | Operator alert via Observability; user is explicitly notified to re-submit | Data entered during outage is lost unless user re-submits; no in-memory buffer defined at portfolio scale |
| Data Repository partial outage (read available, write unavailable) | Reads (chart, metric listing) succeed; writes (entry storage, alert state update) fail | Write failures logged via Observability | Same as above for writes; read-only operations continue unaffected | Same as above |
| NLP Parsing Engine failure | All free-text entries route to ParseAttempt; parse success rate drops to 0%; 85% target unachievable | Parse failure rate spike visible in Observability Collector | ParseAttempt flow provides manual fallback; operator alert if parse success rate falls below target | User experience degrades significantly; all entries require manual disambiguation |
| Alert Engine failure (post-commit) | Alert notifications not dispatched; alert accuracy target (>95%) threatened | Alert evaluation failure events in Observability Collector | Single retry on notification dispatch (§5 Flow 5, System v0.7); entry is preserved regardless | Silent alert failures after retry exhaustion; operator visibility only |
| **Alert notification dispatch failure after retry exhausted** | Alert is in Triggered state permanently; user receives no notification | `alert_evaluation_event` with `dispatch_outcome: "failed_after_retry"` — a distinct event value from "failed" (first attempt) vs. "failed_after_retry" (retry also failed) | Operator-visible via Observability; alert remains Triggered — user may still re-arm; no automated notification recovery at portfolio scale | User misses threshold notification without knowing it; operator alert is the only detection mechanism |
| Chart Generator failure (first phase — acknowledgment) | Chart ack fails; user does not receive even the "generating..." message | Error response to user; chart failure events in Observability Collector | User receives explicit error message; no text-summary fallback (accepted gap, R-016) | Users cannot access visual history during failure |
| **Chart generation coroutine crash (second phase — after acknowledgment sent)** | User has received "generating..." acknowledgment but will never receive the chart; silent failure | `chart_delivery_failure_event` emitted to Observability Collector by the coroutine's error handler (or by a coroutine supervisor if the coroutine crashes without an error handler) | Coroutine must catch all exceptions; on failure: send an error message to the user as the second Telegram message; emit `chart_delivery_failure_event`; increment `chart_delivery_failure_count` metric | If the coroutine crashes without being caught (unhandled exception), the user receives no chart and no error; this is the residual risk if exception handling is incomplete |
| Scheduled Process failure | PendingDeletion accounts not purged; D-013 retention obligation unmet; stale Deferred ParseAttempts accumulate | Absence of `scheduler_heartbeat` event in Observability Collector (heartbeat is emitted at the start of every invocation, before any work — distinct from `scheduler_run_completed`) | Operator investigation triggered by missing heartbeat; manual re-run required | Deletion commitment unmet during failure window; operator-dependent recovery |
| **Scheduled Process concurrent overlap** | Two invocations running simultaneously could race on cascade deletions, produce duplicate purge events, or create partial-delete collisions | `scheduler_overlap_event` emitted when a new invocation detects an existing run-lock | Run-lock mechanism prevents overlap; new invocation aborts immediately and emits event; operator-visible via Observability | If run-lock is not implemented, concurrent deletions could corrupt data or produce duplicate audit events |
| Concurrent first-message race | Duplicate InternalUser records created for the same Telegram user ID | Duplicate key violation at Data Repository if uniqueness constraint enforced | Repository-level unique constraint on Telegram user ID → idempotent upsert | If uniqueness not enforced at DB layer, cross-user data association risk |
| Cascade deletion partial failure | Some Entries or Alerts survive after metric or account deletion; orphaned data | Purge completion event missing from Observability Collector; mismatch between expected and actual cascade counts | Atomic transaction required (AD-7); process must be idempotent and resumable if interrupted | Data integrity failure if not atomic; residual data may constitute privacy breach (R-005) |
| Alert notification during ParseAttempt session | User confuses alert notification for a disambiguation selection | User provides unexpected input to ParseAttempt Manager | Formatting distinction between alert blocks and selection prompts (§11.5, System v0.7) | Residual UX confusion; accepted at portfolio scope |
| **Observability Collector unavailable** | All structured events are lost; all five business success metrics become uncomputable; operator has no automated signal | Absence of `observability_collector_health` heartbeat in monitoring; all component-level event emission falls back to stderr | Fire-and-forget failure contract: main flows continue; events are written to stderr/local log; operator manually inspects local log to reconstruct metrics | All five business metrics are unmeasurable during outage; operator depends on manual log inspection |
| **Re-registration of a Deleted user** | A Telegram user whose account was purged sends a new message; system must start fresh, not reactivate the Deleted record | Account Manager detects that the Telegram user ID maps to an InternalUser with account_status = Deleted | Account Manager treats the inbound message as a first-contact event (Flow 1); a new InternalUser record is created (new internal_user_id); no data from the deleted account is recovered or accessible | If the uniqueness constraint allows a Deleted record to coexist with a new Active record for the same Telegram user ID, the implementation must explicitly filter by non-Deleted status on lookup — this is a repository-layer correctness requirement |
| ParseAttempt + Prompt atomicity failure | Pending ParseAttempt created but no prompt delivered; user cannot respond; stuck state | `parse_attempt_event` with status=Pending and no subsequent prompt dispatch event within a short window; User Session Guard blocks subsequent messages | ParseAttempt Manager compensating delete: if prompt dispatch fails, delete the ParseAttempt record before returning error to user (AD-9) | If compensating delete also fails, operator must manually clear the dangling record; detectable via Observability |

---

## 10. Security & Compliance Baseline

| Area | Threat / Risk | Control | Notes |
|------|--------------|---------|-------|
| **Telegram Bot API token** | Token exposure → full bot impersonation; all user interactions compromised | Token injected via environment variable at startup; never logged, never in source code; rotation is operator responsibility. **Token rotation procedure: redeploy with new env var; no downtime expected. Token authentication failure emits `token_auth_failure_event` to Observability Collector.** | No in-scope token management infrastructure; operator risk accepted (§8.4, System v0.7) |
| **Per-user data isolation** | Implementation error leaks one user's data to another user | All Data Repository queries parameterized by internal_user_id at the repository layer; never filtered at the application layer (AD-5). **Testability: the repository interface must be designed to support injection of a test-controlled storage backend (e.g., an in-memory implementation with the same interface contract). Integration tests must verify that no query returns data belonging to a different user_id — at minimum, tests must call every repository read operation with a different user_id from the one that owns the data and assert an empty or not-found result.** | 100% non-negotiable target (R-005) |
| **User identity** | Identity linkage between Telegram user and stored data | Only an opaque internal_user_id is stored; Telegram identity fields (name, username, phone) are never persisted (D-007) | Telegram holds identity fields outside this system's control; residual risk accepted (R-007) |
| **raw_input personal data** | Free-text messages may contain personal or special-category data (health metrics, financial data) | User informed at onboarding that message text is stored verbatim; raw_input purged on account and metric deletion; no scrubbing at portfolio scope (SD-005) | Residual personal data risk elevated to Medium (R-017); accepted for portfolio scope |
| **raw_input in Observability events** | Accidental inclusion of raw_input in structured events → PII leakage into logs | **Structural enforcement: all Observability event schemas reference only opaque IDs (internal_user_id, metric_id, entry_id, parse_attempt_id). Free-text fields are structurally absent from the schema. The Observability Collector must reject or sanitize any event that contains a field not in the approved schema — a schema validation gate at the emission boundary.** | Even if logs are forwarded to external systems, PII cannot leak if the schema gate is enforced. Schema must be reviewed before deployment. |
| **Open bot registration** | Any Telegram user can register; user count may exceed the designed cohort | No access control enforced at this stage; acknowledged gap (R-018). **The User Session Guard contains a named placeholder check point for an allowlist gate — when access control is introduced, it is inserted here without changes to other components.** This is the single extension point for future access control. | Risk accepted at current scale; the placeholder check point prevents structural changes when access control is added |
| **Rate limiting** | Message flooding from a single user or public exposure | No rate limiting defined at portfolio scale; risk accepted (R-019) | Must be added before any public release or scaling beyond the designed ceiling |
| **Auditability** | Inability to trace a stored entry back to its source input or detect data integrity failures | raw_input retained on Entry records for audit tracing; Observability Collector captures all significant events; cascade deletion counts logged in `cascade_deletion_event` | Observability Collector is the primary audit tool; its availability is critical |

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
- `active_users_count` — count of users with at least one active metric (business success metric). **Freshness mechanism: this value is pushed to the Observability Collector on every successful Entry write (triggered by Entry Processor after Data Repository commit). At ≤100 entries/day, this is a negligible overhead and ensures the count is current within one entry cycle. MetricActivityStatus lazy computation (AD-4) is query-time accurate; the Observability push path reads the current computed value at write time.**
- `chart_invocation_rate` — chart requests / active users (target > 25%); **counts only successfully delivered charts (uses `chart_delivery_success` event, not `chart_invocation_event`), so that failed deliveries do not inflate the numerator**
- `alert_delivery_accuracy_rate` — alerts correctly fired and dispatched / alerts expected to fire (target > 95%)
- `cross_user_isolation_incidents` — count of cross-user data visibility events (target = 0, non-negotiable). **Detection mechanism: this signal is populated only by integration tests (repository-layer isolation tests — see §10). In production, a violation would only be detectable via user-reported anomalies or audit log review. There is no runtime detection mechanism — this is an accepted gap given that the architectural control (repository-layer isolation, AD-5) makes runtime violations structurally impossible if correctly implemented.**

**Logs (structured):**
- `registration_event` — {event: "user_registered", internal_user_id, timestamp}
- `parse_outcome_event` — {event: "parse_success" | "parse_ambiguous" | "parse_failed", internal_user_id, metric_id (if resolved), confidence_score, entry_id (if stored), timestamp}
- `parse_attempt_event` — {event: "parse_attempt_created" | "parse_attempt_resolved" | "parse_attempt_deferred" | "parse_attempt_expired" | "parse_attempt_late_categorised", parse_attempt_id, internal_user_id, timestamp}
- `alert_evaluation_event` — {event: "alert_evaluated", alert_id, metric_id, internal_user_id, condition_met: bool, dispatch_outcome: "delivered" | "failed" | "retried" | "failed_after_retry", timestamp}
- `chart_invocation_event` — {event: "chart_requested", internal_user_id, metric_id, timestamp}
- `chart_delivery_event` — {event: "chart_delivered" | "chart_delivery_failed", internal_user_id, metric_id, failure_reason (if failed), timestamp}
- `account_lifecycle_event` — {event: "pending_deletion_scheduled" | "account_restored" | "account_purged" | "user_registered_post_deletion", internal_user_id, timestamp}
- `cascade_deletion_event` — {event: "metric_deleted" | "account_purged_cascade", metric_id (if metric deletion), internal_user_id, entry_count_deleted, alert_count_deleted, parse_attempt_count_expired, timestamp}
- `metric_lifecycle_event` — {event: "metric_archived" | "metric_reactivated", internal_user_id, metric_id, timestamp}
- `scheduled_process_event` — {event: "scheduler_run_completed" | "scheduler_run_failed" | "scheduler_overlap_detected", accounts_purged, parse_attempts_cleaned, errors, timestamp}
- **`scheduler_heartbeat`** — {event: "scheduler_heartbeat", timestamp} — emitted at the **start** of every scheduled process invocation, before any work, independently of whether the work succeeds; absence of this event within two scheduled intervals is the operator alert trigger for "scheduler not running"
- **`observability_collector_health`** — {event: "collector_heartbeat", timestamp} — emitted by the Observability Collector itself on a regular interval (e.g., every 5 minutes); absence of this event is the signal that the collector itself has failed
- `active_users_event` — {event: "active_users_count_updated", count, timestamp} — pushed by Entry Processor after each successful Entry write; enables near-real-time `active_users_count` in Observability dashboards
- `error_event` — {event: "error", component, error_type, internal_user_id (if applicable), timestamp}
- `token_auth_failure_event` — {event: "token_auth_failure", component: "telegram_gateway", timestamp}

**Traces (critical paths):**
- End-to-end: Telegram Gateway → Entry Processor → NLP Engine → Data Repository → Alert Engine → Telegram Gateway (covers the entry-to-confirmation critical path)
- End-to-end: ParseAttempt Manager → Data Repository → Telegram Gateway (covers disambiguation prompt delivery and AD-9 compensation path)
- Background: Chart Generator coroutine → Data Repository (read) → Telegram Gateway (second message delivery — traces the async chart delivery path)

### 11.2 Operational Dashboards (Conceptual)

| Dashboard | What to Monitor |
|-----------|----------------|
| **Bot health** | `bot_uptime` heartbeat; Telegram API connectivity; process restarts; `token_auth_failure_event` presence; `observability_collector_health` heartbeat presence |
| **Parse quality** | Rolling parse success rate (7-day window); ParseAttempt creation rate; disambiguation completion rate; late categorisation rate; ambiguous-entry percentage |
| **Alert reliability** | Alert evaluation count; dispatch success vs. failure rate; retry rate; `failed_after_retry` count |
| **User activity** | `active_users_count` (near-real-time via `active_users_event`); entries per day; chart request count vs. `chart_delivery_event` success count |
| **Data lifecycle** | PendingDeletion accounts count and age; Deferred ParseAttempt count and age; `scheduler_heartbeat` last timestamp; `scheduler_run_completed` last timestamp and outcome |
| **Errors** | Error event count by component; cascade deletion failures; Data Repository write failure rate; `chart_delivery_failed` count |

---

## 12. Architectural Decisions (ADR-style)

### AD-1: Single-Process Monolith Architecture

- **Decision:** Deploy the system as a single process with logically separated, named components communicating in-process.
- **Alternatives considered:** (a) Microservices — each component as a separate deployable service; (b) Serverless functions — each flow as an independent function invocation.
- **Rationale:** The confirmed scale ceiling is 10 users (~100 metric time series). Distribution adds infrastructure complexity, network failure modes, and operational overhead that is disproportionate to the scale. A single-process design is the minimum viable architecture for this scope.
- **Trade-offs:** Single process = coupled failure modes (one crash takes down all components). Offset by: component separation enables future extraction into services if scale requires; process supervisor provides restart-on-failure. Microservices would require service discovery, distributed tracing, and network resilience logic — all cost without benefit at this scale.
- **Consequences:** Clear component interfaces must be enforced in code to preserve the future option to extract components. No shared mutable state between components except through the Data Repository. **Concurrency note: the single process contains one asynchronous execution path — the chart generation coroutine (AD-6). Shared resources during coroutine execution are limited to the Data Repository (read path only). User Session Guard state and ParseAttempt state are not accessed by the coroutine. Concurrent reads to the Data Repository are assumed safe under the chosen storage technology (AU-003 must confirm this). No locks or synchronization primitives are required unless the storage technology requires serialization for concurrent reads.**
- **Linked NFR/Business Goal:** AG-5 (operational simplicity); §8.2 scale ceiling; R-008 (single operator)

---

### AD-2: Telegram Gateway — Polling vs. Webhook

- **Decision:** Architecture is neutral between polling and webhook. The choice is deferred to deployment context. Webhook is preferred if the deployment platform supports a public HTTPS endpoint; polling is acceptable as a fallback.
- **Alternatives considered:** Long-polling (simpler, no public endpoint required); webhook (lower latency, more efficient, requires HTTPS endpoint).
- **Rationale:** Both approaches are functionally equivalent for the Telegram Bot API. Webhook eliminates the polling interval latency (up to ~1 s) and is more efficient. However, it requires a stable public HTTPS endpoint with a valid TLS certificate. If the deployment platform does not provide this, polling is a clean fallback with no additional latency concern at 10-user scale.
- **Trade-offs:** Polling adds ~1 s average latency to the entry ack budget; this is within the 5 s target but consumes part of the budget. Webhook eliminates this latency but adds deployment infrastructure requirements.
- **Consequences:** The Telegram Gateway component must be designed to support both modes behind the same interface. The mode is determined by configuration, not code changes. **Coupling note: the health check contract (§7.1) must be compatible with the chosen mode. If polling is chosen (no public HTTPS endpoint), the health check cannot be an externally callable HTTP endpoint — it must instead be an internal polling-mode heartbeat signal (e.g., a successful Telegram API poll response used as a health proxy, or a local health file written by the process). This dependency must be resolved at deployment platform selection.**
- **Linked NFR/Business Goal:** AG-1 (≤ 5 s entry ack); NFR Unknown: deployment platform constraints

---

### AD-3: Post-Commit In-Process Alert Evaluation

- **Decision:** Alert evaluation is triggered immediately after successful entry storage, within the same request-handling cycle, but decoupled from the entry storage transaction (not rolled back if alert evaluation fails).
- **Alternatives considered:** (a) Synchronous within the same transaction — atomically evaluates alerts as part of entry storage; (b) Asynchronous via a work queue — evaluates alerts in a separate worker.
- **Rationale:** At 10-user scale, synchronous in-process evaluation after commit is the simplest approach that satisfies the ≤ 60 s alert dispatch target. A work queue adds infrastructure and operational complexity without benefit at this scale. Including alert evaluation inside the entry storage transaction creates a risk that alert evaluation failure rolls back a valid entry (§8.3 explicitly prohibits this).
- **Trade-offs:** In-process evaluation means a slow or failing alert evaluation delays the confirmation message to the user (though entry is already stored). At portfolio scale this is acceptable. At higher scale, a queue would decouple the paths completely.
- **Consequences:** Entry Processor must explicitly catch and log alert evaluation failures without propagating them as entry storage failures. The boundary between "entry stored" and "alert evaluated" must be explicit in the code.
- **Linked NFR/Business Goal:** AG-2 (entry storage reliability); §8.3 atomicity; NFR: alert dispatch ≤ 60 s

---

### AD-4: MetricActivityStatus — Lazy Computation on Read

- **Decision:** MetricActivityStatus is computed on-demand when requested (e.g., when computing the active user count for success metric reporting), not maintained as a continuously updated materialized view. However, `active_users_count` for the Observability Collector is pushed on each Entry write (not computed lazily) to maintain dashboard freshness.
- **Alternatives considered:** (a) Event-driven: recompute on every Entry write; (b) Scheduled: recompute on periodicity boundary (daily or weekly); (c) Lazy: compute on read.
- **Rationale:** At ~100 time series, computation cost is negligible. Lazy computation is the lowest-complexity starting point (SU-005 recommendation). However, the Observability push requirement for `active_users_count` (AG-4, business success metric) requires a lightweight push on Entry write to maintain a non-stale dashboard value. This is not a full event-driven recomputation — it is a targeted read of the current computed value at write time, followed by emitting the result as an Observability event.
- **Trade-offs:** Lazy computation returns a value that reflects the state at query time — no staleness introduced by computation lag. The Observability push on Entry write adds a minor overhead per entry (one read + one event emit). At 100 entries/day, this is negligible. At 10,000+ time series, lazy computation would need to be replaced with a materialized view.
- **Consequences:** MetricActivityStatus is not a stored entity in the persistent sense — it is derived on every read. The Metric Manager owns this computation. Timezone handling (SU-007) is the primary accuracy risk. Entry Processor must call the MetricActivityStatus read and emit `active_users_event` after successful entry storage (alongside the alert evaluation trigger).
- **Linked NFR/Business Goal:** AG-4 (success metrics measurable); business success metric: tracking retention >40%

---

### AD-5: Repository-Layer User Isolation

- **Decision:** Per-user data isolation is enforced at the Data Repository layer by including internal_user_id as a mandatory parameter in all data access operations, not at the application (component) layer via result filtering.
- **Alternatives considered:** Application-layer filtering: components retrieve data and filter by user_id before returning.
- **Rationale:** Application-layer filtering is vulnerable to a "miss one call" failure mode — a single missing filter clause would expose all users' data to the requesting user. Repository-layer enforcement means the query itself is scoped to a single user_id; a missing user_id is a structural error caught at the interface boundary, not a runtime filtering bug.
- **Trade-offs:** Repository-layer enforcement requires that all repository access functions include user_id as a mandatory typed parameter, which adds boilerplate. This cost is justified by the security guarantee. Cross-user visibility is a 100% non-negotiable target (R-005).
- **Consequences:** The Data Repository interface must be designed with user_id as a first-class parameter on every read and write operation. No "get all" operations may exist in the public repository interface that are not scoped by user_id. **Testability requirement: the interface must support injection of a test-controlled backend. Integration tests must verify isolation by calling every read operation with a mismatched user_id and asserting no data is returned.**
- **Linked NFR/Business Goal:** AG-3 (user data isolation); R-005 (cross-user leak — critical); business success metric: 100% isolation

---

### AD-6: Two-Phase Chart Response

- **Decision:** Chart requests receive an immediate acknowledgment message (≤ 5 s) followed by the actual chart image delivered asynchronously (≤ 30 s from request).
- **Alternatives considered:** Single-phase: block the response until the chart is generated and deliver it in one message.
- **Rationale:** Chart generation is computationally heavier than simple data lookups. If the system blocks for up to 30 s before responding, the user has no indication their request was received — violating the perception of responsiveness. A two-phase response provides immediate user feedback within the 5 s entry ack target, then delivers the chart image when ready.
- **Trade-offs:** Two-phase requires the Telegram Gateway and Chart Generator to coordinate the two-step dispatch. It adds implementation complexity (background coroutine). The alternative (single-phase, 30 s block) risks user re-submission and Telegram bot timeout behavior.
- **Consequences:** Chart Generator must support asynchronous execution (post-response fire-and-forget coroutine — see AD-10). Telegram Gateway must support sending a follow-up message to a specific user after an initial acknowledgment. If chart generation fails, the error message is sent as the second message. Delivery outcome is emitted as `chart_delivery_event`.
- **Linked NFR/Business Goal:** AG-1 (response latency); §8.1 chart ack ≤ 5 s; chart delivery ≤ 30 s

---

### AD-7: Cascade Deletion Atomicity

- **Decision:** All cascade deletions (account deletion, metric deletion, scheduled purge) are implemented as a **single database transaction** spanning all entities belonging to the deleted user or metric. The transaction commits only when all related entities (InternalUser, Metrics, Entries, Alerts, ParseAttempts, raw_input fields) have been successfully deleted. If any delete step fails, the transaction is rolled back and the deletion is retried on the next scheduled process run.
- **Alternatives considered:**
  - **(a) Single database transaction (chosen):** All cascade deletes within one atomic commit. Rollback on failure. Simple and correct if the Data Repository supports multi-entity transactions.
  - **(b) Soft-delete with background vacuum worker:** Entities are marked as deleted immediately, a background process later physically removes them. Faster user-facing response; but PII (raw_input) remains physically present until vacuum runs — this is a privacy concern given D-013 and R-005.
  - **(c) Application-level multi-step deletion with compensating writes:** Each entity type is deleted in sequence; on failure, a compensating operation attempts to roll back completed steps. Complex to implement correctly; inconsistent state is possible if compensation also fails.
- **Rationale:** Option (a) is the simplest correct approach at this scale. The Data Repository is assumed to support transactions (AU-003 must confirm). At ~100 time series per user, the transaction scope is small and performance is not a concern. Option (b) introduces a window where PII is physically present but logically deleted — unacceptable given the privacy requirements (R-017, SD-005). Option (c) introduces coordination complexity without benefit.
- **Trade-offs:** Option (a) requires transaction support from the Data Repository technology — this is a hard dependency on AU-003. If the chosen Data Repository does not support multi-entity transactions, option (c) must be revisited. For a portfolio-scale system with a simple relational store, (a) is the right default.
- **Consequences:** The Scheduled Process and Metric Manager must use a transactional delete pattern. The Data Repository interface must expose a transactional cascade delete operation as a first-class method (not assembled from individual delete calls at the application layer). Idempotency: if a transaction is interrupted (process crash mid-transaction), the Data Repository's rollback semantics ensure no partial state persists — the next scheduled process run will re-identify and re-purge the same accounts.
- **Linked NFR/Business Goal:** AG-7 (lifecycle enforcement); R-005 (data isolation — cascade atomicity); §8.3 System v0.7 (atomicity requirements); D-013 (retention guarantee)

---

### AD-8: Alert Evaluation Suspended for Archived Metrics (SU-004 Resolution)

- **Decision:** When Metric.status = Archived, the Alert Engine does not evaluate any Active alerts associated with that metric against new entries. Alert records are preserved in their current status (Active, Triggered, or Archived). If the metric is reactivated (Metric.status → Active), the Alert Engine resumes evaluating Active alerts for that metric.
- **Alternatives considered:**
  - **(a) Suspend evaluation on archival (chosen):** Archiving implies the user is no longer actively tracking the metric; firing alerts on an archived metric would be unexpected behavior.
  - **(b) Continue evaluation on archival:** Alerts remain fully active regardless of metric status. Simple; but semantically unexpected — the user would receive alert notifications for a metric they consider dormant.
  - **(c) Auto-archive or auto-delete associated alerts on metric archival:** Alerts are automatically deactivated when the metric is archived. Cleaner; but irreversibly loses the alert configuration — the user would need to reconfigure alerts on reactivation.
- **Rationale:** Option (a) matches the semantic intent of archival: the metric is paused, not deleted. Alert configuration is preserved for reactivation. Option (b) is surprising to the user. Option (c) is destructive and may cause user frustration on reactivation.
- **Trade-offs:** Option (a) adds a status check to the Alert Engine's evaluation path. This is a trivially cheap check. The behavioral rule must be explicitly coded in the Alert Engine — this AD documents the intended behavior so it cannot be accidentally omitted.
- **Consequences:** Alert Engine evaluation path must include a guard: `if Metric.status == Archived: skip evaluation`. This rule is a first-class behavioral constraint of the Alert Engine (see §4.1). Flow H (Metric Archival) confirmation message must inform the user that alert notifications are paused while the metric is archived.
- **Linked NFR/Business Goal:** AG-7 (lifecycle enforcement); SU-004 resolution; business success metric: alert delivery accuracy (alerts should not fire unexpectedly)

---

### AD-9: ParseAttempt + Prompt Atomicity — Compensating Delete

- **Decision:** ParseAttempt creation and prompt dispatch are treated as an atomic unit via a **compensating delete** pattern owned by the ParseAttempt Manager. On prompt dispatch failure, the ParseAttempt Manager deletes the created ParseAttempt record before returning an error to the user. No Pending ParseAttempt without a dispatched prompt is ever left in the Data Repository.
- **Alternatives considered:**
  - **(a) Compensating delete on dispatch failure (chosen):** Create ParseAttempt → attempt dispatch → on failure: delete ParseAttempt → return error to user.
  - **(b) Transactional create + dispatch:** Wrap ParseAttempt creation and prompt dispatch in a single transaction. Not feasible — Telegram Gateway dispatch is an external I/O operation and cannot participate in a database transaction.
  - **(c) Retry dispatch on failure:** Create ParseAttempt → attempt dispatch with retries → on final failure: either leave Pending or delete. Retry adds latency to the user-facing response. If retries are exhausted, the same decision point is reached.
- **Rationale:** Option (a) is the simplest correct approach. Option (b) is not feasible given the external I/O boundary. Option (c) adds latency without resolving the fundamental cleanup decision. The compensating delete must succeed; if it also fails (extremely unlikely), the dangling record is detected via Observability and operator manual cleanup is the resolution path.
- **Trade-offs:** Compensating delete means two write operations on the failure path (create + delete). This is acceptable: the failure path is exceptional, not common. The alternative (leaving a dangling Pending ParseAttempt) would block the user from sending any new messages until the record is cleared — a far worse outcome.
- **Consequences:** ParseAttempt Manager must implement the compensating delete in a try/finally or equivalent pattern. If the compensating delete fails: emit `error_event` with `component: "parse_attempt_manager"` and `error_type: "compensation_delete_failed"` to Observability Collector; the dangling record is detectable via `parse_attempt_event` (Pending, no prompt dispatched) in the dashboard.
- **Linked NFR/Business Goal:** AG-6 (graceful NLP degradation); §8.3 System v0.7 (ParseAttempt atomicity — hard consistency requirement)

---

### AD-10: Async Chart Execution Model — Post-Response Fire-and-Forget Coroutine

- **Decision:** Chart generation is implemented as a **post-response fire-and-forget coroutine** launched after the acknowledgment message is sent to the user. The coroutine must: (a) catch all exceptions; (b) on failure, send an error message to the user as the second Telegram message; (c) emit `chart_delivery_event` with outcome "delivered" or "chart_delivery_failed" to the Observability Collector regardless of success or failure.
- **Alternatives considered:**
  - **(a) Post-response fire-and-forget coroutine (chosen):** Simple; acknowledgment returned synchronously; chart generated in background.
  - **(b) Dedicated background thread pool:** More controllable concurrency; adds thread management overhead; not justified at portfolio scale.
  - **(c) In-process task queue:** More formal; adds infrastructure within the monolith; overkill for a single async concern.
- **Rationale:** Option (a) is the minimum viable implementation for a single async concern in a single-process monolith serving ≤10 users. Options (b) and (c) add architectural complexity without benefit at this scale. The key risk (unhandled exception in the coroutine leaving the user with no response) is mitigated by the required exception handling contract.
- **Trade-offs:** Fire-and-forget means there is no formal back-pressure or queue depth limit. At 10-user scale with occasional chart requests, this is not a concern. If chart requests were to arrive faster than they can be generated (not realistic at portfolio scale), requests could pile up without bound. The coroutine is the only non-trivially-concurrent execution path in the monolith.
- **Consequences:** Chart Generator implementation must include a top-level exception handler covering the full coroutine body. The coroutine must be supervised by the main process (if the coroutine crashes silently, no error message reaches the user). The coroutine accesses Data Repository in read-only mode — no write locks are required. Telegram Gateway must support sending a follow-up message to a specific user outside of the request/response cycle.
- **Linked NFR/Business Goal:** AG-1 (chart ack ≤ 5 s); AG-5 (operational simplicity); AD-6 (two-phase chart response)

---

## 13. Risks & Open Questions

### 13.1 Architecture Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| NLP parsing latency exceeds the 5 s entry ack budget if an external service is required | High — users experience delayed feedback; core UX proposition undermined | Medium — depends on NLP library/service choice (not yet decided) | Prefer in-process NLP library; if external, measure latency early and budget accordingly. **A structured `/log` command fallback is NOT currently modelled as a mitigation — if NLP latency is persistently unacceptable in production, a future ADR will be required to add a structured command flow (new Message Dispatcher classification path, new Entry Processor branch, new user-facing documentation).** |
| Data Repository backup gap | Medium — data loss on Repository failure; D-013 retention obligation unmet without backup | Medium — backup mechanism must be implemented before first deployment | **Mitigated by AD intent in §7.1: daily file export to durable storage; RPO ≤ 24 h; RTO ≤ 4 h. This risk is reduced from High to Medium — architectural intent is defined; residual risk is in deployment execution.** |
| Scheduled Process is a single point of failure for all time-triggered obligations | High — PendingDeletion purges never happen; stale Deferred ParseAttempts accumulate | Medium — scheduler failure is silent unless heartbeat monitored | `scheduler_heartbeat` event (distinct from `scheduler_run_completed`) in Observability Collector; operator alert if heartbeat absent for more than two scheduled intervals; design process to be idempotent and re-runnable manually |
| Open bot registration (R-018) causes user count to exceed the 20-user architecture ceiling | Medium — system degrades without warning above ceiling | Low–Medium (if bot address leaks publicly) | Document the ceiling explicitly; User Session Guard contains a named access-control placeholder check point (see §10); allowlist or invite-code mechanism can be added here without structural changes |
| PII in Observability logs (raw_input accidentally logged) | Medium — privacy breach via log access | Low — if schema validation gate at Observability Collector is enforced at design time | Structural schema enforcement: all event schemas reference only IDs; schema validation gate at emission boundary rejects non-conforming events (see §10) |
| Async chart coroutine unhandled exception | Medium — user receives acknowledgment but no chart or error; silent failure | Low — if AD-10 exception handling contract is implemented | AD-10 mandates top-level exception handler in coroutine; `chart_delivery_failed` event emitted; second Telegram message sent on failure |
| Observability Collector failure cascading to all five business metrics | High — all success metrics uncomputable; operator has no automated signal | Low — collector is a simple structured log emitter | Fire-and-forget contract with stderr fallback; `observability_collector_health` heartbeat enables detection; operator falls back to manual local log inspection |

### 13.2 Open Questions

1. **NLP library or service choice** — Blocks: in-process vs. external decision; entry ack latency estimate; AD-1 monolith trade-off confirmation; future `/log` fallback ADR may be required if external latency is unacceptable. *Impact: High.*
2. **Deployment platform** — Blocks: polling vs. webhook decision (AD-2); health check endpoint type (AD-2 coupling note); scheduled process implementation (cron, in-process scheduler, or platform-native); process supervisor choice. *Impact: Medium.*
3. **Data Repository technology (AU-003)** — Blocks: transaction semantics for AD-7; unique-constraint-on-Telegram-ID (AD-5); concurrent read safety for AD-10 chart coroutine; backup tooling for D-013. *Impact: High.*
4. **ParseAttempt expiry timeout (SU-001)** — Recommended starting value: 24 hours. Must be confirmed and made configurable. *Impact: Medium.*
5. **NLP confidence threshold (SU-002)** — Must be defined before the NLP Engine can distinguish auto-parse from ParseAttempt creation. Directly impacts the 85% parse success target. *Impact: High.*
6. **Stale Deferred ParseAttempt cleanup window (SU-006)** — Recommended starting value: 30 days. Must be confirmed and configurable. *Impact: Low.*
7. **Scheduled Process cadence confirmation** — Recommended minimum: at least every 12 hours (worst-case purge delay ≤12 h beyond the 3-day window). Final value is a deployment decision; must be communicated accurately in user-facing deletion notices. *Impact: Medium.*
8. **Chart rendering library** — Blocks: chart delivery latency estimate; image size constraints; AD-6 two-phase feasibility. *Impact: Medium.*
9. **Timezone handling for MetricActivityStatus (SU-007)** — UTC as default is confirmed in System v0.7. Per-user timezone is a future enhancement. No blocking decision required for v1. *Impact: Low.*
10. **Data Repository concurrent read safety** — Must be confirmed at AU-003 resolution: does the chosen storage technology support concurrent reads from the chart generation coroutine without locks? *Impact: Medium.*

---

## 14. Traceability Matrix

| Business Goal | Architectural Goal | Component | Key Decision | Risk |
|--------------|-------------------|-----------|-------------|------|
| Reduce tracking abandonment (retention >40%) | AG-1 (≤5 s ack); AG-6 (graceful NLP degradation) | Telegram Gateway; NLP Parsing Engine; Entry Processor; ParseAttempt Manager | AD-1 (monolith); AD-3 (post-commit alert eval); AD-6 (two-phase chart); AD-9 (ParseAttempt atomicity) | R-002 (parse failures); R-009 (NLP accuracy); R-014 (ParseAttempt expiry) |
| Enable self-insight through history | AG-2 (reliable entry storage); AG-4 (measurable metrics) | Data Repository; Chart Generator; Alert Engine; Metric Manager; **Scheduled Process (D-013 retention enforcement — without retention, entries become unavailable within 1 year)** | AD-4 (lazy MetricActivityStatus + Observability push); AD-5 (repository-layer isolation); AD-6 (two-phase chart); **D-013 backup intent (§7.1)** | R-002 (immutable wrong entry); R-006 (no export); R-016 (chart failure) |
| User data privacy and trust | AG-3 (user isolation); AG-7 (lifecycle enforcement) | Data Repository; Account Manager; Scheduled Process; Metric Manager (cascade) | AD-5 (repository-layer isolation); **AD-7 (cascade deletion atomicity — single DB transaction)** | R-005 (cross-user leak — critical); R-007 (raw_input residual); R-017 (raw_input PII); R-018 (open registration) |
| Service continuity | AG-5 (operational simplicity); AG-7 (lifecycle enforcement) | Scheduled Process; Observability Collector; Configuration & Secrets | AD-1 (monolith + process supervisor + health check contract); AD-2 (polling/webhook) | R-008 (single operator); R-013 (persistence failure); scheduled process failure |
| Portfolio demonstration (all success metrics at target) | AG-4 (all metrics measurable) | Observability Collector; all components emitting structured events | All ADs — observability is a cross-cutting concern; **AD-4 Observability push for `active_users_count` freshness**; **AD-8 (SU-004 alert-on-Archived resolved)** | R-009 (parse accuracy unmeasurable without observability); R-012 (MetricActivityStatus stale); R-018 (inflated user count) |

---

## Governance Block

### Version
v0.8

### Based On
Business v0.5 + Context v0.7

### Changes Introduced

All changes are in response to mandatory and recommended revisions from `architecture_v0.7_review.md`:

1. **AD-7 defined** (Cascade Deletion Atomicity — single database transaction). Phantom reference in §14 replaced with the actual decision. Three alternatives explicitly compared.
2. **AD-8 defined** (SU-004 Resolution — alert evaluation suspended for Archived metrics). Elevated from an inline open question (§13.2 item 8) to a full ADR. Alert Engine component model updated with explicit behavioral constraint.
3. **AD-9 defined** (ParseAttempt + Prompt Atomicity — compensating delete). ParseAttempt Manager now owns the compensation mechanism. Flow B updated with step-by-step compensation path.
4. **AD-10 defined** (Async Chart Execution Model — post-response fire-and-forget coroutine). Resolves the undefined two-phase chart mechanism. AD-1 updated with concurrency note.
5. **Flow F added** (Account Restoration — System v0.7 Flow 10a). Models PendingDeletion → Active transition, confirmation message, and non-confirmation behavior.
6. **Flow G added** (ParseAttempt Late Categorisation — System v0.7 Flow 3b late categorisation subprocess). Models Deferred list view, Entry creation path (a), and discard path (b).
7. **Flow H added** (Metric Archival and Reactivation). Models Active ↔ Archived transitions, AD-8 behavioral consequence, and failure points.
8. **Backup architectural intent defined** (§7.1 NFR Mapping). Daily file export; RPO ≤ 24 h; RTO ≤ 4 h. Risk level reduced from "High, unmitigated" to "Medium, mitigated."
9. **Observability Collector failure contract defined** (fire-and-forget with stderr fallback). Added to §4.2 Observability Collector description, §7.1 NFR Mapping, and §9 Failure Scenarios.
10. **`scheduler_heartbeat` event added** (§11.1 Signals). Distinct from `scheduler_run_completed` — emitted at start of each invocation regardless of work outcome. Flow E updated.
11. **`observability_collector_health` heartbeat added** (§11.1 Signals). Self-health signal for the Observability Collector.
12. **`active_users_count` freshness mechanism defined** (§11.1 Signals, AD-4 updated). Pushed on each Entry write via `active_users_event`. Avoids AD-4 lazy staleness in Observability push path.
13. **`chart_delivery_event` added** (§11.1). Separate from `chart_invocation_event` — tracks delivered vs. failed chart deliveries. `chart_invocation_rate` metric updated to use delivery success event.
14. **`alert_evaluation_event` updated** (§11.1). `dispatch_outcome` now distinguishes "failed_after_retry" from "failed" (first attempt).
15. **New failure scenarios added** (§9): Observability Collector unavailable; Chart generation coroutine crash after acknowledgment; Scheduled Process concurrent overlap; Re-registration of Deleted user; Alert notification dispatch failure after retry exhausted.
16. **Scheduled Process cadence** (§4.1, §7.1, §13.2 item 7): Recommended minimum ≥ every 12 hours. Worst-case purge delay implication stated.
17. **Health check contract specified** (§7.1). Response contract defined. AD-2 coupling note added for polling-mode health check.
18. **Testability strategy for isolation** (§10, AD-5). Repository interface injection requirement and integration test contract added.
19. **raw_input log-boundary structural enforcement** (§10). Schema validation gate at Observability Collector added. Structural absence of free-text fields in event schemas.
20. **Open bot registration allowlist placeholder** (§4.1 User Session Guard, §10). Named check point added for future access control — single extension point without structural changes.
21. **Re-registration of Deleted user** (§4.1 Account Manager). Explicit handling: create new InternalUser record, never reactivate deleted record.
22. **Traceability Matrix updated** (§14). Scheduled Process added to "Enable self-insight through history" row (D-013 link). AD-7 phantom reference replaced. AD-8 and AD-9 added to relevant rows.
23. **/log structured command fallback removed as a stated mitigation** (§13.1). Replaced with an explicit note: if NLP latency is unacceptable, a future ADR will be required. No current architectural backing exists for a `/log` command.
24. **SU-004 inline resolution removed from §13.2** (item 8 promoted to AD-8).

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|----|----------|-----------|---------|--------|
| AD-1 | Single-process monolith + concurrency note for chart coroutine | ~10-user scale; operational simplicity; component separation preserves future extraction option; chart coroutine is read-only, no shared mutable state beyond Data Repository reads | v0.8 | Confirmed |
| AD-2 | Polling vs. webhook — deferred; health check coupling documented | Platform constraints not yet known; both options satisfy functional requirements; health check must adapt to chosen mode | v0.8 | Open — pending deployment platform decision |
| AD-3 | Post-commit in-process alert evaluation | Entry storage must not be rolled back on alert failure; in-process sufficient at this scale | v0.8 | Confirmed (unchanged) |
| AD-4 | MetricActivityStatus lazy computation on read + Observability push on Entry write | Lowest complexity at portfolio scale; Observability `active_users_count` pushed on each Entry write to maintain freshness | v0.8 | Confirmed (updated) |
| AD-5 | Repository-layer user isolation + testability strategy | Security boundary; integration test injection pattern required for AG-3 verification | v0.8 | Confirmed (updated) |
| AD-6 | Two-phase chart response | Immediate acknowledgment ≤5 s required; chart generation may take up to 30 s | v0.8 | Confirmed (unchanged) |
| AD-7 | Cascade deletion atomicity — single database transaction | Simplest correct approach at portfolio scale; soft-delete alternatives rejected due to PII window; compensating write alternative rejected as complex and fragile | v0.8 | Confirmed (new) |
| AD-8 | Alert evaluation suspended for Archived metrics (SU-004 resolution) | Archiving implies dormant tracking; unexpected alert notifications on archived metrics would surprise users; alert configuration preserved for reactivation | v0.8 | Confirmed (new) |
| AD-9 | ParseAttempt + Prompt atomicity via compensating delete | External I/O boundary makes true transaction impossible; compensating delete is the correct pattern; dangling Pending ParseAttempt is worse than a failed flow | v0.8 | Confirmed (new) |
| AD-10 | Async chart execution — post-response fire-and-forget coroutine | Minimum viable async implementation for a single async concern; top-level exception handler and delivery event are mandatory contract | v0.8 | Confirmed (new) |

### Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|----|------|-------------|--------|-----------------|
| AU-001 | Architecture | NLP library/service not chosen — affects in-process vs. external decision and entry ack latency budget | High | Evaluate candidate NLP libraries early in implementation; benchmark latency before committing to architecture |
| AU-002 | Architecture | Deployment platform not specified — affects polling vs. webhook (AD-2), health check type, and scheduled process implementation | Medium | Determine before implementation begins |
| AU-003 | Architecture | Data Repository technology not chosen — affects transaction semantics (AD-7), unique constraint implementation (AD-5), concurrent read safety (AD-10), and backup tooling | High | Choose before any implementation of flows with atomicity requirements (Flows 1, C, Flow 11) |
| SU-001 | System (carried) | ParseAttempt expiry timeout — recommended 24 h | Medium | Confirm at implementation; make configurable |
| SU-002 | System (carried) | NLP confidence threshold — undefined | High | Define at NLP library/service selection time |
| SU-006 | System (carried) | Stale Deferred ParseAttempt cleanup window — recommended 30 days | Low | Confirm at implementation; make configurable |
| SU-007 | System (carried) | Timezone handling — UTC default confirmed; per-user timezone deferred | Low | No action required for v1 |
| SU-008 | Business (carried) | raw_input GDPR classification not formally assessed | Medium | Accept for portfolio scope; review before scaling |
