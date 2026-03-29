# Architecture Overview

## 1. Document References

- Business Version: v0.3
- Context Version: v0.3

---

## 2. Architectural Goals

| Goal | Why it matters | Linked Business Goal | Metric |
|---|---|---|---|
| Low-friction message handling | Every extra second of latency erodes the core value proposition of logging from within a chat | Personal utility — reduce logging friction | Text response latency ≤ 3 s under normal load |
| Correct per-user data isolation | Trust is the foundation of a closed personal system; a cross-user data leak is the worst failure mode | Multi-tenancy (D-02), personal utility | Zero cross-user query paths; User ID mandatory on all storage operations |
| Graceful parse failure recovery | Parse failures must not silently discard user intent | Parse failure resolution rate > 80% | PendingClarification resolution rate tracked via ParseAttempt / PendingClarification records |
| Zero-dependency simplicity | Free hosting tiers impose resource constraints; added dependencies increase failure surface | Near-zero infrastructure cost | Single-process deployment; embedded storage; no external services beyond Telegram |
| Observability from day one | Developer is sole operator; metrics must be self-service queryable without tooling | System Functionality (zero critical failures in 30 days), Developer Learning Outcome | Structured logs; queryable ParseAttempt / PendingClarification tables; User.last_active_at timestamps |
| Predictable failure behavior | Every failure path must produce a user-visible message — no silent drops | Error communication NFR (Section 8.6) | 100% of failure paths have defined response; no silent message loss |
| Survivable restarts | Free-tier hosts kill idle processes; the system must reach a clean, consistent state after every startup | System reliability, data durability | Startup sweep completes before first message is processed; Open PendingClarifications abandoned; expired deletions purged |

---

## 3. Architecture Summary

The system is a **single-process, event-driven Telegram bot** with embedded relational storage. All components run within one runtime process co-located with the storage layer, deployed on a free-tier hosting platform. There is no microservice split, no message queue, no external data service, and no external charting service.

The bot process continuously receives Telegram updates (either via long-polling or webhook — see AD-1), dispatches each inbound message through a layered routing pipeline, and responds synchronously within the same request cycle. The **Dispatcher owns per-user message serialization** via an in-process per-user lock acquired at dispatch entry and released only after the full handler cycle (including all storage writes) completes. Chart generation is the only computationally heavy operation and is bounded by a hard timeout enforced via **preemptive cancellation** (not cooperative flag-checking).

A **Heartbeat component** executes periodic self-pings within the Telegram Gateway process loop to prevent free-tier process suspension and reduce cold-start latency. On every process startup, a sweep executes before accepting messages: it abandons stale Open PendingClarifications and executes pending account deletions past their 3-day window. A daily data export (triggered within the single-process loop on a timer, or externally triggered) copies a portable snapshot of the embedded storage to a developer-controlled external location — this is the sole disaster recovery mechanism.

The architecture favours correctness over throughput, simplicity over extensibility, and explicit failure messages over silent degradation. At ≤ 100 users with ~500 messages/day, no scaling mechanism is needed.

---

## 4. Component Model

### 4.1 Core Components

| Component | Responsibility | Inputs | Outputs | Key Risks |
|---|---|---|---|---|
| **Telegram Gateway** | Connects to the Telegram Bot API; receives inbound updates; sends outbound text messages and PNG images; enforces rate-limit retry before surfacing errors; filters non-text messages at the pre-dispatch gate; runs the Heartbeat timer loop for cold-start prevention | Telegram updates (long-poll or webhook); outbound message payloads from handlers; periodic Heartbeat timer | Inbound message events to the Dispatcher; delivery acknowledgements; periodic no-op keep-alive calls to the API | Telegram API change or outage makes the system unreachable; rate-limit retry logic must not silently drop messages |
| **Dispatcher** | Routes every inbound text message through the priority chain: (1) PendingClarification check → (2) Account state check → (3) Keyword match — including keyword collision disambiguation — → (4) Log intent default. **Owns per-user message serialization**: acquires a per-user in-process lock at dispatch entry; releases it only after the handler completes and all storage writes have returned. A second message from the same user arriving while the lock is held is queued and processed after the lock is released. | Inbound text message event with Telegram ID and text payload | Routed request to appropriate Command Handler or Parse Engine; rejection response for blocked account state | Misrouting log-intent messages as commands (keyword collision is resolved here, not in Parse Engine); lock acquisition must not deadlock; account state check must occur before any write |
| **Parse Engine** | Extracts a parameter name and numeric value (with optional unit) from a free-text message that has already been routed to it as log intent by the Dispatcher; creates a ParseAttempt record for every invocation | Free-text message payload (already disambiguated from command keywords by the Dispatcher) | Parsed (name, value, unit) tuple on success; parse failure signal on failure; ParseAttempt record written to storage | False positives (wrong parameter or value extracted); false negatives (valid log input rejected); parse failure rate must be instrumented from day one |
| **Command Handlers** | One handler per dispatch target (Log, History, Chart, Compare, List, Delete Parameter, Delete Account, Restore Account, Onboarding, Help, Clarification); each handler encapsulates the complete logic for its assigned flow as defined in System v0.3 Sections 6–7 | Routed request with Telegram ID and parsed parameters | Response message(s) sent via Telegram Gateway; storage reads and writes via Storage Layer; chart image sent via Telegram Gateway (Chart Handler only) | Chart Handler must enforce the 15-second preemptive timeout; Deletion handlers must enforce two-step confirmation; Onboarding Handler must deliver operator disclosure with write-before-send atomicity contract |
| **Storage Layer** | Persists and retrieves all system entities (User, Parameter, LogEntry, ParseAttempt, PendingClarification, OnboardingSession, DeletionConfirmation); enforces mandatory User ID scoping on every query; sanitizes all inputs before storage operations; all multi-entity writes execute within a single transaction | Read/write requests from Command Handlers and Startup Sweep | Query results; write acknowledgements or failure signals | Cross-user query path defect is the highest-impact security failure; raw user input must never be interpolated directly into queries; transaction support is a mandatory selection criterion for the embedded storage engine |
| **Startup Sweep** | Executes once on every bot process start before the Telegram Gateway begins accepting messages; (a) marks all Open PendingClarification records as Abandoned; (b) purges all User records in Pending Deletion state where `deletion_requested_at + 3 days ≤ current_time`, cascading to all owned entities; writes an audit log entry per purge | Embedded storage state on startup | Updated storage state; structured audit log entries | If sweep crashes, bot must not start accepting messages; sweep must be idempotent in case of partial execution |

### 4.2 Supporting Components

| Component | Responsibility | Notes |
|---|---|---|
| **Chart Generator** | Generates a static PNG trend chart image from a set of LogEntry data points; executed in-process under a hard 15-second timeout enforced by the Chart Handler via **preemptive cancellation** — the rendering operation must be interruptible at the OS/runtime level (e.g., goroutine context cancellation, thread interruption, or async task cancellation), not merely flag-checked; the image is held in memory and delivered directly — never persisted | Cooperative cancellation (checking a flag between steps) is explicitly prohibited as the rendering implementation may block on a single call; the cancellation mechanism must be capable of interrupting a blocking render operation |
| **Heartbeat** | Executes a periodic no-op or self-ping API call within the Telegram Gateway process loop on a configurable interval (e.g., every 4–5 minutes) to prevent free-tier process suspension; logs each execution with a timestamp; log absence is the detection signal for keep-alive failure | Owned by the Telegram Gateway; trigger is a timer within the process loop; observability: structured log entry `{event=heartbeat, timestamp}` on each execution; absence of heartbeat log entries indicates keep-alive has stopped |
| **Data Export Agent** | Produces a portable structured dump of the embedded storage on a **timer-triggered basis within the single-process loop** (or, secondarily, on an externally triggered signal); writes the artifact to a developer-controlled external location; logs a structured record on completion and on failure; the export is **read-consistent**: a storage-level snapshot or brief write quiesce ensures the dump represents a single point in time | Export trigger: internal process timer fires daily; if the export destination is unavailable, the failure is logged with `{event=export_failure, reason, timestamp}` and retried on the next timer tick; the developer is expected to observe the absence of daily `export_success` log entries as the detection signal; export does not require bot quiescence — reads are performed under the same transaction/snapshot mechanism used for normal queries |
| **Secrets / Config Loader** | Reads the Telegram Bot API token from the environment variable at process startup; fails fast if the token is absent | Token must not appear in any log output, error stack trace, or debug dump |
| **Structured Logger** | Emits structured log records in **newline-delimited JSON format** for all failure paths, startup sweep events, purge audit entries, heartbeat ticks, export execution events, and key flow transitions; all records include `user_id`, `flow_name`, `event_type`, and `timestamp`; export and heartbeat records use `user_id=system` | JSON format enables log forwarding tooling to parse records without custom delimiters; free-tier stdout logs may be ephemeral; developer should configure log forwarding before launch |

---

## 5. Interaction Model

### 5.1 Interaction Patterns

| Pattern | Where used | Rationale |
|---|---|---|
| **Request / Response (synchronous, per-user serialized)** | All user-initiated flows (log, query, chart, delete, onboarding, help) | Telegram is inherently request/response; users expect a reply to every message; per-user in-process lock in the Dispatcher ensures sequential execution for the same user |
| **Event-driven (startup hook)** | Startup Sweep | Process lifecycle event triggers the sweep before message processing begins; no user request initiates it |
| **Timer-driven (in-process)** | Data Export Agent; Heartbeat | Internal process timers fire on schedule; decoupled from the message processing loop but within the same process |

### 5.2 Key Flows

---

**Flow A: Successful Metric Logging**
- **Trigger:** User sends a free-text message with no matching command keyword
- **Steps:**
  1. Telegram Gateway receives update → Dispatcher
  2. Dispatcher: acquires per-user lock → no Open PendingClarification → account Active → no keyword match → routes to Parse Engine
  3. Parse Engine extracts parameter name + value → creates ParseAttempt (outcome=success) → routes to Log Handler
  4. Log Handler (within a single storage transaction): checks if parameter exists (case-insensitive exact match); creates Parameter if new; appends LogEntry; updates `Parameter.last_entry_at`, `User.last_active_at`
  5. Log Handler sends confirmation message via Telegram Gateway
  6. Dispatcher: releases per-user lock
- **Failure points:** Storage write failure at step 4; parse false positive at step 3
- **Recovery:** On storage write failure → transaction rolled back; explicit error message returned; no confirmation sent; user instructed to retry; per-user lock released after error response

---

**Flow B: Parse Failure → Clarification → Resolution**
- **Trigger:** User sends a message that fails parse; user then responds to the clarification prompt
- **Steps (Failure):**
  1. Dispatcher: acquires per-user lock → routes to Parse Engine
  2. Parse Engine cannot extract pair → creates ParseAttempt (outcome=failure) → Clarification Handler
  3. Clarification Handler (within a single storage transaction): creates PendingClarification (state=Open); sends one-shot clarification prompt
  4. Dispatcher: releases per-user lock
- **Steps (Resolution):**
  5. User replies; Dispatcher: acquires per-user lock → detects Open PendingClarification → routes to Clarification Resolution Handler
  6. Parse Engine attempts parse on new message:
     - Success → PendingClarification → Resolved; LogEntry created; confirmation sent (all within one transaction)
     - Failure → PendingClarification → Abandoned; message re-enters dispatch from step 1 (may produce new PendingClarification)
  7. Dispatcher: releases per-user lock
- **Failure points:** User ignores the prompt (record abandoned on next message or startup sweep); repeated parse failure traps user in clarification loop
- **Recovery:** Clarification prompt must instruct the user to re-send with explicit `parameter name: value` format; user can always re-send original message to trigger a fresh attempt

---

**Flow C: Chart Generation**
- **Trigger:** User sends a `chart [name]` message
- **Steps:**
  1. Dispatcher: acquires per-user lock → keyword match → routes to Chart Handler
  2. Chart Handler resolves parameter name (case-insensitive exact match); fetches LogEntries
  3. If fewer than 2 data points → returns informative message; no chart generated; releases lock
  4. Chart Generator begins PNG rendering under preemptive 15-second cancellation context (e.g., goroutine with context cancel, thread with interrupt, async task with cancellation token)
  5. If cancellation deadline exceeded → rendering operation is forcibly interrupted (not merely flag-checked); error message returned; process unblocked
  6. On success → PNG sent as Telegram message; image discarded from memory
  7. Dispatcher: releases per-user lock
- **Failure points:** Insufficient data (handled); timeout exceeded (handled via preemptive cancellation); storage read failure; Telegram image send failure
- **Recovery:** All failure paths return explicit user-visible error messages; no silent failure; per-user lock released in all branches

---

**Flow D: Startup Sweep**
- **Trigger:** Bot process starts (planned restart or crash recovery)
- **Steps:**
  1. Secrets / Config Loader reads token; fails fast if absent
  2. Startup Sweep runs before Telegram Gateway opens:
     - Marks all Open PendingClarification records → Abandoned (idempotent: re-running on already-Abandoned records is a no-op)
     - For each User in Pending Deletion where window expired: purges all owned entities; sets User → Deleted; writes purge audit log entry (idempotent: re-running on already-Deleted users is a no-op)
  3. Telegram Gateway begins accepting updates; Heartbeat timer initialized
- **Failure points:** Sweep crash before completion; partial purge
- **Recovery:** Sweep operations are idempotent; if sweep fails on an unhandled exception, the process must not start (fail-fast); restart triggers a fresh sweep from the beginning; partial state from a prior failed sweep is safe because all sweep operations are idempotent by design

---

**Flow E: Account Deletion + Restoration**
- **Trigger:** User sends `delete account`
- **Steps:**
  1. Dispatcher routes to Account Deletion Handler
  2. Handler sends confirmation prompt with explicit 3-day window and exact expiry date/time
  3. User confirms → User set to Pending Deletion; `deletion_requested_at` set; confirmation message sent
  4. Within 3-day window: `restore account` → Account Restoration Handler clears flags; User returns to Active
  5. After window: Startup Sweep executes purge (Flow D, step 2)
- **Failure points:** User misunderstands the 3-day window; bot offline when window expires (purge deferred to next startup)
- **Recovery:** Confirmation message must state exact expiry timestamp; deferred purge on next startup sweep is the accepted behavior under free-tier operational model

---

**Flow F: Data Export**
- **Trigger:** Internal process timer fires (daily interval); or, secondarily, an external signal to the process (e.g., OS signal, admin endpoint)
- **Steps:**
  1. Data Export Agent timer fires within the bot process loop
  2. Agent acquires a storage-level read snapshot (using the embedded storage's read transaction or equivalent) to ensure a consistent point-in-time dump; ongoing writes from message processing are not blocked
  3. Agent serializes all entities (User, Parameter, LogEntry, ParseAttempt, PendingClarification, OnboardingSession) into a portable structured format (e.g., JSON or CSV)
  4. Agent writes the artifact to the developer-configured external location
  5. On success: logs `{event=export_success, entity_count, export_destination, timestamp}`
  6. On failure at step 4 (write to external location fails): logs `{event=export_failure, reason, timestamp}`; retries on the next timer tick; **no silent failure**; the developer detects failure by absence of daily `export_success` log entries
- **Failure points:** External destination unavailable; storage read snapshot failure; process terminates mid-export
- **Recovery:** Failure at any step produces a structured log entry; the prior export artifact is not overwritten until the new artifact is successfully written; a mid-export process termination leaves the prior artifact intact at the external destination; on restart, the export timer re-initializes and fires at the next scheduled interval

---

**Flow G: Onboarding (with Operator Disclosure Atomicity)**
- **Trigger:** First message from a new Telegram ID
- **Steps:**
  1. Dispatcher routes to Onboarding Handler (no User record found)
  2. Onboarding Handler: **writes User record and sets `operator_disclosure_delivered = false` in a single storage transaction first**; transaction commits before any Telegram message is sent
  3. Handler sends the welcome message (which includes the operator disclosure statement)
  4. On successful Telegram send: Handler **updates `operator_disclosure_delivered = true` in storage**
  5. On Telegram send failure: `operator_disclosure_delivered` remains `false`; on the user's next message, the Dispatcher detects the undelivered disclosure flag and re-triggers the welcome message send before routing to normal flow
- **Failure contract:**
  - If storage write at step 2 fails → no message sent; user receives an error; onboarding retried on next message
  - If Telegram send at step 3 fails → `operator_disclosure_delivered = false` remains in storage; re-delivery attempted on next interaction
  - If storage update at step 4 fails after successful send → `operator_disclosure_delivered = false` remains; re-delivery will be attempted (message is delivered twice); this is the accepted safe-side behavior — duplicate disclosure is preferable to missed disclosure

---

## 6. Data Strategy (Conceptual)

| Entity / Domain Data | Owner Component | Consistency Needs | Lifecycle | Risks |
|---|---|---|---|---|
| User | Storage Layer | Strong — User ID is the root of all data isolation; state transitions must be atomic; `operator_disclosure_delivered` flag update is separate from the initial User record creation (see Flow G failure contract) | New → Onboarding → Active → Pending Deletion → Deleted (terminal) | Telegram ID reassignment (highly unlikely per A-01); orphaned User records if Telegram ID changes |
| Parameter | Storage Layer | Strong — creation must be idempotent (per-user lock in Dispatcher prevents concurrent same-user creation races; Section 8.8); deletion is irreversible | Non-existent → Active → Deleted (terminal, hard-delete) | Accidental deletion is permanent; auto-creation from mistyped messages may pollute the parameter list |
| LogEntry | Storage Layer | Append-only; immutable once created; written in the same transaction as `Parameter.last_entry_at` and `User.last_active_at` updates | Recorded → Purged (only on parent Parameter deletion or User purge) | No edit mechanism; errors require a new LogEntry; purge is permanent |
| ParseAttempt | Storage Layer | Append-only audit record; no updates | Recorded (terminal, immutable) | Purged only on User account deletion; volume grows linearly with usage but is trivially small at target scale |
| PendingClarification | Storage Layer | Transient; state transitions (Open → Resolved / Abandoned) must be atomic with message processing; per-user Dispatcher lock prevents concurrent transitions | Open → Resolved or Abandoned (both terminal) | Stale Open records cleaned up by Startup Sweep; one-shot model means lost data if user ignores prompt |
| DeletionConfirmation | Storage Layer | Transient; stores the pending two-step deletion confirmation context; created when user issues the first deletion command; consumed (deleted) when user confirms or cancels; **survives restarts** (written to storage, not held in memory) | Created → Confirmed (terminal, triggers deletion flow) or Expired (terminal, cleared by Startup Sweep) | On restart between step 1 and step 2: record survives in storage; user's confirmation after restart resolves against the stored record as normal; no UX break |
| OnboardingSession | Storage Layer | `operator_disclosure_delivered` flag must be set to `false` in the same transaction as the User record creation; updated to `true` only after confirmed Telegram message send | In Progress → Completed | Incomplete disclosure flag is detectable and triggers re-delivery on next interaction |
| Chart Image | Chart Generator (in-memory only) | No persistence required; generated on demand; discarded after Telegram delivery or on timeout cancellation | Ephemeral (in-memory, delivery-scoped) | Memory pressure on free-tier hosts during chart generation; enforced by timeout |
| Export Artifact | Data Export Agent | Point-in-time snapshot under a read transaction; consistency at export time; prior artifact not overwritten until new artifact successfully written | Created on schedule; stored externally; replaces prior snapshot on success | Export covers all entities; developer responsible for verifying completeness and restorability; silent export failure must be detectable via log absence |

---

## 7. Non-Functional Requirements Coverage

### 7.1 NFR Mapping

| NFR Category | Requirement | Architectural Tactic | Trade-off |
|---|---|---|---|
| Performance — text latency | ≤ 3 s for all text responses under normal load | Single-process synchronous handling; embedded storage eliminates network I/O for reads/writes | Cold-start latency on free-tier exceeds this target; excluded from bound by design |
| Performance — chart latency | ≤ 15 s; hard timeout enforced | Chart Generator runs in-process with **preemptive cancellation** (not cooperative flag-checking); image held in memory only | Preemptive cancellation requires runtime support for interrupting a blocking call; failure returns error, not partial image |
| Performance — cold start | ≤ 60 s after idle | Heartbeat component (owned by Telegram Gateway) executes periodic no-op API calls on a timer to prevent process suspension | Heartbeat consumes a small amount of hosting quota and API rate-limit budget; without it, cold-start latency is uncontrolled |
| Availability | Best-effort > 90% daily; no formal SLA | Free-tier hosting accepted; manual monitoring by developer; Heartbeat doubles as a liveness signal (log absence = potential cold-start or process failure); startup sweep ensures clean state on restart | No automated failover; single point of failure is the hosting environment |
| Data Durability | RPO = 24 hours | Daily data export to external location via internal process timer; structured log records confirm export execution; portable structured dump; developer-defined restore procedure | Restore is manual and requires developer action; data loss of up to 24 hours is accepted; silent export failure is detectable via log absence |
| Data Isolation | Mandatory User ID scoping on all queries | Storage Layer enforces User ID as a mandatory filter parameter; no unscoped query path exists | Requires disciplined enforcement at every query site; no framework-level enforcement |
| Input Sanitization | All user input parameterized before storage | Storage Layer accepts only structured parameters, never raw text interpolation | Developer must not bypass the Storage Layer for ad hoc queries |
| Secrets | Token never in source, logs, or version control | Secrets / Config Loader reads from environment variable; Structured Logger explicitly excludes the token value | Developer must configure hosting environment variable before deployment |
| Error Communication | Every failure path returns a user-visible message; no silent drops | Each Command Handler has an explicit failure branch; Telegram Gateway retries on rate-limit before surfacing error | Failure branches add code paths that must be tested; rate-limit retry adds latency |
| Concurrency | Per-user message serialization | **Dispatcher owns per-user in-process lock**: acquired at dispatch entry, released after handler completes and all storage writes return; second message from same user waits in the lock queue | Lock acquisition adds minor overhead; per-user contention is negligible at target scale; lock must be released in all branches including error paths |

### 7.2 NFR Unknowns

| Unknown | Decision Blocked |
|---|---|
| Exact value of N for history query (A-08) | History Handler cannot be fully implemented until N is defined; verbose responses risk Telegram message length limits |
| Telegram update delivery mechanism: polling vs. webhook (SD-10, A-11) | Telegram Gateway design; hosting platform requirements (webhook requires public HTTPS endpoint); cold-start behavior differs between the two |
| Exact parameter name length bound (Section 8.7) | Input validation cannot be implemented without a defined upper limit; recommended ≤ 100 characters but not yet confirmed |
| Permitted character set for parameter names (Section 8.7) | Rejection logic cannot be implemented; sanitization scope is undefined |
| Log forwarding / export mechanism for structured logs (Section 11.6) | Without this, pre-restart error history is ephemeral; retrospective error analysis is impossible |
| Data export destination (Section 8.3, A-10) | Export Agent cannot be configured; RPO guarantee depends on export running daily to a confirmed location |

---

## 8. Scalability & Performance Reasoning

**Expected load:** ≤ 100 users × ~5 messages/day = ~500 messages/day ≈ 0.006 messages/second average; peak bursts estimated at 5–10 messages/minute. This is below any meaningful threshold for a single-process system.

**Bottlenecks:**
- **Chart generation** is the only CPU-intensive operation. At this load, concurrent chart requests from different users are handled sequentially in the single-process model; the 15-second preemptive timeout prevents any single request from blocking the process indefinitely. Per AD-4, chart generation for User A does block User B's message processing in a strict single-threaded synchronous model — at 100 users, this is an accepted and expected trade-off.
- **Cold-start latency** is the primary user-perceived performance risk. Free-tier process suspension after idle is the most probable cause of > 3 s response latency in practice. The Heartbeat component is the primary mitigation.
- **Telegram API send latency** is outside system control. Outbound message delivery time is not included in the 3-second target (which covers system processing, not network delivery).
- **Per-user lock contention** is negligible at target scale. A single user sending messages faster than the system can process them is the only contention scenario; at ~5 messages/day per user, lock wait time is effectively zero.

**Caching boundaries (conceptual):** No caching is warranted at this scale. All reads from embedded local storage are fast enough without a cache layer. Introducing a cache would add complexity with no measurable benefit.

**Queueing needs (conceptual):** Per-user message serialization (Section 8.8) is implemented as a **per-user in-process lock owned by the Dispatcher**. The Dispatcher acquires the lock for a user's Telegram ID before routing and releases it only after the handler and all storage writes complete. A second message arriving for the same user while the lock is held waits in a minimal in-process queue. No external queue is needed. This mechanism is the correctness guarantee for PendingClarification state transitions and Parameter creation idempotency.

**Growth ceiling:** This architecture is not designed to scale beyond ~1,000 users. If the user base were to grow significantly, embedded co-located storage, single-process concurrency, and free-tier hosting would all become bottlenecks. No scalability path is architected intentionally, consistent with the project's scope boundary.

---

## 9. Reliability & Failure Scenarios

| Scenario | Impact | Detection | Mitigation | Residual Risk |
|---|---|---|---|---|
| Telegram platform outage | System completely inaccessible to all users | No inbound messages received; manual developer check | Monitor Telegram status; no technical mitigation possible; document posture for users | Full service loss for outage duration; no fallback channel |
| Free-tier hosting process suspension (cold start) | First message after idle receives delayed response (up to 60 s) | Absence of Heartbeat log entries; user complaint | Heartbeat component executes periodic no-op API call on a timer (e.g., every 4–5 minutes) to prevent suspension; cold-start latency excluded from 3 s target | Unavoidable without a paid hosting tier; Heartbeat reduces but does not eliminate cold starts |
| Heartbeat stops executing | Cold-start risk increases; no proactive prevention of process suspension | Absence of `{event=heartbeat}` log entries in structured logs | Developer reviews Heartbeat log entries as part of daily operational check | If log forwarding is not configured, Heartbeat failure is invisible until a user reports a cold-start |
| Free-tier hosting eviction or storage quota exceeded | Data loss or service termination | Storage utilization monitoring (manual at 80% threshold) | Daily data export to external location; developer-defined restore procedure | Up to 24 hours of data loss if export is not current; restore is fully manual |
| Data Export Agent fails to write to external location | RPO degrades; export artifact not updated | Absence of daily `{event=export_success}` log entries; `{event=export_failure}` log entry | Structured log entry on failure; retry on next timer tick; developer monitors for export_success absence | If export fails silently for multiple days, RPO degrades without data loss detection until a restore is needed |
| Data Export Agent: process terminates mid-export | Export artifact partially written or corrupt at destination | Absence of `{event=export_success}` for that cycle; developer observes stale artifact at destination | Prior artifact not overwritten until new artifact is fully written; on restart, export timer re-initializes | At most one export cycle lost; prior artifact remains intact |
| Storage write failure | Log entry or state change not persisted; user receives error message and must retry | Explicit error message returned to user; error logged with flow name and error type | Structured error response; no false confirmation sent; transaction rolled back if multi-entity write | If the failure is persistent (storage corruption), user data may be unrecoverable until restore from export |
| Storage read failure | Query or chart returns error instead of data | Explicit error message returned to user | Structured error response; no empty result returned silently | User cannot access history or charts until storage recovers |
| Storage file corruption (not just absence) | Potentially irrecoverable data loss; export artifact may also be from a pre-corruption snapshot | Storage open/read failure at startup or runtime; developer investigation required | Daily export artifact provides last-known-good state; developer must restore from artifact; post-restore, accept data loss up to last export | Export artifact itself may contain data up to 24 hours before corruption; any data written after the last successful export is unrecoverable |
| Chart generation timeout (preemptive cancellation fails) | Bot process becomes unresponsive; all subsequent messages blocked | No response delivered; user complaint | Preemptive cancellation mechanism must be validated to interrupt a blocking render call; language/runtime must support forced interruption | If the implementation incorrectly uses cooperative cancellation on a blocking call, the process blocks; this must be caught in implementation testing |
| Chart generation timeout (normal — cancellation succeeds) | User receives error message; bot process unblocked | Timeout enforcement mechanism terminates the generation process | Hard 15-second preemptive timeout; error message returned; no blocking | Chart is unavailable for that request; user can retry |
| Partial storage write (e.g., LogEntry written but `last_entry_at` not updated) | Inconsistent entity state; observability signals may be slightly off | Manual inspection of storage state | All multi-entity writes executed within a single storage transaction; fail entire operation if any part fails | Transaction support is a hard requirement for storage selection; if the embedded storage engine does not support transactions, it must not be selected |
| Stale Open PendingClarification after crash | First message from affected user routed incorrectly to clarification handler | Startup Sweep marks all Open → Abandoned before accepting messages | Startup Sweep runs before Telegram Gateway opens; operations are idempotent | User's open clarification is silently abandoned; user must re-send original message |
| Startup Sweep fails partway through on unhandled exception | Partially abandoned PendingClarification or partially purged User records remain | Process fails to start (fail-fast on sweep exception); developer observes startup failure | Sweep operations are idempotent; re-running sweep on already-processed records is a no-op; restart triggers fresh sweep | If idempotency is incorrectly implemented, repeated sweep runs could produce inconsistent state; must be validated |
| Bot offline when account deletion window expires | Purge delayed until next startup | Startup Sweep checks deletion_requested_at timestamps on every startup | Deferred purge on next startup sweep | User data persists slightly longer than the 3-day window; accepted under free-tier operational model |
| Concurrent same-user messages (hosting delivers parallel execution contexts) | Duplicate Parameters or LogEntries; inconsistent PendingClarification state | Duplicate records visible in storage | Per-user lock in Dispatcher prevents concurrent same-user message processing within the process; risk only if hosting delivers the same user's messages to separate parallel processes | If the hosting environment spawns multiple processes, per-user lock does not span processes; this risk is accepted and must be verified against the selected hosting platform |
| Onboarding Telegram send fails after User record created | `operator_disclosure_delivered = false` in storage; disclosure may not reach user | Dispatcher detects undelivered disclosure flag on next interaction; re-triggers welcome message | Re-delivery attempted on next user interaction; duplicate disclosure preferred over missed disclosure | If user never sends another message, disclosure remains undelivered; this is accepted as a limitation of best-effort Telegram delivery |
| Onboarding: storage flag update fails after Telegram send succeeds | Disclosure sent to user but `operator_disclosure_delivered = false` in storage; re-delivery will occur on next interaction | Developer can observe duplicate welcome messages in Telegram | Re-delivery will occur once on next interaction; second disclosure is redundant but not harmful | Duplicate disclosures are the safe-side failure mode; accepted |
| Two-step deletion confirmation state lost on restart | **DeletionConfirmation record survives restart in storage** (it is not held in memory); user's confirmation after restart resolves against the stored record normally | No UX break; user flow continues as expected | DeletionConfirmation is a first-class storage entity with the same durability guarantees as other entities | No residual risk; by storing the confirmation context, restart does not affect the two-step flow |
| Telegram rate limit exceeded on outbound messages | Message delivery delayed or failed | Rate limit error from Telegram API | Retry with brief delay before surfacing error to user; no silent drop | If retry limit is exhausted, user receives an error; message is not retried after the error is surfaced |
| Data isolation defect (missing User ID filter) | Cross-user data exposure | Developer code review; storage query audit | Storage Layer enforces User ID as a mandatory filter; architectural boundary prevents unscoped queries | A query logic bug that bypasses the Storage Layer interface could expose data; requires developer discipline |
| Telegram account ID reused by a different person | New Telegram account holder accesses prior user's data | Not automatically detectable by the system | No technical mitigation possible at this architecture level; risk is accepted and disclosed as a known limitation | PII exposure via Telegram ID recycling; Telegram's ID reassignment rate is extremely low in practice |

---

## 10. Security & Compliance Baseline

| Area | Threat / Risk | Control | Notes |
|---|---|---|---|
| Data access — cross-user | Query logic defect exposes one user's data to another | Storage Layer enforces mandatory User ID scoping on every read/write operation; no unscoped query path exists | Highest-impact security failure mode for this system; must be reviewed in any code change touching storage queries |
| Data access — operator | Developer has unrestricted access to all raw user data | Operator disclosure delivered in onboarding welcome message (Flow G); `operator_disclosure_delivered` flag tracked on OnboardingSession; re-delivery on failure | No technical access control separates developer from user data; trust-based model for a closed personal group |
| Storage file access control | Embedded storage file contains all user data; filesystem exposure on hosting platform | Storage file should be placed in a directory not accessible to other tenants or web-served paths; hosting platform filesystem isolation is a deployment prerequisite | Developer must verify that the hosting platform's filesystem is not world-readable or exposed to other tenants before deployment |
| Secrets — Telegram Bot API token | Token leaked via source code, version control, or log output | Token stored as hosting environment variable only; Structured Logger explicitly excludes token value from all output; Secrets / Config Loader fails fast if token absent | Developer must verify that the hosting platform supports environment variable injection (A-09) before deployment |
| Input injection — storage queries | User-supplied parameter names or log values injected into storage queries | All user input parameterized or sanitized before any storage operation; raw text never interpolated into queries; enforced at the Storage Layer boundary | Technology-class agnostic requirement; applies regardless of storage mechanism selected |
| PII handling | No PII collected; identity model is Telegram ID only | No real name, email, or phone number stored or processed; Telegram ID is the sole identifier | If a user's Telegram account is compromised, their bot data is accessible to the attacker via that account |
| Telegram account ID reuse | Numeric Telegram ID reassigned to a different person after account deletion | No technical mitigation; rate of Telegram ID recycling is extremely low | Acknowledged as a known residual risk; developer should document this limitation for users |
| Non-text input | Malformed or unexpected Telegram message types reach parse engine | Non-text input rejected at the pre-dispatch gate before any processing; rejection message returned; no ParseAttempt created | Voice notes, images, stickers, forwarded media, locations, and contacts are all rejected at this gate |
| Demo / synthetic data contamination | Synthetic onboarding data appears in real analytics flows | All demo entities tagged `is_synthetic = true`; all analytics flows (chart, history, compare) filter out synthetic entries | Tagging must be applied at creation time; no mechanism to retroactively tag if missed |
| Per-user abuse (message flood) | A single malicious or malfunctioning user floods the bot with inbound messages; monopolizes the per-user lock queue; creates excessive ParseAttempt records | No per-user rate limiting is architecturally defined; the per-user lock naturally serializes processing but does not prevent record bloat | At ≤ 100 users in a known personal group, abuse risk is low; the developer should be aware that ParseAttempt volume grows unbounded per user and is only purged on account deletion |
| Export artifact security | Export artifact contains all user data; written to developer-controlled external location | Export destination is developer-configured; developer is responsible for ensuring the destination is not publicly accessible | Developer must not write the export to a public URL, unencrypted email, or shared drive accessible to unintended parties |
| Auditability | No audit trail for purge events or operator actions | Startup Sweep writes a structured audit log entry per purge event (User ID, `purge_executed_at`, `deletion_requested_at`) | Log durability risk on free-tier hosting; developer should configure log forwarding to preserve audit trail across restarts |

---

## 11. Observability Baseline

### 11.1 Signals

**Metrics (SLO candidates):**
- Parse failure resolution rate: `(ParseAttempt.outcome=success count + PendingClarification.state=resolved count) / total ParseAttempts` over rolling 30-day window; target > 80%
- User Return Rate: distinct users with interaction in week 2 / distinct users with interaction in week 1; target > 40%
- Parameter Retention Rate: parameters with a LogEntry in days 25–35 / parameters created before day 5; target > 50%
- Bot availability: binary daily check via direct interaction and Heartbeat log presence; target > 90% daily availability
- Storage utilization: percentage of free-tier quota consumed; action threshold at 80%

**Developer query mechanism:** The developer queries the embedded storage directly using ad hoc SQL (or equivalent) and reads structured log output (JSON lines) to compute the above metrics. No external dashboarding tooling is required. The developer should have at least one saved query per metric above before launch, so that weekly review does not require composing queries from scratch.

**Logs (structured — newline-delimited JSON):**
- Every failure path: `{event=error, user_id, flow_name, error_type, timestamp}`
- Every startup sweep action: `{event=purge, user_id, purge_executed_at, deletion_requested_at}` or `{event=abandon, clarification_id, user_id, timestamp}`
- Every chart generation timeout: `{event=chart_timeout, user_id, parameter_name, timeout_at}`
- Every Telegram rate-limit retry and ultimate failure: `{event=rate_limit, user_id, flow_name, retry_count, outcome, timestamp}`
- Every Heartbeat execution: `{event=heartbeat, timestamp}` — absence of this entry indicates process suspension or Heartbeat failure
- Every Data Export execution: `{event=export_success, entity_count, export_destination, timestamp}` or `{event=export_failure, reason, timestamp}` — absence of `export_success` entries for > 24 hours indicates RPO risk
- Token value must never appear in any log record

**Traces (critical paths):**
- End-to-end latency for the log flow (inbound message → per-user lock acquired → storage write → confirmation sent → lock released)
- End-to-end latency for the chart flow (inbound message → lock acquired → chart generation → image sent or timeout → lock released)
- Startup sweep execution time (startup → sweep complete → gateway open)
- In a single-process system without a tracing framework, traces are approximated by logging timestamps at entry and exit of each phase; the developer computes latency from log timestamps

### 11.2 Operational Dashboards (conceptual)

The developer queries the embedded storage and log output directly — no external dashboarding tooling is required or defined.

| What to monitor | Signal source | Action trigger |
|---|---|---|
| Parse failure resolution rate (weekly) | ParseAttempt + PendingClarification tables (ad hoc SQL query) | < 80% → review parse logic; check user message patterns |
| User return rate (weekly cohort) | User table (`first_seen_at`, `last_active_at`) (ad hoc SQL query) | < 40% → review onboarding and usability |
| Parameter retention rate (day 30) | Parameter + LogEntry tables (ad hoc SQL query) | < 50% → investigate which parameters are abandoned and why |
| Bot liveness | Heartbeat log entries (JSON lines filter) + manual daily direct interaction | Absent heartbeat entries or no response → investigate hosting status; trigger restart |
| Export execution (daily) | Structured log — `export_success` / `export_failure` entries | Absent export_success for > 24 hours → investigate export agent; check external destination; verify RPO |
| Storage quota | Hosting platform console | > 80% → initiate data export and cleanup |
| Error rate by flow | Structured log — `event=error` entries grouped by flow_name | Recurring errors in a single flow → investigate and fix before next deploy |
| Pending deletion records | User table (`is_pending_deletion = true`) (ad hoc SQL query) | Records stuck beyond 3-day window → investigate startup sweep execution |

---

## 12. Architectural Decisions (ADR-style)

### AD-1: Telegram Update Delivery Mechanism (Polling vs. Webhook)

- **Decision:** Not yet resolved — recorded as an open architectural decision (linked to SD-10 in System v0.3)
- **Alternatives considered:**
  - *Long-polling:* Bot process actively polls Telegram API for updates; works on any hosting environment; no public HTTPS endpoint required; persistent connection must be maintained
  - *Webhook:* Telegram pushes updates to a registered HTTPS endpoint; requires a public URL and valid TLS certificate; not available on all free-tier platforms; eliminates the polling loop
- **Rationale:** The choice depends on the hosting platform selected by the developer. Polling is the safer default for free-tier environments where public HTTPS endpoints are not guaranteed. Webhook is preferable if a public endpoint is available, as it eliminates idle polling overhead.
- **Trade-offs:** Polling keeps a persistent connection alive (helpful for cold-start reduction); webhook requires infrastructure configuration but is more resource-efficient when available
- **Consequences:** Must be resolved before deployment. Telegram Gateway component design depends on this decision.
- **Linked NFR/Business Goal:** Cold-start latency; hosting free-tier constraint; A-11

---

### AD-2: Single-Process Architecture

- **Decision:** The bot runs as a single OS process. All components (Dispatcher, Parse Engine, Command Handlers, Storage Layer, Chart Generator, Startup Sweep, Heartbeat, Data Export Agent) execute within this process. There is no inter-process communication, no message broker, no separate service for storage.
- **Alternatives considered:**
  - *Multi-process or microservice split:* Separate processes for message handling, storage, and chart generation; enables independent scaling and fault isolation
  - *Serverless / function-per-flow:* Each command flow is a separate function invocation; eliminates idle resource consumption. **Rejected on a deeper architectural basis:** stateless function invocations cannot enforce per-user message serialization without an external distributed lock or queue — which violates the zero-external-dependency constraint (AD-3). A different hosting arrangement does not resolve this incompatibility.
- **Rationale:** At ≤ 100 users with ~500 messages/day, multi-process complexity provides no practical benefit. Free-tier hosting typically provides a single container or instance. Single-process eliminates inter-process communication failures and reduces operational surface. Serverless is incompatible with per-user serialization without external state.
- **Trade-offs:** A crash in one component (e.g., chart generation) can affect the entire process if not properly isolated via preemptive timeout enforcement; no independent scaling; cannot deploy individual components separately
- **Consequences:** Chart Generator must be isolated via preemptive timeout to prevent process blocking. Startup Sweep must complete before the process accepts messages. Heartbeat and Data Export Agent run as timer-driven loops within the same process. All state transitions rely on in-process sequencing rather than distributed coordination.
- **Linked NFR/Business Goal:** Near-zero infrastructure cost; simplicity; personal-scale target; per-user serialization correctness

---

### AD-3: Embedded Relational Storage Co-located with Bot Process (Transaction Support Required)

- **Decision:** All persistent entities are stored in an embedded relational database co-located with the bot process on the hosting platform. **Transaction support is a mandatory selection criterion**: the chosen embedded storage engine must support atomic multi-entity writes. No external database service is used.
- **Alternatives considered:**
  - *External managed database (e.g., free-tier cloud DB):* Separates storage from compute; survives process restarts; adds a network dependency and a second free-tier service
  - *File-based non-relational storage (e.g., JSON files):* Simpler to set up; no relational querying; no transaction support; fragile under concurrent writes — rejected because transaction support is required for atomic multi-entity writes
- **Rationale:** Embedded relational storage eliminates network latency for all storage operations (supporting the 3-second latency target), eliminates a second external service dependency, and provides relational querying and **transaction support required for atomic multi-entity writes** (LogEntry + `last_entry_at` updates, PendingClarification state transitions, onboarding flag writes). At the target data volume (~182,500 records/year), embedded storage is fully sufficient.
- **Trade-offs:** Storage is tied to the hosting environment; data is lost if the hosting platform evicts the process and discards the filesystem (mitigated by daily export); no independent scaling of storage
- **Consequences:** Daily export is mandatory as the sole disaster recovery mechanism. Developer must verify that the hosting platform provides persistent filesystem storage across restarts (not all free-tier platforms guarantee this). **Transaction support is confirmed as a hard requirement**: any embedded storage engine that does not support transactions must not be selected.
- **Linked NFR/Business Goal:** Near-zero infrastructure cost; RPO 24 hours; single-process architecture (AD-2); multi-entity write atomicity
- **Status:** Confirmed — transaction support is a mandatory selection criterion

---

### AD-4: Synchronous Request / Response per Message with Per-User Lock

- **Decision:** Each inbound Telegram message is processed to completion (storage writes, response sent) before the next message from the same user is accepted. The Dispatcher owns per-user serialization via an in-process lock.
- **Alternatives considered:**
  - *Async processing with a job queue:* Inbound messages enqueued; workers process asynchronously; decouples receipt from processing; enables parallelism across users
  - *Async within a message (non-blocking I/O):* Single-threaded event loop with async/await; allows I/O overlap within a single message but does not add per-user parallelism. **Note:** For the chart flow specifically, non-blocking async execution could allow the bot to process other users' messages while chart generation runs. In a strict single-threaded synchronous model, chart generation for User A blocks User B's processing. At 100 users with ~5 messages/day, this is an accepted and expected trade-off — the 15-second preemptive timeout bounds the worst-case blocking duration.
- **Rationale:** At the target scale and message volume, synchronous per-user serialization is simpler, avoids race conditions on PendingClarification state and Parameter creation, and meets the 3-second latency target without optimization. Async complexity is not justified.
- **Trade-offs:** A slow operation (e.g., chart generation) blocks subsequent messages from all users (not just the same user) in a strict single-threaded model; chart generation preemptive timeout is critical to bound this blocking
- **Consequences:** Chart Generator preemptive timeout enforcement is non-optional. Per-user lock in Dispatcher is the correctness guarantee for PendingClarification and Parameter creation. Race condition risk accepted for edge cases where hosting delivers parallel execution contexts for the same user (see UA-03).
- **Linked NFR/Business Goal:** Concurrency NFR (Section 8.8); correctness over throughput; personal-scale target

---

### AD-5: One-Shot Clarification Model

- **Decision:** When the Parse Engine fails to extract a valid (name, value) pair, exactly one clarification prompt is sent. The next message from the user is tested as a clarification response; if it fails to parse, the PendingClarification is abandoned and the new message enters normal dispatch.
- **Alternatives considered:**
  - *Multi-turn clarification dialog:* System asks follow-up questions until a valid entry is obtained; provides better UX for confused users; significantly increases state complexity
  - *Silent drop:* Failed parse messages are discarded silently; no state created; simplest implementation; violates the "no silent drop" NFR
- **Rationale:** Confirmed as a design decision in Business v0.3 (D-03). Perfect parsing is not required; a single clarification prompt is sufficient and avoids open-ended conversational state.
- **Trade-offs:** Users who ignore the prompt lose the original entry silently; the clarification prompt must clearly instruct the user to re-send; high parse failure rates compound this risk
- **Consequences:** Parse failure resolution rate must be instrumented from day one. The clarification prompt text must include explicit instructions for re-sending. Startup Sweep must abandon stale Open records on restart.
- **Linked NFR/Business Goal:** Parse failure resolution rate > 80%; D-03; personal utility

---

### AD-6: No External Alerting or Notification Mechanism

- **Decision:** The system produces no outbound notifications, alerts, or reminders. All observability is pull-based (developer queries storage and logs directly).
- **Alternatives considered:**
  - *Automated error alerting (e.g., email or Telegram message to developer on error):* Provides proactive failure detection; requires additional outbound channel; adds complexity
  - *Scheduled reminders to users:* Prompts users to log; increases engagement; confirmed out of scope (D-05)
- **Rationale:** Threshold alerts and push notifications are confirmed out of scope (D-05). At this scale, manual daily developer interaction combined with Heartbeat log monitoring is the availability detection mechanism. Adding alerting infrastructure would violate the near-zero infrastructure cost constraint.
- **Trade-offs:** Extended outages may go undetected until the developer's daily check; no automated recovery
- **Consequences:** Developer must interact with the bot at least once daily and review Heartbeat and export log entries. Log forwarding mechanism (if configured) is the closest approximation to proactive error visibility.
- **Linked NFR/Business Goal:** D-05; near-zero cost; availability target > 90% daily

---

### AD-7: Heartbeat as an Owned Reliability Mechanism (Not a Monitoring Mechanism)

- **Decision:** Cold-start prevention is the responsibility of a dedicated **Heartbeat** component owned by the Telegram Gateway. Heartbeat is a reliability mechanism (prevents process suspension) — not an alerting or notification mechanism — and is architecturally distinct from AD-6.
- **Alternatives considered:**
  - *External scheduled ping (e.g., cron job pinging the bot endpoint):* Requires external infrastructure; violates zero-external-dependency constraint
  - *No keep-alive:* Cold-start latency is uncontrolled; High probability cold-start risk identified in the reliability section
- **Rationale:** The Heartbeat mechanism is the primary mitigation for the most probable high-impact availability risk. It runs inside the existing single-process loop with zero additional infrastructure. Its log output doubles as an availability signal.
- **Trade-offs:** Heartbeat consumes a small amount of API rate-limit budget; if the Heartbeat timer itself fails silently, cold-start risk resurfaces undetected
- **Consequences:** Heartbeat log entries (`{event=heartbeat, timestamp}`) must be present in every operational session. Absence is the detection signal for Heartbeat failure. Developer includes Heartbeat log presence in the daily operational check.
- **Linked NFR/Business Goal:** Cold-start latency NFR; > 90% daily availability target

---

## 13. Risks & Open Questions

### 13.1 Architecture Risks

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| Hosting platform does not provide persistent filesystem across restarts | All persisted data lost on restart; RPO violated | Medium — varies by free-tier platform | Verify filesystem persistence guarantees before deployment; configure daily export before launch |
| Chart generation preemptive cancellation incorrectly implemented (cooperative flag-check used instead) | Bot process blocks on a rendering call beyond 15 s; all subsequent messages delayed or lost | Low-Medium — requires implementation error | Preemptive cancellation mechanism must be validated in testing to interrupt a blocking render call; cooperative cancellation is explicitly prohibited |
| Per-user serialization not guaranteed by hosting environment (concurrent delivery to parallel processes) | Race conditions on PendingClarification and Parameter creation | Low-Medium — depends on hosting platform's update delivery behavior | Verify hosting environment delivers messages to a single process instance; document accepted risk if multi-process delivery is unavoidable |
| Startup Sweep idempotency incorrectly implemented | Repeated sweep runs produce inconsistent state (double-purge, double-abandon) | Low — requires implementation error | Sweep operations must be idempotent by design; validate in testing |
| Structured log loss on process restart (free-tier ephemeral stdout) | Retrospective error analysis impossible; Heartbeat and export audit trail lost | High — free-tier stdout is frequently discarded on restart | Configure log forwarding before launch; document that pre-restart error history is ephemeral (Section 11.6) |
| Token leaked via error stack trace or debug log | Bot suspended by Telegram; security incident | Low — requires implementation error | Structured Logger explicitly excludes token; code review for any log statement that could include environment variables |
| MVP scope not formally defined before architecture is built upon | Rework if full-scope design components are built but later excluded | Medium | Business Open Question 1 (minimum viable scope) must be resolved before implementation begins |
| Export failure undetected for multiple days | RPO degrades; data recovery window shrinks | Low-Medium — only if developer does not review export logs | Developer monitors daily `export_success` log entries; export failure is logged and not silent |

### 13.2 Open Questions

1. **What is the Telegram update delivery mechanism: polling or webhook?** (SD-10, A-11) — blocks Telegram Gateway component design; affects hosting requirements; must be resolved before deployment.

2. **What hosting platform will be used?** — determines filesystem persistence guarantees (impacts data durability strategy), environment variable support (impacts secrets handling), and public HTTPS endpoint availability (impacts AD-1).

3. **What is the fixed N for history queries (last N entries)?** (A-08) — blocks History Handler implementation; affects Telegram message length risk.

4. **What is the exact parameter name length bound and permitted character set?** (Section 8.7) — blocks input validation implementation in the Parse Engine and Storage Layer.

5. **What is the minimum viable scope?** (Business Open Question 1) — if MVP scope is subsequently constrained, components designed for full scope (e.g., period comparison, account deletion) may be deferred; architecture should not be treated as final until this is resolved.

6. **Where does the daily export artifact go?** (Section 8.3, Data Export Agent) — blocks Data Export Agent configuration; RPO guarantee depends on this being operational before launch.

7. **Will the developer configure log forwarding before launch?** — if not, all error history, Heartbeat records, export execution records, and purge audit records are ephemeral across restarts; developer accepts reduced retrospective observability.

---

## 14. Traceability Matrix

| Business Goal | Architectural Goal | Component | Key Decision | Risk |
|---|---|---|---|---|
| Personal utility — reduce logging friction | Low-friction message handling; ≤ 3 s text response | Telegram Gateway, Dispatcher (per-user lock), Parse Engine, Storage Layer | AD-2 (single-process), AD-3 (embedded storage), AD-4 (synchronous per-message) | Cold-start latency on free-tier; parse false negatives increase friction |
| Personal utility — parse failure recovery | Graceful parse failure recovery; resolution rate > 80% | Parse Engine, Command Handlers (Clarification), Storage Layer (ParseAttempt, PendingClarification) | AD-5 (one-shot clarification) | High parse failure rate under real user inputs; users ignoring clarification prompt |
| Personal utility — visual trend analysis | Chart availability; chart timeout safety | Chart Generator (preemptive cancellation), Telegram Gateway, Storage Layer | AD-2 (single-process in-process chart), AD-4 (synchronous with preemptive timeout) | Chart timeout enforcement failure via incorrect cancellation mechanism |
| Developer learning — stateful bot architecture | Observability from day one; explicit failure behavior | Structured Logger (JSON format), Storage Layer (ParseAttempt, PendingClarification, User), Startup Sweep | AD-6 (no external alerting); Structured Logger owns JSON format | Ephemeral logs on free-tier; audit trail loss on restart; export failure undetected |
| Portfolio artifact — multi-user data isolation | Correct per-user data isolation | Storage Layer (mandatory User ID scoping) | AD-3 (embedded storage with relational querying) | Data isolation defect; missing User ID filter in query |
| System reliability — zero critical failures in 30 days | Predictable failure behavior; survivable restarts; cold-start prevention | Startup Sweep, Chart Generator (preemptive timeout), Telegram Gateway + Heartbeat (cold-start), Storage Layer (failure contracts) | AD-2, AD-3, AD-4, AD-7 (Heartbeat) | Chart timeout enforcement failure; partial storage write; hosting eviction; Heartbeat failure |
| Near-zero infrastructure cost | Zero-dependency simplicity | All components (single process, embedded storage, no external services) | AD-2, AD-3 | Hosting platform eviction; filesystem non-persistence; free-tier resource limits |
| Data durability — RPO 24 hours | Recoverable from export | Data Export Agent (timer-driven, logged), Storage Layer | AD-3 (co-located storage) | Export failure undetected; export not configured before launch; export artifact not independently stored |

---

## Governance Block

### Version
v0.2

### Based On
Business v0.3 + Context v0.3

### Changes Introduced
- **[Rev 1] Per-user message serialization ownership assigned:** Dispatcher now owns a per-user in-process lock acquired at dispatch entry, released after handler and storage writes complete. Pattern described in Section 3 summary, Section 4.1 Dispatcher, Section 8 queueing, Flow A/B/C/E steps, NFR mapping, and AD-4.
- **[Rev 2] Chart Generator timeout pattern upgraded to preemptive cancellation:** "Language-level cancellation" replaced throughout with "preemptive cancellation"; cooperative cancellation (flag-checking) explicitly prohibited. Updated Section 3, Section 4.2 Chart Generator, Flow C, NFR mapping, AD-4, and risk register.
- **[Rev 3] Flow F (Data Export) added:** Trigger mechanism (internal process timer), consistency contract (read snapshot; prior artifact preserved until success), failure behavior (structured log on failure; retry on next tick), and observability signal (`export_success` / `export_failure`) defined. Section 4.2 Data Export Agent expanded.
- **[Rev 4] Dispatcher/Parse Engine keyword collision disambiguation overlap resolved:** Keyword collision disambiguation removed from Parse Engine component description. Dispatcher retains ownership (dispatch step 3). Parse Engine description clarified to operate only on already-disambiguated log-intent messages.
- **[Rev 5] Onboarding operator disclosure failure contract defined:** Flow G added with explicit write-before-send atomicity, failure contract for each partial-failure permutation, and re-delivery logic. Data Strategy updated for OnboardingSession.
- **[Rev 6] Data Export Agent failure scenario added:** Failure scenario for silent export failure and mid-export process termination added to Section 9. Export artifact preservation policy defined.
- **[Rev 7] Heartbeat added as owned architectural component (AD-7):** Heartbeat component added to Section 4.2, assigned to Telegram Gateway. Trigger pattern (in-process timer), observability signal (`{event=heartbeat}`), and failure detection (log absence) defined. AD-7 added. Removed keep-alive from AD-6 consequences; cold-start NFR tactic updated to reference Heartbeat. Section 3 and Section 8 updated.
- **[Rev 8] AD-3 transaction support status clarified:** Transaction support is now a confirmed mandatory selection criterion, not an unverified consequence. AD-3 updated; Storage Layer responsibility updated to include transaction requirement.
- **[Rev 9] Two-step deletion confirmation restart gap resolved:** DeletionConfirmation modeled as a first-class storage entity (not in-memory state). Data Strategy table updated. Failure scenario updated to reflect no UX break on restart.
- **[Rev 10] Chart Generator and Structured Logger added to traceability matrix:** Chart Generator added under personal utility / visual trend analysis row. Structured Logger added under developer learning / observability row.
- **[Additional] Storage file corruption failure scenario added:** Section 9 now covers storage file corruption as distinct from file absence or runtime write failure.
- **[Additional] Telegram account ID reuse risk added:** Section 10 and Section 9 now acknowledge this known residual risk.
- **[Additional] Per-user abuse / message flood security note added:** Section 10 documents the absence of rate limiting as a known gap with accepted risk rationale.
- **[Additional] Export artifact security note added:** Section 10 documents developer responsibility for securing the export destination.
- **[Additional] AD-2 serverless dismissal strengthened:** Serverless rejected on the stronger architectural argument (incompatibility with per-user serialization without external state), not merely hosting-tier availability.
- **[Additional] AD-4 async dismissal completed for chart flow:** AD-4 now explicitly notes that chart generation blocks all users in a strict single-threaded model and states this is an accepted trade-off at target scale.
- **[Additional] Structured log format standardized to newline-delimited JSON:** Specified in Section 4.2 Structured Logger and Section 11.1.
- **[Additional] Developer query mechanism made concrete:** Section 11.1 and 11.2 now describe that the developer uses saved ad hoc SQL queries and JSON log filtering; "developer queries storage directly" is no longer the full description.

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| AD-1 | Telegram update delivery mechanism (polling vs. webhook) | Depends on hosting platform selection; polling is safer default for free-tier | v0.1 | Open — must be resolved before deployment |
| AD-2 | Single-process architecture | Justified by target scale; eliminates inter-process complexity; serverless incompatible with per-user serialization | v0.2 | Confirmed |
| AD-3 | Embedded relational storage co-located with bot process | Eliminates network latency and second service dependency; transaction support is a mandatory selection criterion | v0.2 | Confirmed — transaction support required |
| AD-4 | Synchronous request/response per message with per-user lock | Avoids race conditions; meets latency target; Dispatcher owns per-user lock | v0.2 | Confirmed |
| AD-5 | One-shot clarification model | Inherited from Business v0.3 D-03; avoids open-ended conversational state | v0.1 | Confirmed (inherited) |
| AD-6 | No external alerting or notification mechanism | Consistent with D-05 (out of scope); near-zero cost constraint; Heartbeat is a separate reliability mechanism | v0.2 | Confirmed (inherited) |
| AD-7 | Heartbeat as an owned reliability mechanism | Cold-start is the highest-probability availability risk; in-process timer requires zero additional infrastructure | v0.2 | Confirmed |

### Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| UA-01 | Architecture | Telegram update delivery mechanism unresolved (polling vs. webhook) | Telegram Gateway design; hosting requirements | Resolve when hosting platform is selected (before deployment) |
| UA-02 | Architecture | Hosting platform filesystem persistence not yet confirmed | Data durability strategy; export-as-sole-mitigation assumption | Verify with hosting provider before deployment |
| UA-03 | Architecture | Per-user message serialization not guaranteed by hosting environment (multi-process delivery risk) | Race condition risk if hosting delivers same user's messages to parallel processes | Verify hosting update delivery behavior; document accepted risk |
| UA-04 | Implementation | History query N value not defined (A-08) | History Handler cannot be fully implemented | Developer to define before implementation of Flow 4 |
| UA-05 | Implementation | Parameter name length bound and character set not defined (Section 8.7) | Input validation cannot be implemented | Developer to define before implementation of Parse Engine |
| UA-06 | Operations | Daily export destination not defined | RPO guarantee depends on export being operational | Developer to configure before launch |
