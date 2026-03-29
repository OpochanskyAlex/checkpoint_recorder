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

The bot process continuously receives Telegram updates (either via long-polling or webhook — see AD-1), dispatches each inbound message through a layered routing pipeline, and responds synchronously within the same request cycle. Chart generation is the only computationally heavy operation and is bounded by a hard timeout.

On every process startup, a sweep executes before accepting messages: it abandons stale Open PendingClarifications and executes pending account deletions past their 3-day window. A daily data export (scheduled or triggered externally) copies a portable snapshot of the embedded storage to a developer-controlled external location — this is the sole disaster recovery mechanism.

The architecture favours correctness over throughput, simplicity over extensibility, and explicit failure messages over silent degradation. At ≤ 100 users with ~500 messages/day, no scaling mechanism is needed.

---

## 4. Component Model

### 4.1 Core Components

| Component | Responsibility | Inputs | Outputs | Key Risks |
|---|---|---|---|---|
| **Telegram Gateway** | Connects to the Telegram Bot API; receives inbound updates; sends outbound text messages and PNG images; enforces rate-limit retry before surfacing errors; filters non-text messages at the pre-dispatch gate | Telegram updates (long-poll or webhook); outbound message payloads from handlers | Inbound message events to the Dispatcher; delivery acknowledgements | Telegram API change or outage makes the system unreachable; rate-limit retry logic must not silently drop messages |
| **Dispatcher** | Routes every inbound text message through the priority chain: (1) PendingClarification check → (2) Account state check → (3) Keyword match → (4) Log intent default | Inbound text message event with Telegram ID and text payload | Routed request to appropriate Command Handler or Parse Engine; rejection response for blocked account state | Misrouting log-intent messages as commands (keyword collision); account state check must occur before any write |
| **Parse Engine** | Extracts a parameter name and numeric value (with optional unit) from a free-text message; applies the keyword collision disambiguation rule; creates a ParseAttempt record for every invocation | Free-text message payload | Parsed (name, value, unit) tuple on success; parse failure signal on failure; ParseAttempt record written to storage | False positives (wrong parameter or value extracted); false negatives (valid log input rejected); parse failure rate must be instrumented from day one |
| **Command Handlers** | One handler per dispatch target (Log, History, Chart, Compare, List, Delete Parameter, Delete Account, Restore Account, Onboarding, Help); each handler encapsulates the complete logic for its assigned flow as defined in System v0.3 Sections 6–7 | Routed request with Telegram ID and parsed parameters | Response message(s) sent via Telegram Gateway; storage reads and writes via Storage Layer; chart image sent via Telegram Gateway (Chart Handler only) | Chart Handler must enforce the 15-second timeout; Deletion handlers must enforce two-step confirmation; Onboarding Handler must deliver operator disclosure in first message |
| **Storage Layer** | Persists and retrieves all system entities (User, Parameter, LogEntry, ParseAttempt, PendingClarification, OnboardingSession); enforces mandatory User ID scoping on every query; sanitizes all inputs before storage operations | Read/write requests from Command Handlers and Startup Sweep | Query results; write acknowledgements or failure signals | Cross-user query path defect is the highest-impact security failure; raw user input must never be interpolated directly into queries |
| **Startup Sweep** | Executes once on every bot process start before the Telegram Gateway begins accepting messages; (a) marks all Open PendingClarification records as Abandoned; (b) purges all User records in Pending Deletion state where `deletion_requested_at + 3 days ≤ current_time`, cascading to all owned entities; writes an audit log entry per purge | Embedded storage state on startup | Updated storage state; structured audit log entries | If sweep crashes, bot must not start accepting messages; sweep must be idempotent in case of partial execution |

### 4.2 Supporting Components

| Component | Responsibility | Notes |
|---|---|---|
| **Chart Generator** | Generates a static PNG trend chart image from a set of LogEntry data points; executed in-process with a hard 15-second timeout enforced by the Chart Handler; the image is held in memory and delivered directly — never persisted | Timeout mechanism is critical: chart generation must be actively terminated at 15 s to prevent blocking the bot process |
| **Secrets / Config Loader** | Reads the Telegram Bot API token from the environment variable at process startup; fails fast if the token is absent | Token must not appear in any log output, error stack trace, or debug dump |
| **Data Export Agent** | Produces a portable structured dump of the embedded storage on a scheduled or externally triggered basis; writes the artifact to a developer-controlled external location (e.g., external file storage or email attachment) | Not a user-facing feature; sole mitigation for the 24-hour RPO; export schedule and destination are operational configuration defined by the developer |
| **Structured Logger** | Emits structured log records for all failure paths, startup sweep events, purge audit entries, and key flow transitions; all records include User ID, flow name, and event type | Free-tier stdout logs may be ephemeral; developer should configure log forwarding before launch |

---

## 5. Interaction Model

### 5.1 Interaction Patterns

| Pattern | Where used | Rationale |
|---|---|---|
| **Request / Response (synchronous)** | All user-initiated flows (log, query, chart, delete, onboarding, help) | Telegram is inherently request/response; users expect a reply to every message; synchronous processing within a single bot process is correct at this scale |
| **Event-driven (startup hook)** | Startup Sweep | Process lifecycle event triggers the sweep before message processing begins; no user request initiates it |
| **Scheduled / Externally triggered** | Data Export Agent | Export runs on a developer-defined schedule or manual trigger; it is decoupled from the message processing loop |

### 5.2 Key Flows

---

**Flow A: Successful Metric Logging**
- **Trigger:** User sends a free-text message with no matching command keyword
- **Steps:**
  1. Telegram Gateway receives update → Dispatcher
  2. Dispatcher: no Open PendingClarification → account Active → no keyword match → routes to Parse Engine
  3. Parse Engine extracts parameter name + value → creates ParseAttempt (outcome=success) → routes to Log Handler
  4. Log Handler: checks if parameter exists (case-insensitive exact match); creates Parameter if new; appends LogEntry; updates `Parameter.last_entry_at`, `User.last_active_at`
  5. Log Handler sends confirmation message via Telegram Gateway
- **Failure points:** Storage write failure at step 4; parse false positive at step 3
- **Recovery:** On storage write failure → explicit error message returned; no confirmation sent; user instructed to retry

---

**Flow B: Parse Failure → Clarification → Resolution**
- **Trigger:** User sends a message that fails parse; user then responds to the clarification prompt
- **Steps (Failure):**
  1. Parse Engine cannot extract pair → creates ParseAttempt (outcome=failure) → Clarification Handler
  2. Clarification Handler creates PendingClarification (state=Open); sends one-shot clarification prompt
- **Steps (Resolution):**
  3. User replies; Dispatcher detects Open PendingClarification → routes to Clarification Resolution Handler
  4. Parse Engine attempts parse on new message:
     - Success → PendingClarification → Resolved; LogEntry created; confirmation sent
     - Failure → PendingClarification → Abandoned; message re-enters dispatch from step 2 (may produce new PendingClarification)
- **Failure points:** User ignores the prompt (record abandoned on next message or startup sweep); repeated parse failure traps user in clarification loop
- **Recovery:** Clarification prompt must instruct the user to re-send with explicit `parameter name: value` format; user can always re-send original message to trigger a fresh attempt

---

**Flow C: Chart Generation**
- **Trigger:** User sends a `chart [name]` message
- **Steps:**
  1. Dispatcher keyword match → Chart Handler
  2. Chart Handler resolves parameter name (case-insensitive exact match); fetches LogEntries
  3. If fewer than 2 data points → returns informative message; no chart generated
  4. Chart Generator produces PNG in memory under 15-second timeout
  5. If timeout exceeded → process terminated; error message returned
  6. On success → PNG sent as Telegram message; image discarded from memory
- **Failure points:** Insufficient data (handled); timeout exceeded (handled); storage read failure (handled); Telegram image send failure
- **Recovery:** All failure paths return explicit user-visible error messages; no silent failure

---

**Flow D: Startup Sweep**
- **Trigger:** Bot process starts (planned restart or crash recovery)
- **Steps:**
  1. Secrets / Config Loader reads token; fails fast if absent
  2. Startup Sweep runs before Telegram Gateway opens:
     - Marks all Open PendingClarification records → Abandoned
     - For each User in Pending Deletion where window expired: purges all owned entities; sets User → Deleted; writes purge audit log entry
  3. Telegram Gateway begins accepting updates
- **Failure points:** Sweep crash before completion; partial purge
- **Recovery:** Sweep must be idempotent; if sweep fails, process should not start; restart triggers a fresh sweep

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
- **Recovery:** Confirmation message must state exact expiry timestamp; deferred purge on next startup is the accepted behavior under free-tier model

---

## 6. Data Strategy (Conceptual)

| Entity / Domain Data | Owner Component | Consistency Needs | Lifecycle | Risks |
|---|---|---|---|---|
| User | Storage Layer | Strong — User ID is the root of all data isolation; state transitions must be atomic | New → Onboarding → Active → Pending Deletion → Deleted (terminal) | Telegram ID reassignment (highly unlikely per A-01); orphaned User records if Telegram ID changes |
| Parameter | Storage Layer | Strong — creation must be idempotent (concurrent same-user messages, per Section 8.8); deletion is irreversible | Non-existent → Active → Deleted (terminal, hard-delete) | Accidental deletion is permanent; auto-creation from mistyped messages may pollute the parameter list |
| LogEntry | Storage Layer | Append-only; immutable once created | Recorded → Purged (only on parent Parameter deletion or User purge) | No edit mechanism; errors require a new LogEntry; purge is permanent |
| ParseAttempt | Storage Layer | Append-only audit record; no updates | Recorded (terminal, immutable) | Purged only on User account deletion; volume grows linearly with usage but is trivially small at target scale |
| PendingClarification | Storage Layer | Transient; state transitions (Open → Resolved / Abandoned) must be atomic with message processing | Open → Resolved or Abandoned (both terminal) | Stale Open records cleaned up by Startup Sweep; one-shot model means lost data if user ignores prompt |
| OnboardingSession | Storage Layer | Operator disclosure delivered flag must be set in the same transaction as the welcome message delivery | In Progress → Completed | Incomplete onboarding sessions are non-blocking; operator disclosure must be delivered regardless of completion |
| Chart Image | Chart Generator (in-memory only) | No persistence required; generated on demand; discarded after Telegram delivery | Ephemeral (in-memory, delivery-scoped) | Memory pressure on free-tier hosts during chart generation; enforced by timeout |
| Export Artifact | Data Export Agent | Point-in-time snapshot; consistency at export time | Created on schedule; stored externally; replaces prior snapshot | Export covers all entities; developer responsible for verifying completeness and restorability |

---

## 7. Non-Functional Requirements Coverage

### 7.1 NFR Mapping

| NFR Category | Requirement | Architectural Tactic | Trade-off |
|---|---|---|---|
| Performance — text latency | ≤ 3 s for all text responses under normal load | Single-process synchronous handling; embedded storage eliminates network I/O for reads/writes | Cold-start latency on free-tier exceeds this target; excluded from bound by design |
| Performance — chart latency | ≤ 15 s; hard timeout enforced | Chart Generator runs in-process with active timeout termination; image held in memory only | In-process timeout requires language-level cancellation support; failure returns error, not partial image |
| Performance — cold start | ≤ 60 s after idle | Keep-alive mechanism recommended (e.g., scheduled ping to prevent process suspension) | Keep-alive consumes hosting quota; without it, cold-start latency is uncontrolled |
| Availability | Best-effort > 90% daily; no formal SLA | Free-tier hosting accepted; manual monitoring by developer; startup sweep ensures clean state on restart | No automated failover; single point of failure is the hosting environment |
| Data Durability | RPO = 24 hours | Daily data export to external location; portable structured dump; developer-defined restore procedure | Restore is manual and requires developer action; data loss of up to 24 hours is accepted |
| Data Isolation | Mandatory User ID scoping on all queries | Storage Layer enforces User ID as a mandatory filter parameter; no unscoped query path exists | Requires disciplined enforcement at every query site; no framework-level enforcement |
| Input Sanitization | All user input parameterized before storage | Storage Layer accepts only structured parameters, never raw text interpolation | Developer must not bypass the Storage Layer for ad hoc queries |
| Secrets | Token never in source, logs, or version control | Secrets / Config Loader reads from environment variable; Structured Logger explicitly excludes the token value | Developer must configure hosting environment variable before deployment |
| Error Communication | Every failure path returns a user-visible message; no silent drops | Each Command Handler has an explicit failure branch; Telegram Gateway retries on rate-limit before surfacing error | Failure branches add code paths that must be tested; rate-limit retry adds latency |
| Concurrency | Per-user message serialization | Single-process architecture with sequential per-user processing; second message from same user queued until first completes | Hosting environment must not deliver concurrent messages to parallel execution contexts; race condition risk noted if it does |
| Observability | Parse failure rate, user return rate, parameter retention queryable by developer | ParseAttempt, PendingClarification, User, Parameter entities store all signal data; developer queries storage directly | No dashboarding tooling defined; developer must write queries manually |

### 7.2 NFR Unknowns

| Unknown | Decision Blocked |
|---|---|
| Exact value of N for history query (A-08) | History Handler cannot be fully implemented until N is defined; verbose responses risk Telegram message length limits |
| Telegram update delivery mechanism: polling vs. webhook (SD-10, A-11) | Telegram Gateway design; hosting platform requirements (webhook requires public HTTPS endpoint); cold-start behavior differs between the two |
| Exact parameter name length bound (Section 8.7) | Input validation cannot be implemented without a defined upper limit; recommended ≤ 100 characters but not yet confirmed |
| Permitted character set for parameter names (Section 8.7) | Rejection logic cannot be implemented; sanitization scope is undefined |
| Log forwarding / export mechanism for structured logs (Section 11.6) | Without this, pre-restart error history is ephemeral; retrospective error analysis is impossible |
| Data export destination and schedule (Section 8.3, A-10) | Export Agent cannot be configured; RPO guarantee depends on export running daily |

---

## 8. Scalability & Performance Reasoning

**Expected load:** ≤ 100 users × ~5 messages/day = ~500 messages/day ≈ 0.006 messages/second average; peak bursts estimated at 5–10 messages/minute. This is below any meaningful threshold for a single-process system.

**Bottlenecks:**
- **Chart generation** is the only CPU-intensive operation. At this load, concurrent chart requests are unlikely, but the 15-second timeout prevents any single request from blocking the process.
- **Cold-start latency** is the primary user-perceived performance risk. Free-tier process suspension after idle is the most probable cause of > 3 s response latency in practice.
- **Telegram API send latency** is outside system control. Outbound message delivery time is not included in the 3-second target (which covers system processing, not network delivery).

**Caching boundaries (conceptual):** No caching is warranted at this scale. All reads from embedded local storage are fast enough without a cache layer. Introducing a cache would add complexity with no measurable benefit.

**Queueing needs (conceptual):** Per-user message serialization (Section 8.8) requires a per-user in-process queue or lock to prevent concurrent same-user message processing. No external queue is needed. The in-process mechanism must ensure the second message from a user waits until the first is fully processed, including all storage writes.

**Growth ceiling:** This architecture is not designed to scale beyond ~1,000 users. If the user base were to grow significantly, embedded co-located storage, single-process concurrency, and free-tier hosting would all become bottlenecks. No scalability path is architected intentionally, consistent with the project's scope boundary.

---

## 9. Reliability & Failure Scenarios

| Scenario | Impact | Detection | Mitigation | Residual Risk |
|---|---|---|---|---|
| Telegram platform outage | System completely inaccessible to all users | No inbound messages received; manual developer check | Monitor Telegram status; no technical mitigation possible; document posture for users | Full service loss for outage duration; no fallback channel |
| Free-tier hosting process suspension (cold start) | First message after idle receives delayed response (up to 60 s) | User complaint; manual developer check | Scheduled keep-alive ping to prevent suspension; cold-start latency excluded from 3 s target | Unavoidable without a paid hosting tier; keep-alive reduces but does not eliminate cold starts |
| Free-tier hosting eviction or storage quota exceeded | Data loss or service termination | Storage utilization monitoring (manual at 80% threshold) | Daily data export to external location; developer-defined restore procedure | Up to 24 hours of data loss if export is not current; restore is fully manual |
| Storage write failure | Log entry or state change not persisted; user receives error message and must retry | Explicit error message returned to user; error logged with flow name and error type | Structured error response; no false confirmation sent | If the failure is persistent (storage corruption), user data may be unrecoverable until restore from export |
| Storage read failure | Query or chart returns error instead of data | Explicit error message returned to user | Structured error response; no empty result returned silently | User cannot access history or charts until storage recovers |
| Chart generation timeout | User receives error message; bot process unblocked | Timeout enforcement mechanism terminates the generation process | Hard 15-second timeout; error message returned; no blocking | Chart is unavailable for that request; user can retry |
| Partial storage write (e.g., LogEntry written but `last_entry_at` not updated) | Inconsistent entity state; observability signals may be slightly off | Manual inspection of storage state | Use transactions for multi-entity writes to ensure atomicity; fail entire operation if any part fails | If the storage mechanism does not support transactions, this risk is elevated (see AD-3) |
| Stale Open PendingClarification after crash | First message from affected user routed incorrectly to clarification handler | Startup Sweep marks all Open → Abandoned before accepting messages | Startup Sweep runs before Telegram Gateway opens | User's open clarification is silently abandoned; user must re-send original message |
| Bot offline when account deletion window expires | Purge delayed until next startup | Startup Sweep checks deletion_requested_at timestamps on every startup | Deferred purge on next startup sweep | User data persists slightly longer than the 3-day window; accepted under free-tier operational model |
| Concurrent same-user messages cause race condition | Duplicate Parameters or LogEntries; inconsistent PendingClarification state | Duplicate records visible in storage; user may see unexpected confirmations | Per-user serialization in single-process model; document risk if hosting delivers parallel execution contexts | If the hosting environment parallelizes delivery for the same user, race conditions may occur; risk accepted at target scale |
| Telegram rate limit exceeded on outbound messages | Message delivery delayed or failed | Rate limit error from Telegram API | Retry with brief delay before surfacing error to user; no silent drop | If retry limit is exhausted, user receives an error; message is not retried after the error is surfaced |
| Data isolation defect (missing User ID filter) | Cross-user data exposure | Developer code review; storage query audit | Storage Layer enforces User ID as a mandatory filter; architectural boundary prevents unscoped queries | A query logic bug that bypasses the Storage Layer interface could expose data; requires developer discipline |

---

## 10. Security & Compliance Baseline

| Area | Threat / Risk | Control | Notes |
|---|---|---|---|
| Data access — cross-user | Query logic defect exposes one user's data to another | Storage Layer enforces mandatory User ID scoping on every read/write operation; no unscoped query path exists | Highest-impact security failure mode for this system; must be reviewed in any code change touching storage queries |
| Data access — operator | Developer has unrestricted access to all raw user data | Operator disclosure delivered in onboarding welcome message (Flow 9); `operator_disclosure_delivered` flag tracked on OnboardingSession | No technical access control separates developer from user data; trust-based model for a closed personal group |
| Secrets — Telegram Bot API token | Token leaked via source code, version control, or log output | Token stored as hosting environment variable only; Structured Logger explicitly excludes token value from all output; Secrets / Config Loader fails fast if token absent | Developer must verify that the hosting platform supports environment variable injection (A-09) before deployment |
| Input injection — storage queries | User-supplied parameter names or log values injected into storage queries | All user input parameterized or sanitized before any storage operation; raw text never interpolated into queries; enforced at the Storage Layer boundary | Technology-class agnostic requirement; applies regardless of storage mechanism selected |
| PII handling | No PII collected; identity model is Telegram ID only | No real name, email, or phone number stored or processed; Telegram ID is the sole identifier | If a user's Telegram account is compromised, their bot data is accessible to the attacker via that account |
| Non-text input | Malformed or unexpected Telegram message types reach parse engine | Non-text input rejected at the pre-dispatch gate before any processing; rejection message returned; no ParseAttempt created | Voice notes, images, stickers, forwarded media, locations, and contacts are all rejected at this gate |
| Demo / synthetic data contamination | Synthetic onboarding data appears in real analytics flows | All demo entities tagged `is_synthetic = true`; all analytics flows (chart, history, compare) filter out synthetic entries | Tagging must be applied at creation time; no mechanism to retroactively tag if missed |
| Auditability | No audit trail for purge events or operator actions | Startup Sweep writes a structured audit log entry per purge event (User ID, `purge_executed_at`, `deletion_requested_at`) | Log durability risk on free-tier hosting; developer should configure log forwarding to preserve audit trail across restarts |

---

## 11. Observability Baseline

### 11.1 Signals

**Metrics (SLO candidates):**
- Parse failure resolution rate: `(ParseAttempt.outcome=success count + PendingClarification.state=resolved count) / total ParseAttempts` over rolling 30-day window; target > 80%
- User Return Rate: distinct users with interaction in week 2 / distinct users with interaction in week 1; target > 40%
- Parameter Retention Rate: parameters with a LogEntry in days 25–35 / parameters created before day 5; target > 50%
- Bot availability: binary daily check via direct interaction; target > 90% daily availability
- Storage utilization: percentage of free-tier quota consumed; action threshold at 80%

**Logs (structured):**
- Every failure path: `{user_id, flow_name, error_type, timestamp}`
- Every startup sweep action: `{event=purge|abandon, user_id, purge_executed_at, deletion_requested_at}` (purge); `{event=abandon, clarification_id, user_id, timestamp}` (clarification abandonment)
- Every chart generation timeout: `{user_id, parameter_name, timeout_at, duration_exceeded}`
- Every Telegram rate-limit retry and ultimate failure: `{user_id, flow_name, retry_count, outcome}`
- Token value must never appear in any log record

**Traces (critical paths):**
- End-to-end latency for the log flow (inbound message → storage write → confirmation sent)
- End-to-end latency for the chart flow (inbound message → chart generation → image sent or timeout)
- Startup sweep execution time (startup → sweep complete → gateway open)

### 11.2 Operational Dashboards (conceptual)

The developer queries the embedded storage and log output directly — no external dashboarding tooling is required or defined.

| What to monitor | Signal source | Action trigger |
|---|---|---|
| Parse failure resolution rate (weekly) | ParseAttempt + PendingClarification tables | < 80% → review parse logic; check user message patterns |
| User return rate (weekly cohort) | User table (`first_seen_at`, `last_active_at`) | < 40% → review onboarding and usability |
| Parameter retention rate (day 30) | Parameter + LogEntry tables | < 50% → investigate which parameters are abandoned and why |
| Bot liveness | Manual daily direct interaction | No response → investigate hosting status; trigger restart |
| Storage quota | Hosting platform console | > 80% → initiate data export and cleanup |
| Error rate by flow | System log (structured entries) | Recurring errors in a single flow → investigate and fix before next deploy |
| Pending deletion records | User table (`is_pending_deletion = true`) | Records stuck beyond 3-day window → investigate startup sweep execution |

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

- **Decision:** The bot runs as a single OS process. All components (Dispatcher, Parse Engine, Command Handlers, Storage Layer, Chart Generator, Startup Sweep) execute within this process. There is no inter-process communication, no message broker, no separate service for storage.
- **Alternatives considered:**
  - *Multi-process or microservice split:* Separate processes for message handling, storage, and chart generation; enables independent scaling and fault isolation
  - *Serverless / function-per-flow:* Each command flow is a separate function invocation; eliminates idle resource consumption
- **Rationale:** At ≤ 100 users with ~500 messages/day, multi-process complexity provides no practical benefit. Free-tier hosting typically provides a single container or instance. Single-process eliminates inter-process communication failures and reduces operational surface.
- **Trade-offs:** A crash in one component (e.g., chart generation) can affect the entire process if not properly isolated via timeout enforcement; no independent scaling; cannot deploy individual components separately
- **Consequences:** Chart Generator must be isolated via timeout to prevent process blocking. Startup Sweep must complete before the process accepts messages. All state transitions rely on in-process sequencing rather than distributed coordination.
- **Linked NFR/Business Goal:** Near-zero infrastructure cost; simplicity; personal-scale target

---

### AD-3: Embedded Relational Storage Co-located with Bot Process

- **Decision:** All persistent entities are stored in an embedded relational database co-located with the bot process on the hosting platform. No external database service is used.
- **Alternatives considered:**
  - *External managed database (e.g., free-tier cloud DB):* Separates storage from compute; survives process restarts; adds a network dependency and a second free-tier service
  - *File-based non-relational storage (e.g., JSON files):* Simpler to set up; no relational querying; no transaction support; fragile under concurrent writes
- **Rationale:** Embedded relational storage eliminates network latency for all storage operations (supporting the 3-second latency target), eliminates a second external service dependency, and provides relational querying and transaction support needed for atomic multi-entity writes. At the target data volume (~182,500 records/year), embedded storage is fully sufficient.
- **Trade-offs:** Storage is tied to the hosting environment; data is lost if the hosting platform evicts the process and discards the filesystem (mitigated by daily export); no independent scaling of storage
- **Consequences:** Daily export is mandatory as the sole disaster recovery mechanism. Developer must verify that the hosting platform provides persistent filesystem storage across restarts (not all free-tier platforms guarantee this). Transaction support must be confirmed for the selected embedded storage engine to support atomic multi-entity writes (see Section 9 partial-write risk).
- **Linked NFR/Business Goal:** Near-zero infrastructure cost; RPO 24 hours; single-process architecture (AD-2)

---

### AD-4: Synchronous Request / Response per Message

- **Decision:** Each inbound Telegram message is processed to completion (storage writes, response sent) before the next message from the same user is accepted.
- **Alternatives considered:**
  - *Async processing with a job queue:* Inbound messages enqueued; workers process asynchronously; decouples receipt from processing; enables parallelism across users
  - *Async within a message (non-blocking I/O):* Single-threaded event loop with async/await; allows I/O overlap within a single message but does not add per-user parallelism
- **Rationale:** At the target scale and message volume, synchronous per-user serialization is simpler, avoids race conditions on PendingClarification state and Parameter creation, and meets the 3-second latency target without optimization. Async complexity is not justified.
- **Trade-offs:** A slow operation (e.g., storage write) blocks subsequent messages from the same user; chart generation timeout is critical to prevent process-wide blocking; no parallelism benefit across users in strict synchronous model
- **Consequences:** Chart Generator timeout enforcement is non-optional. Per-user serialization must be guaranteed by the hosting environment's message delivery behavior or enforced in-process. Race condition risk accepted for edge cases (Section 8.8, Section 9.6).
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
- **Rationale:** Threshold alerts and push notifications are confirmed out of scope (D-05). At this scale, manual daily developer interaction is the availability monitoring mechanism (Section 11.4). Adding alerting infrastructure would violate the near-zero infrastructure cost constraint.
- **Trade-offs:** Extended outages may go undetected until the developer's daily check; no automated recovery
- **Consequences:** Developer must interact with the bot at least once daily. Log forwarding mechanism (if configured) is the closest approximation to proactive error visibility.
- **Linked NFR/Business Goal:** D-05; near-zero cost; availability target > 90% daily

---

## 13. Risks & Open Questions

### 13.1 Architecture Risks

| Risk | Impact | Probability | Mitigation |
|---|---|---|---|
| Hosting platform does not provide persistent filesystem across restarts | All persisted data lost on restart; RPO violated | Medium — varies by free-tier platform | Verify filesystem persistence guarantees before deployment; configure daily export before launch |
| Chart generation in-process blocks bot on timeout enforcement failure | All subsequent messages delayed or lost | Low — timeout mechanism is required; failure is in implementation | Timeout enforcement must be validated in testing; use language-level cancellation, not just a sleep |
| Per-user serialization not guaranteed by hosting environment (concurrent delivery) | Race conditions on PendingClarification and Parameter creation | Low-Medium — depends on hosting platform's update delivery behavior | Verify hosting environment delivers messages sequentially for the same user; document accepted risk if not |
| Startup Sweep partial execution on crash | Some stale Open PendingClarifications or expired deletion records not cleaned up | Low — sweep must be idempotent | Make sweep operations idempotent; re-running sweep on the same records must produce the same result |
| Structured log loss on process restart (free-tier ephemeral stdout) | Retrospective error analysis impossible; audit trail for purge events lost | High — free-tier stdout is frequently discarded on restart | Configure log forwarding before launch; document that pre-restart error history is ephemeral (Section 11.6) |
| Token leaked via error stack trace or debug log | Bot suspended by Telegram; security incident | Low — requires implementation error | Structured Logger explicitly excludes token; code review for any log statement that could include environment variables |
| MVP scope not formally defined before architecture is built upon | Rework if full-scope design components are built but later excluded | Medium | Business Open Question 1 (minimum viable scope) must be resolved before implementation begins |

### 13.2 Open Questions

1. **What is the Telegram update delivery mechanism: polling or webhook?** (SD-10, A-11) — blocks Telegram Gateway component design; affects hosting requirements; must be resolved before deployment.

2. **What hosting platform will be used?** — determines filesystem persistence guarantees (impacts data durability strategy), environment variable support (impacts secrets handling), and public HTTPS endpoint availability (impacts AD-1).

3. **What is the fixed N for history queries (last N entries)?** (A-08) — blocks History Handler implementation; affects Telegram message length risk.

4. **What is the exact parameter name length bound and permitted character set?** (Section 8.7) — blocks input validation implementation in the Parse Engine and Storage Layer.

5. **What is the minimum viable scope?** (Business Open Question 1) — if MVP scope is subsequently constrained, components designed for full scope (e.g., period comparison, account deletion) may be deferred; architecture should not be treated as final until this is resolved.

6. **Where does the daily export artifact go, and what is the export schedule?** (Section 8.3, Data Export Agent) — blocks Data Export Agent configuration; RPO guarantee depends on this being operational before launch.

7. **Will the developer configure log forwarding before launch?** — if not, all error history and purge audit records are ephemeral across restarts; developer accepts reduced retrospective observability.

---

## 14. Traceability Matrix

| Business Goal | Architectural Goal | Component | Key Decision | Risk |
|---|---|---|---|---|
| Personal utility — reduce logging friction | Low-friction message handling; ≤ 3 s text response | Telegram Gateway, Dispatcher, Parse Engine, Storage Layer | AD-2 (single-process), AD-3 (embedded storage), AD-4 (synchronous per-message) | Cold-start latency on free-tier; parse false negatives increase friction |
| Personal utility — parse failure recovery | Graceful parse failure recovery; resolution rate > 80% | Parse Engine, Command Handlers (Clarification), Storage Layer (ParseAttempt, PendingClarification) | AD-5 (one-shot clarification) | High parse failure rate under real user inputs; users ignoring clarification prompt |
| Developer learning — stateful bot architecture | Observability from day one; explicit failure behavior | Structured Logger, Storage Layer (ParseAttempt, PendingClarification, User), Startup Sweep | AD-6 (no external alerting) | Ephemeral logs on free-tier; audit trail loss on restart |
| Portfolio artifact — multi-user data isolation | Correct per-user data isolation | Storage Layer (mandatory User ID scoping) | AD-3 (embedded storage with relational querying) | Data isolation defect; missing User ID filter in query |
| System reliability — zero critical failures in 30 days | Predictable failure behavior; survivable restarts | Startup Sweep, Chart Generator (timeout), Telegram Gateway (rate-limit retry), Storage Layer (failure contracts) | AD-2, AD-3, AD-4 | Chart timeout enforcement failure; partial storage write without transactions; hosting eviction |
| Near-zero infrastructure cost | Zero-dependency simplicity | All components (single process, embedded storage, no external services) | AD-2, AD-3 | Hosting platform eviction; filesystem non-persistence; free-tier resource limits |
| Data durability — RPO 24 hours | Recoverable from export | Data Export Agent, Storage Layer | AD-3 (co-located storage) | Export not configured before launch; export artifact not independently stored; restore procedure not validated |

---

## Governance Block

### Version
v0.1

### Based On
Business v0.3 + Context v0.3

### Changes Introduced
- Initial architecture document produced from Business v0.3 and System Context v0.3
- Seven architectural goals defined with linked business goals and metrics
- Five core components and four supporting components defined with responsibilities, inputs, outputs, and key risks
- Three interaction patterns identified; five key flows documented with step-by-step component traces and failure recovery behavior
- Conceptual data strategy defined for all eight entity / data domains
- NFR mapping covering all ten NFR categories from System v0.3; six NFR unknowns identified that block implementation decisions
- Scalability and performance reasoning confirmed single-process architecture is appropriate at target load
- Fifteen failure scenarios defined with detection, mitigation, and residual risk
- Security baseline covering cross-user data access, operator access, secrets, input injection, PII, non-text input, synthetic data contamination, and auditability
- Observability baseline with metrics, structured log schema, critical path traces, and conceptual operational dashboard
- Six architectural decisions in ADR format (AD-1 through AD-6); AD-1 remains unresolved pending hosting platform selection
- Seven architecture risks and seven open questions identified
- Full traceability matrix linking all business goals to architectural goals, components, decisions, and risks

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| AD-1 | Telegram update delivery mechanism (polling vs. webhook) | Depends on hosting platform selection; polling is safer default for free-tier | v0.1 | Open — must be resolved before deployment |
| AD-2 | Single-process architecture | Justified by target scale; eliminates inter-process complexity; consistent with free-tier constraint | v0.1 | Confirmed |
| AD-3 | Embedded relational storage co-located with bot process | Eliminates network latency and second service dependency; sufficient at target data volume | v0.1 | Confirmed |
| AD-4 | Synchronous request/response per message | Avoids race conditions; meets latency target; complexity not justified at scale | v0.1 | Confirmed |
| AD-5 | One-shot clarification model | Inherited from Business v0.3 D-03; avoids open-ended conversational state | v0.1 | Confirmed (inherited) |
| AD-6 | No external alerting or notification mechanism | Consistent with D-05 (out of scope); near-zero cost constraint | v0.1 | Confirmed (inherited) |

### Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| UA-01 | Architecture | Telegram update delivery mechanism unresolved (polling vs. webhook) | Telegram Gateway design; hosting requirements | Resolve when hosting platform is selected (before deployment) |
| UA-02 | Architecture | Hosting platform filesystem persistence not yet confirmed | Data durability strategy; export-as-sole-mitigation assumption | Verify with hosting provider before deployment |
| UA-03 | Architecture | Per-user message serialization not guaranteed by hosting environment | Concurrency / race condition risk | Verify hosting update delivery behavior; document accepted risk |
| UA-04 | Implementation | History query N value not defined (A-08) | History Handler cannot be fully implemented | Developer to define before implementation of Flow 4 |
| UA-05 | Implementation | Parameter name length bound and character set not defined (Section 8.7) | Input validation cannot be implemented | Developer to define before implementation of Parse Engine |
| UA-06 | Operations | Daily export destination and schedule not defined | RPO guarantee depends on export being operational | Developer to configure before launch |
| UA-07 | Operations | Log forwarding mechanism not defined | Audit trail and error history may be lost on restart | Developer to decide before launch; document posture if not configured |
