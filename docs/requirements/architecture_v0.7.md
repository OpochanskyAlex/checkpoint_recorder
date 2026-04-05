# Architecture Overview

> **Version:** v0.1
> **Status:** Initial draft — ready for review
> **Date:** 2026-04-01

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
| AG-4: Measurable success metrics | All five business success metrics must be computable from system-generated events | Portfolio demonstration | All five metrics observable via Logging / Observability Component |
| AG-5: Operational simplicity | Single operator, AI-agent assisted (R-008). System must be operable without a dedicated team | Service continuity | ≥95% monthly uptime; operator can diagnose incidents from logs alone |
| AG-6: Graceful NLP degradation | When automatic parsing fails, the system must never silently discard user intent (D-012, R-002) | Reduce tracking abandonment | ParseAttempt creation rate; disambiguation completion rate |
| AG-7: Correct lifecycle enforcement | Account deletion (3-day grace, SD-004), alert one-shot (SD-003), and cascade deletion atomicity must be enforced without manual intervention | User data privacy and trust; service continuity | Zero partial-purge incidents; PendingDeletion → Deleted transition on schedule |

---

## 3. Architecture Summary

The system is a **single-process, component-structured monolith** deployed as a Telegram bot backend serving approximately 10 users. Given the confirmed scale ceiling of 20 concurrent users (§8.2, System v0.7) and a single operational owner, the complexity of a distributed architecture is unjustified and actively harmful to operability.

The design organises the system into **logically separated, named components** — each with a clear responsibility and well-defined inputs/outputs — without physically distributing them into separate services. Components communicate in-process. This provides a clear upgrade path if scale requires distribution in the future, without incurring the operational overhead at current scale.

The primary interaction pattern is **synchronous request/response** driven by incoming Telegram messages. A single asynchronous concern — alert evaluation after entry storage — is modelled as a **post-commit event** within the same process. A **scheduled process** handles all time-triggered responsibilities: retention enforcement, PendingDeletion purge, and stale ParseAttempt cleanup.

The Telegram Bot API is the sole external communication channel (both inbound and outbound), and there is no alternative fallback channel.

---

## 4. Component Model

### 4.1 Core Components

| Component | Responsibility | Inputs | Outputs | Key Risks |
|-----------|---------------|--------|---------|-----------|
| **Telegram Gateway** | Receives all inbound messages from Telegram Bot API; dispatches all outbound messages (text and images) to users | Telegram Bot API (polling or webhook); outbound message payloads from other components | Normalized inbound message events (user ID, message text, timestamp) to the Message Dispatcher; delivered responses to users | Telegram API unavailability halts all I/O; rate limits under unexpected load (R-004, R-019) |
| **Message Dispatcher** | Classifies inbound messages by intent (data entry, command, disambiguation response, periodicity selection, alert re-arm, account deletion, etc.) and routes to the responsible handler component | Normalized inbound message events | Routed calls to Entry Processor, ParseAttempt Manager, Metric Manager, Account Manager, Alert Engine, or Chart Generator | Mis-classification silently routes a data entry to a command handler or vice versa; edge cases in classification create dead-end user states |
| **User Session Guard** | Checks the InternalUser account status before any handler is invoked (Active / PendingDeletion / Deleted); enforces the one-active-ParseAttempt-per-user constraint; provides a uniform access point for per-user conversation state | Inbound message event + internal_user_id | Account status decision (allow / block with message / redirect to restoration flow); current ParseAttempt state for the user | Incorrect state read under concurrent messages from the same user (race to create duplicate InternalUser records — §8.3, System v0.7) |
| **Entry Processor** | Orchestrates the data entry flow: invokes NLP Engine, determines auto-create vs. existing metric, manages periodicity prompt, writes the Entry record, triggers alert evaluation, dispatches confirmation | Parsed message intent from Dispatcher; NLP result from NLP Engine; Data Repository; Alert Engine | Stored Entry record; confirmation message to user; alert evaluation trigger; parse outcome event to Observability Collector | Entry immutability means a silently incorrect auto-parse permanently pollutes the time series (R-002); periodicity prompt non-completion leaves entry unstored without error (SD-002) |
| **NLP Parsing Engine** | Accepts raw free-text; returns (metric_name, values, dimension_assignments, confidence_score); does not make storage decisions | Raw free-text string; user's existing metric name vocabulary (from Data Repository) | Structured parse result: metric_name (string), value(s) (numeric), dimension_assignments (map), confidence (float), outcome (auto-parse / ambiguous / unrecognized) | Confidence threshold is undefined (SU-002); too low → incorrect auto-parses; too high → excessive ParseAttempts; NLP library / service choice is deferred |
| **ParseAttempt Manager** | Creates, updates, and resolves ParseAttempt records; manages Pending → Resolved / Deferred / Expired transitions; enforces one-active-ParseAttempt-per-user constraint; delivers disambiguation prompts; supports late categorisation | NLP Engine outcome (ambiguous); user disambiguation selection; expiry events from Scheduler | ParseAttempt records in Data Repository; disambiguation prompt to Telegram Gateway; late categorisation trigger to Entry Processor; deferral / expiry events to Observability Collector | Dangling Pending ParseAttempt with no dispatched prompt is a consistency failure (§8.3, System v0.7); Deferred entries accumulate without a cleanup policy (SU-006) |
| **Alert Engine** | Post-entry: evaluates all Active alerts for the metric against the new entry value; transitions Triggered alerts to Triggered state; dispatches notification with single retry; logs evaluation result | New Entry record (post-storage); Alert records from Data Repository; Telegram Gateway | Alert status update in Data Repository; alert notification to Telegram Gateway; alert evaluation event to Observability Collector | Alert evaluation failure must not roll back the entry (§8.3, System v0.7); notification dispatch failure leaves the alert Triggered but the user uninformed (R-011); conversation state collision with active ParseAttempt session (§11.5, System v0.7) |
| **Chart Generator** | Retrieves entry history for a metric; generates a time-series chart image; delivers to user via Telegram Gateway | Chart request (metric_id, optional time range); Data Repository | Chart image → Telegram Gateway; chart invocation event to Observability Collector; error message if insufficient data or rendering failure | No text-summary fallback if rendering fails (R-016); large time ranges may produce oversized images failing Telegram delivery |
| **Metric Manager** | Handles explicit metric creation (Flow 7), metric listing (Flow 8), metric archival, and individual metric deletion (Flow 11) with cascade atomicity; manages MetricActivityStatus computation | User commands; Data Repository | Metric records; MetricActivityStatus (lazy computed on read — see AD-4); cascade deletion confirmation events; Observability events | Cascade atomicity failure leaves orphaned Entries or Alerts (R-005 data isolation impact); near-duplicate metric names not detectable under exact-match deduplication (R-003, SU-003) |
| **Account Manager** | Handles user onboarding (Flow 1) including idempotent registration; account deletion request (Flow 10); account restoration (Flow 10a); onboarding message composition (retention policy, no-export notice, raw_input storage notice, one-shot alert notice) | First-contact trigger; deletion / restoration commands; Data Repository | InternalUser records; onboarding message; PendingDeletion state transition; registration events to Observability Collector | Concurrent first messages racing to create duplicate InternalUser records (§8.3 idempotency requirement); compound first-contact flow partial failure must not silently lose entry intent (R-015) |
| **Scheduled Process** | Time-triggered: purges accounts where PendingDeletion grace period has elapsed (3-day, SD-004); cleans up stale Deferred ParseAttempts beyond the cleanup window (SU-006); enforces 1-year retention guarantee (D-013) | Scheduled time triggers; Data Repository | Permanent purge of eligible user data (atomic per user); cleanup of stale ParseAttempts; scheduled process execution events to Observability Collector | Process failure leaves PendingDeletion accounts in limbo (D-013 obligation unmet); partial purge is a data integrity failure — process must be idempotent and resumable (§8.3, System v0.7) |

### 4.2 Supporting Components

| Component | Responsibility | Notes |
|-----------|---------------|-------|
| **Data Repository** | Durable storage of all system entities (InternalUser, Metric, Entry, Alert, ParseAttempt, MetricActivityStatus); enforces per-user data isolation at the storage layer; provides transactional semantics for atomic cascade deletions and idempotent writes | Per-user isolation enforced at the repository layer — not at the application filtering layer. This is a security boundary, not a convenience abstraction. No schema specified; technology choice deferred. |
| **Observability Collector** | Captures structured event records for all five business success metrics and operational health signals; the sole means by which success metrics are computable (§7, System v0.7) | Structured log events (not free-text). All components emit to this collector. Technology choice deferred. |
| **Configuration & Secrets** | Manages the Telegram Bot API token, scheduled process intervals, ParseAttempt expiry timeout (SU-001), NLP confidence threshold (SU-002), ParseAttempt stale cleanup window (SU-006) | Telegram Bot API token must never appear in source code or logs. Its storage and rotation are the Bot Operator's responsibility. System reads it from environment at startup. |

---

## 5. Interaction Model

### 5.1 Interaction Patterns

| Pattern | Where Applied | Rationale |
|---------|--------------|-----------|
| **Synchronous Request/Response** | All user-triggered flows (entry, disambiguation, chart request, metric management, account management) | Telegram is a message-driven interface; users expect a response to each message; portfolio scale makes async complexity unjustified |
| **Post-Commit Event (in-process)** | Alert evaluation after Entry storage (Flow 2, step 5; Flow 3a, step 5) | Alert evaluation must not block or roll back entry storage; it is a downstream consequence, not a transactional requirement |
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
  7. Alert Engine → Data Repository (evaluate Active alerts for metric) → optionally → Telegram Gateway (notification dispatch)
  8. Entry Processor → Observability Collector (parse success event, entry_id)
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
  4. ParseAttempt Manager → Data Repository (create ParseAttempt record, status = Pending)
  5. ParseAttempt Manager → Telegram Gateway (disambiguation prompt with candidate metrics)
  6. ParseAttempt Manager → Observability Collector (ambiguous parse event)
  7. [Later] User responds → Dispatcher → ParseAttempt Manager → resolves to Entry Processor (as Flow A from step 5)
  8. OR: [Expiry] Scheduled Process / internal timer → ParseAttempt Manager → Data Repository (status = Deferred); Observability event
- **Failure Points:**
  - Step 4 succeeds but step 5 fails: dangling Pending ParseAttempt. Must be cleaned up or prompt must be retried. (§8.3)
  - Expiry timeout value (SU-001) not yet defined — 24 h is the recommended starting point
- **Recovery:** Deferred ParseAttempts are not failures; they are resting states. Late categorisation is supported (Flow 3b, System v0.7). Cleanup window governs eventual discard (SU-006).

---

#### Flow C: Account Deletion with Grace Period

- **Trigger:** User sends account deletion request
- **Steps:**
  1. Telegram Gateway → Dispatcher → Account Manager
  2. Account Manager → Data Repository (set InternalUser.status = PendingDeletion, record deletion_scheduled_timestamp = now + 3 days)
  3. Account Manager → Telegram Gateway (3-day notice message — SD-004)
  4. Account Manager → Observability Collector (deletion scheduled event)
  5. [3 days later] Scheduled Process → Data Repository (identify accounts past deletion_scheduled_timestamp with status = PendingDeletion → atomic purge of all user data)
  6. Scheduled Process → Observability Collector (purge completion event)
- **Failure Points:**
  - Step 5: Scheduled Process failure → PendingDeletion accounts linger; deletion commitment unmet (D-013); operator must investigate via Observability Collector
  - Step 5: Partial purge → data integrity failure; process must be idempotent and resumable (§8.3)
- **Recovery:** Scheduled Process must be designed to resume partial purges safely. Operator alert if the process has not run within its expected window.

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

- **Trigger:** Scheduled time trigger (cadence to be defined at implementation)
- **Steps:**
  1. Scheduled Process → Data Repository: identify InternalUsers with last_interaction_timestamp > 1 year ago (D-013 retention enforcement)
  2. Scheduled Process → Data Repository: identify PendingDeletion accounts past deletion_scheduled_timestamp → atomic purge
  3. Scheduled Process → Data Repository: identify Deferred ParseAttempts past stale cleanup window (SU-006) → transition to Expired
  4. Scheduled Process → Observability Collector (execution result: accounts purged, ParseAttempts cleaned up, any failures)
- **Failure Points:**
  - Process not running: all three retention obligations are unmet; operator must monitor scheduled process heartbeat
  - Partial execution: idempotency required at each step

---

## 6. Data Strategy (Conceptual)

| Entity / Domain Data | Owner Component | Consistency Needs | Lifecycle | Risks |
|---------------------|----------------|------------------|-----------|-------|
| InternalUser | Account Manager (write) / User Session Guard (read) / Data Repository (store) | Strong consistency on creation (idempotent, no duplicates — §8.3) | Active → PendingDeletion → Deleted (terminal); purged by Scheduled Process | Concurrent first-message race creating duplicate records (§8.3); Deleted users who re-register must start fresh |
| Metric | Metric Manager / Entry Processor (auto-create) | Consistent name-uniqueness per user; dimension_names immutable after first entry | Active → Archived ↔ Active → Deleted (cascade from metric deletion or account deletion) | Near-duplicate names fragment history (R-003); dimension naming locked after first compound entry |
| Entry | Entry Processor / Data Repository | Immutable after storage; entry_timestamp must preserve original message time even for late-categorised entries | Stored → Deleted (cascade from metric or account deletion only) | Incorrect auto-parse permanently pollutes time series (R-002); raw_input is residual personal data (R-017) |
| Alert | Alert Engine / Metric Manager | Status transitions must be atomic; re-arm resets status to Active | Active → Triggered → Active (re-arm) | Archived ↔ Active | Deleted (cascade) | One-shot behavior: Triggered alert never fires again without explicit user re-arm (SD-003); alert on undefined dimension rejected (Flow 6, step 3) |
| ParseAttempt | ParseAttempt Manager | Consistent with one-active-per-user constraint | Pending → Resolved (terminal) | Pending → Deferred → Expired (terminal) | Dangling Pending without dispatched prompt is a consistency failure (§8.3) |
| MetricActivityStatus | Metric Manager (lazy compute on read — AD-4) | Eventually consistent; computed from Entry history on demand | Derived — recomputed; no separate lifecycle | Stale if computation is triggered at wrong time relative to timezone boundaries (SU-007) |
| raw_input (on Entry and ParseAttempt) | Data Repository | Retained as part of parent record | Purged atomically on account deletion (Flow 10) and metric deletion (Flow 11) | Residual personal data risk (R-017); no scrubbing at portfolio scope (SD-005); user informed at onboarding |

---

## 7. Non-Functional Requirements Coverage

### 7.1 NFR Mapping

| NFR Category | Requirement | Architectural Tactic | Trade-off |
|-------------|-------------|---------------------|-----------|
| Performance — Entry ack | ≤ 5 s end-to-end (§8.1, System v0.7) | NLP Engine is in-process (no network round-trip to external NLP service preferred); Data Repository on same host or low-latency connection | In-process NLP limits language model complexity; larger models may require an external service adding latency |
| Performance — Chart ack | ≤ 5 s acknowledgment; ≤ 30 s full delivery | Two-phase response: immediate acknowledgment via Telegram Gateway; chart generation in background coroutine / thread; deliver when ready | Adds implementation complexity for the two-phase pattern; simplest single-threaded alternative risks Telegram "bot not responding" perception |
| Performance — Alert dispatch | ≤ 60 s from entry storage to notification | Post-commit in-process evaluation; no queue needed at 10-user scale | If evaluation blocks for any reason, the 60 s budget is consumed; at scale this would require a queue |
| Availability | ≥ 95% monthly uptime (§8.2, System v0.7) | Single-instance deployment with process supervisor / container restart-on-failure; health check endpoint for operator monitoring | Single point of failure for the process; no hot standby at portfolio scale; operator accepts downtime risk (R-008) |
| Scale ceiling | ≤ 20 concurrent users without architecture review | Monolithic design with internal concurrency handling; explicit ceiling documented | Exceeding ceiling requires architecture review — no graceful degradation designed beyond this point |
| Atomicity — Registration | Idempotent; no duplicate InternalUser records | Upsert or unique-constraint-on-Telegram-ID at Data Repository layer | Requires database-level uniqueness enforcement, not application-level deduplication |
| Atomicity — Cascade deletion | Atomic per user (account) and per metric (metric deletion) | Database transaction spanning all related entities in a single commit | Transaction scope increases with data volume; at ~100 time series, this is not a concern |
| Atomicity — ParseAttempt + Prompt | ParseAttempt creation and prompt dispatch treated as a unit | If prompt dispatch fails: clean up the ParseAttempt or retry dispatch before returning an error to the user | Retry logic adds complexity; dangling Pending ParseAttempt is worse than a failed flow |
| Security — Token | Bot API token must never appear in logs or source | Environment variable injection at startup; secrets management responsibility of operator | Operator-side risk accepted (§8.4, System v0.7) |
| Security — User isolation | Per-user data isolation 100% non-negotiable | Isolation enforced at the Data Repository layer (all queries parameterized by internal_user_id) — not at the application filtering layer | Application-layer filtering creates a miss-one-call vulnerability; repository-layer enforcement is the safer default |
| Observability | All five success metrics must be computable | Structured event emission from every component to Observability Collector; no free-text log-parsing required | Adds an event-emission call to every significant code path; must not fail silently (if event emission fails, the metric becomes unmeasurable) |

### 7.2 NFR Unknowns

| Missing NFR | Decision Blocked |
|-------------|-----------------|
| **Recovery Time Objective (RTO) / Recovery Point Objective (RPO)** | Blocks: backup strategy for Data Repository; determines whether a backup replica is required at all, or whether data loss up to the last scheduled backup is acceptable |
| **Backup frequency for Data Repository** | Blocks: storage strategy; at ~100 time series the data volume is tiny, but the backup schedule must be defined before deployment to honour D-013 (1-year retention guarantee) |
| **Deployment platform constraints** | Blocks: choice of Telegram polling vs. webhook (webhook requires a public HTTPS endpoint); process supervisor technology; scheduled process implementation (cron vs. in-process scheduler) |
| **NLP parsing library or service** | Blocks: performance estimate for entry ack latency; whether in-process NLP is viable or an external service call is required; affects AD-1 (monolith) trade-off |
| **Chart rendering library** | Blocks: chart delivery latency estimate; image size constraints (Telegram file size limits) |
| **ParseAttempt expiry timeout value (SU-001)** | Blocks: Scheduled Process configuration; user-facing disambiguation session UX |
| **NLP confidence threshold (SU-002)** | Blocks: ParseAttempt creation rate; directly impacts the 85% parse success target |
| **Stale Deferred ParseAttempt cleanup window (SU-006)** | Blocks: Scheduled Process configuration; storage growth estimate |
| **Scheduled Process execution cadence** | Blocks: worst-case delay between PendingDeletion grace period expiry and actual purge; impacts D-013 commitment honesty |

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
| Chart generation latency | Chart Generator | Two-phase response (immediate ack + async generation) prevents timeout perception; rendering budget is 25 s of the 30 s total |
| Telegram Bot API rate limits | Telegram Gateway | At 10-user scale, rate limits are not a practical concern; would become relevant if bot is made public (R-019) |
| Cascade deletion transaction size | Data Repository | At ~100 time series per user, transaction scope is small; not a performance concern at current scale |
| Scheduled Process overlap | Scheduled Process | Ensure the process is not re-invoked while still running (idempotency guard) |

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
| Telegram API unavailable | All I/O halted; no messages received or sent; bot appears offline to users | Telegram Gateway fails to connect; health signal absent from Observability Collector | Process supervisor keeps bot process alive; bot resumes polling / reconnects when API recovers; operator alert via Observability | No fallback channel; users cannot log entries during outage |
| Data Repository unavailable | Entry storage fails; all flows fail at the persistence step; user receives error and is asked to re-submit | Entry Processor / Repository calls throw errors; Observability Collector logs storage failure events | Operator alert via Observability; user is explicitly notified to re-submit | Data entered during outage is lost unless user re-submits; no in-memory buffer defined at portfolio scale |
| Data Repository partial outage (read available, write unavailable) | Reads (chart, metric listing) succeed; writes (entry storage, alert state update) fail | Write failures logged via Observability | Same as above for writes; read-only operations continue unaffected | Same as above |
| NLP Parsing Engine failure | All free-text entries route to ParseAttempt; parse success rate drops to 0%; 85% target unachievable | Parse failure rate spike visible in Observability Collector | ParseAttempt flow provides manual fallback; operator alert if parse success rate falls below target | User experience degrades significantly; all entries require manual disambiguation |
| Alert Engine failure (post-commit) | Alert notifications not dispatched; alert accuracy target (>95%) threatened | Alert evaluation failure events in Observability Collector | Single retry on notification dispatch (§5 Flow 5, System v0.7); entry is preserved regardless | Silent alert failures; user misses threshold notification; operator visibility only |
| Chart Generator failure | Chart feature unavailable; chart adoption metric impacted | Error response to user; chart failure events in Observability Collector | User receives explicit error message; no text-summary fallback (accepted gap, R-016) | Users cannot access visual history during failure; no fallback defined |
| Scheduled Process failure | PendingDeletion accounts not purged; D-013 retention obligation unmet; stale Deferred ParseAttempts accumulate | Absence of scheduled process heartbeat event in Observability Collector | Operator investigation triggered by missing heartbeat; manual re-run required | Deletion commitment unmet during failure window; operator-dependent recovery |
| Concurrent first-message race | Duplicate InternalUser records created for the same Telegram user ID | Duplicate key violation at Data Repository if uniqueness constraint enforced | Repository-level unique constraint on Telegram user ID → idempotent upsert | If uniqueness not enforced at DB layer, cross-user data association risk |
| Cascade deletion partial failure | Some Entries or Alerts survive after metric or account deletion; orphaned data | Purge completion event missing from Observability Collector; mismatch between expected and actual cascade counts | Atomic transaction required; process must be idempotent and resumable if interrupted | Data integrity failure if not atomic; residual data may constitute privacy breach (R-005) |
| Alert notification during ParseAttempt session | User confuses alert notification for a disambiguation selection | User provides unexpected input to ParseAttempt Manager | Formatting distinction between alert blocks and selection prompts (§11.5, System v0.7) | Residual UX confusion; accepted at portfolio scope |
| ParseAttempt + Prompt atomicity failure | Pending ParseAttempt created but no prompt delivered; user cannot respond; stuck state | Pending ParseAttempt with no user-visible prompt; User Session Guard would block subsequent messages | Cleanup: if prompt dispatch fails, delete the ParseAttempt; retry prompt; return error to user | If cleanup also fails, operator must manually clear the dangling record |

---

## 10. Security & Compliance Baseline

| Area | Threat / Risk | Control | Notes |
|------|--------------|---------|-------|
| **Telegram Bot API token** | Token exposure → full bot impersonation; all user interactions compromised | Token injected via environment variable at startup; never logged, never in source code; rotation is operator responsibility | No in-scope token management infrastructure; operator risk accepted (§8.4, System v0.7) |
| **Per-user data isolation** | Implementation error leaks one user's data to another user | All Data Repository queries parameterized by internal_user_id at the repository layer; never filtered at the application layer | 100% non-negotiable target (R-005); must be covered by integration tests verifying isolation |
| **User identity** | Identity linkage between Telegram user and stored data | Only an opaque internal_user_id is stored; Telegram identity fields (name, username, phone) are never persisted (D-007) | Telegram holds identity fields outside this system's control; residual risk accepted (R-007) |
| **raw_input personal data** | Free-text messages may contain personal or special-category data (health metrics, financial data) | User informed at onboarding that message text is stored verbatim; raw_input purged on account and metric deletion; no scrubbing at portfolio scope (SD-005) | Residual personal data risk elevated to Medium (R-017); accepted for portfolio scope |
| **Open bot registration** | Any Telegram user can register; user count may exceed the designed cohort | No access control at this stage; acknowledged gap (R-018); if bot becomes public or cohort exceeds ~10 users, an allowlist or invite-code mechanism must be introduced before further scaling | Risk accepted at current scale; architecture must support adding access control without structural changes |
| **Rate limiting** | Message flooding from a single user or public exposure | No rate limiting defined at portfolio scale; risk accepted (R-019) | Must be added before any public release or scaling beyond the designed ceiling |
| **Auditability** | Inability to trace a stored entry back to its source input or detect data integrity failures | raw_input retained on Entry records for audit tracing; Observability Collector captures all significant events; cascade deletion counts logged | Observability Collector is the primary audit tool; its availability is critical |
| **PII in logs** | Observability events accidentally capture personal data (e.g., raw_input content) | Structured events must reference entity IDs (user_id, metric_id, entry_id), not free-text content; raw_input must not appear in Observability events | Explicitly enforced at design time; log schema must be reviewed before deployment |

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
- `active_users_count` — count of users with at least one active metric (business success metric)
- `chart_invocation_rate` — chart requests / active users (target > 25%)
- `alert_delivery_accuracy_rate` — alerts correctly fired and dispatched / alerts expected to fire (target > 95%)
- `cross_user_isolation_incidents` — count of cross-user data visibility events (target = 0, non-negotiable)

**Logs (structured):**
- `registration_event` — {event: "user_registered", internal_user_id, timestamp}
- `parse_outcome_event` — {event: "parse_success" | "parse_ambiguous" | "parse_failed", internal_user_id, metric_id (if resolved), confidence_score, entry_id (if stored), timestamp}
- `parse_attempt_event` — {event: "parse_attempt_created" | "parse_attempt_resolved" | "parse_attempt_deferred" | "parse_attempt_expired", parse_attempt_id, internal_user_id, timestamp}
- `alert_evaluation_event` — {event: "alert_evaluated", alert_id, metric_id, internal_user_id, condition_met: bool, dispatch_outcome: "delivered" | "failed" | "retried", timestamp}
- `chart_invocation_event` — {event: "chart_requested", internal_user_id, metric_id, timestamp}
- `account_lifecycle_event` — {event: "pending_deletion_scheduled" | "account_restored" | "account_purged", internal_user_id, timestamp}
- `cascade_deletion_event` — {event: "metric_deleted", metric_id, internal_user_id, entry_count_deleted, alert_count_deleted, parse_attempt_count_expired, timestamp}
- `scheduled_process_event` — {event: "scheduler_run_completed" | "scheduler_run_failed", accounts_purged, parse_attempts_cleaned, errors, timestamp}
- `error_event` — {event: "error", component, error_type, internal_user_id (if applicable), timestamp}

**Traces (critical paths):**
- End-to-end: Telegram Gateway → Entry Processor → NLP Engine → Data Repository → Alert Engine → Telegram Gateway (covers the entry-to-confirmation critical path)
- End-to-end: ParseAttempt Manager → Data Repository → Telegram Gateway (covers disambiguation prompt delivery)

### 11.2 Operational Dashboards (Conceptual)

| Dashboard | What to Monitor |
|-----------|----------------|
| **Bot health** | Bot uptime heartbeat; Telegram API connectivity status; process restarts |
| **Parse quality** | Rolling parse success rate (7-day window); ParseAttempt creation rate; disambiguation completion rate; ambiguous-entry percentage |
| **Alert reliability** | Alert evaluation count; dispatch success vs. failure rate; retry rate |
| **User activity** | Active user count; entries per day; chart request count |
| **Data lifecycle** | PendingDeletion accounts count and age; Deferred ParseAttempt count and age; scheduled process last run timestamp and outcome |
| **Errors** | Error event count by component; cascade deletion failures; Data Repository write failure rate |

---

## 12. Architectural Decisions (ADR-style)

### AD-1: Single-Process Monolith Architecture

- **Decision:** Deploy the system as a single process with logically separated, named components communicating in-process.
- **Alternatives considered:** (a) Microservices — each component as a separate deployable service; (b) Serverless functions — each flow as an independent function invocation.
- **Rationale:** The confirmed scale ceiling is 10 users (~100 metric time series). Distribution adds infrastructure complexity, network failure modes, and operational overhead that is disproportionate to the scale. A single-process design is the minimum viable architecture for this scope.
- **Trade-offs:** Single process = coupled failure modes (one crash takes down all components). Offset by: component separation enables future extraction into services if scale requires; process supervisor provides restart-on-failure. Microservices would require service discovery, distributed tracing, and network resilience logic — all cost without benefit at this scale.
- **Consequences:** Clear component interfaces must be enforced in code to preserve the future option to extract components. No shared mutable state between components except through the Data Repository.
- **Linked NFR/Business Goal:** AG-5 (operational simplicity); §8.2 scale ceiling; R-008 (single operator)

---

### AD-2: Telegram Gateway — Polling vs. Webhook

- **Decision:** Architecture is neutral between polling and webhook. The choice is deferred to deployment context. Webhook is preferred if the deployment platform supports a public HTTPS endpoint; polling is acceptable as a fallback.
- **Alternatives considered:** Long-polling (simpler, no public endpoint required); webhook (lower latency, more efficient, requires HTTPS endpoint).
- **Rationale:** Both approaches are functionally equivalent for the Telegram Bot API. Webhook eliminates the polling interval latency (up to ~1 s) and is more efficient. However, it requires a stable public HTTPS endpoint with a valid TLS certificate. If the deployment platform does not provide this, polling is a clean fallback with no additional latency concern at 10-user scale.
- **Trade-offs:** Polling adds ~1 s average latency to the entry ack budget; this is within the 5 s target but consumes part of the budget. Webhook eliminates this latency but adds deployment infrastructure requirements.
- **Consequences:** The Telegram Gateway component must be designed to support both modes behind the same interface. The mode is determined by configuration, not code changes.
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

- **Decision:** MetricActivityStatus is computed on-demand when requested (e.g., when computing the active user count for success metric reporting), not maintained as a continuously updated materialized view.
- **Alternatives considered:** (a) Event-driven: recompute on every Entry write; (b) Scheduled: recompute on periodicity boundary (daily or weekly); (c) Lazy: compute on read.
- **Rationale:** At ~100 time series, computation cost is negligible. Lazy computation is the lowest-complexity starting point (SU-005 recommendation). Event-driven recomputation on every Entry write is over-engineered for portfolio scale. Scheduled recomputation introduces a dependency on the Scheduled Process for a metric that may be queried at any time.
- **Trade-offs:** Lazy computation returns a value that reflects the state at query time — no staleness introduced by computation lag. Cost is paid on every read. At 100 time series this is acceptable; at 10,000+ time series, lazy computation would need to be replaced with a materialized view.
- **Consequences:** MetricActivityStatus is not a stored entity in the persistent sense — it is derived on every read. The Metric Manager owns this computation. Timezone handling (SU-007) is the primary accuracy risk.
- **Linked NFR/Business Goal:** AG-4 (success metrics measurable); business success metric: tracking retention >40%

---

### AD-5: Repository-Layer User Isolation

- **Decision:** Per-user data isolation is enforced at the Data Repository layer by including internal_user_id as a mandatory parameter in all data access operations, not at the application (component) layer via result filtering.
- **Alternatives considered:** Application-layer filtering: components retrieve data and filter by user_id before returning.
- **Rationale:** Application-layer filtering is vulnerable to a "miss one call" failure mode — a single missing filter clause would expose all users' data to the requesting user. Repository-layer enforcement means the query itself is scoped to a single user_id; a missing user_id is a structural error caught at the interface boundary, not a runtime filtering bug.
- **Trade-offs:** Repository-layer enforcement requires that all repository access functions include user_id as a mandatory typed parameter, which adds boilerplate. This cost is justified by the security guarantee. Cross-user visibility is a 100% non-negotiable target (R-005).
- **Consequences:** The Data Repository interface must be designed with user_id as a first-class parameter on every read and write operation. No "get all" operations may exist in the public repository interface that are not scoped by user_id.
- **Linked NFR/Business Goal:** AG-3 (user data isolation); R-005 (cross-user leak — critical); business success metric: 100% isolation

---

### AD-6: Two-Phase Chart Response

- **Decision:** Chart requests receive an immediate acknowledgment message (≤ 5 s) followed by the actual chart image delivered asynchronously (≤ 30 s from request).
- **Alternatives considered:** Single-phase: block the response until the chart is generated and deliver it in one message.
- **Rationale:** Chart generation is computationally heavier than simple data lookups. If the system blocks for up to 30 s before responding, the user has no indication their request was received — violating the perception of responsiveness. A two-phase response provides immediate user feedback within the 5 s entry ack target, then delivers the chart image when ready.
- **Trade-offs:** Two-phase requires the Telegram Gateway and Chart Generator to coordinate the two-step dispatch. It adds implementation complexity (background coroutine or thread for chart generation). The alternative (single-phase, 30 s block) risks user re-submission and Telegram bot timeout behavior.
- **Consequences:** Chart Generator must support asynchronous execution. Telegram Gateway must support sending a follow-up message to a specific user after an initial acknowledgment. If chart generation fails, the error message is sent as the second message.
- **Linked NFR/Business Goal:** AG-1 (response latency); §8.1 chart ack ≤ 5 s; chart delivery ≤ 30 s

---

## 13. Risks & Open Questions

### 13.1 Architecture Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|-----------|
| NLP parsing latency exceeds the 5 s entry ack budget if an external service is required | High — users experience delayed feedback; core UX proposition undermined | Medium — depends on NLP library/service choice (not yet decided) | Prefer in-process NLP library; if external, measure latency early and budget accordingly; structured command fallback (/log) as escape hatch if latency is persistently above target |
| Data Repository backup gap — no backup strategy defined | High — data loss on Repository failure; D-013 retention obligation unmet | Medium — backup strategy is a known NFR unknown | Define backup frequency and restoration procedure before first deployment; even a simple daily file backup satisfies D-013 at this scale |
| Scheduled Process is a single point of failure for all time-triggered obligations | High — PendingDeletion purges never happen; stale Deferred ParseAttempts accumulate | Medium — scheduler failure is silent unless heartbeat monitored | Heartbeat event in Observability Collector; operator alert if heartbeat absent; design process to be idempotent and re-runnable manually |
| Open bot registration (R-018) causes user count to exceed the 20-user architecture ceiling | Medium — system degrades without warning above ceiling | Low–Medium (if bot address leaks publicly) | Document the ceiling explicitly; add access control mechanism (allowlist or invite codes) before any public sharing |
| PII in Observability logs (raw_input accidentally logged) | Medium — privacy breach via log access; raw_input contains personal data | Low — if log schema is reviewed at design time | Enforce a structured event schema that references only IDs (user_id, entry_id) and metrics, never free-text content |

### 13.2 Open Questions

1. **NLP library or service choice** — Blocks: in-process vs. external decision; entry ack latency estimate; AD-1 monolith trade-off confirmation. *Impact: High.*
2. **Deployment platform** — Blocks: polling vs. webhook decision (AD-2); scheduled process implementation (cron, in-process scheduler, or platform-native); process supervisor choice. *Impact: Medium.*
3. **Data Repository technology** — Blocks: transaction semantics for cascade deletion atomicity (§8.3); unique-constraint-on-Telegram-ID implementation (AD-5); backup strategy. *Impact: High.*
4. **ParseAttempt expiry timeout (SU-001)** — Recommended starting value: 24 hours. Must be confirmed and made configurable. *Impact: Medium.*
5. **NLP confidence threshold (SU-002)** — Must be defined before the NLP Engine can distinguish auto-parse from ParseAttempt creation. Directly impacts the 85% parse success target. *Impact: High.*
6. **Stale Deferred ParseAttempt cleanup window (SU-006)** — Recommended starting value: 30 days. Must be confirmed and configurable. *Impact: Low.*
7. **Scheduled Process cadence** — Worst-case delay between PendingDeletion grace period expiry and actual purge. At most, this should be less than the grace period duration (3 days). *Impact: Medium.*
8. **SU-004: Alert evaluation on Archived metrics** — Should Active alerts on an Archived metric still fire? Logical default: suspend evaluation when Metric.status = Archived. Needs stakeholder confirmation. *Impact: Low.*
9. **Chart rendering library** — Blocks: chart delivery latency estimate; image size constraints; AD-6 two-phase feasibility. *Impact: Medium.*
10. **Timezone handling for MetricActivityStatus (SU-007)** — UTC as default is confirmed in System v0.7. Per-user timezone is a future enhancement. No blocking decision required for v1. *Impact: Low.*

---

## 14. Traceability Matrix

| Business Goal | Architectural Goal | Component | Key Decision | Risk |
|--------------|-------------------|-----------|-------------|------|
| Reduce tracking abandonment (retention >40%) | AG-1 (≤5 s ack); AG-6 (graceful NLP degradation) | Telegram Gateway; NLP Parsing Engine; Entry Processor; ParseAttempt Manager | AD-1 (monolith); AD-3 (post-commit alert eval); AD-6 (two-phase chart) | R-002 (parse failures); R-009 (NLP accuracy); R-014 (ParseAttempt expiry) |
| Enable self-insight through history | AG-2 (reliable entry storage); AG-4 (measurable metrics) | Data Repository; Chart Generator; Alert Engine; Metric Manager | AD-4 (lazy MetricActivityStatus); AD-5 (repository-layer isolation); AD-6 (two-phase chart) | R-002 (immutable wrong entry); R-006 (no export); R-016 (chart failure) |
| User data privacy and trust | AG-3 (user isolation); AG-7 (lifecycle enforcement) | Data Repository; Account Manager; Scheduled Process; Metric Manager (cascade) | AD-5 (repository-layer isolation); AD-7 (atomic cascade) | R-005 (cross-user leak — critical); R-007 (raw_input residual); R-017 (raw_input PII); R-018 (open registration) |
| Service continuity | AG-5 (operational simplicity); AG-7 (lifecycle enforcement) | Scheduled Process; Observability Collector; Configuration & Secrets | AD-1 (monolith + process supervisor); AD-2 (polling/webhook) | R-008 (single operator); R-013 (persistence failure); scheduled process failure |
| Portfolio demonstration (all success metrics at target) | AG-4 (all metrics measurable) | Observability Collector; all components emitting structured events | All ADs — observability is a cross-cutting concern | R-009 (parse accuracy unmeasurable without observability); R-012 (MetricActivityStatus stale); R-018 (inflated user count) |

---

## Governance Block

### Version
v0.1

### Based On
Business v0.5 + Context v0.7

### Changes Introduced
- Initial architecture document produced from Business Analysis v0.5 and System Analysis v0.7
- Six architectural decisions defined (AD-1 through AD-6)
- Ten open questions identified (seven carry-over NFR unknowns from System v0.7 + three new architecture-level questions)
- Five architecture risks identified

### Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|----|----------|-----------|---------|--------|
| AD-1 | Single-process monolith | ~10-user scale; operational simplicity; component separation preserves future extraction option | v0.1 | Confirmed |
| AD-2 | Polling vs. webhook — deferred to deployment context; webhook preferred | Platform constraints not yet known; both options satisfy functional requirements | v0.1 | Open — pending deployment platform decision |
| AD-3 | Post-commit in-process alert evaluation | Entry storage must not be rolled back on alert failure; in-process sufficient at this scale | v0.1 | Confirmed |
| AD-4 | MetricActivityStatus lazy computation on read | Lowest complexity at portfolio scale; SU-005 recommendation | v0.1 | Confirmed |
| AD-5 | Repository-layer user isolation | Security boundary — application-layer filtering is vulnerable to miss-one-call failures | v0.1 | Confirmed |
| AD-6 | Two-phase chart response | Immediate acknowledgment ≤5 s required; chart generation may take up to 30 s | v0.1 | Confirmed |

### Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|----|------|-------------|--------|-----------------|
| AU-001 | Architecture | NLP library/service not chosen — affects in-process vs. external decision and entry ack latency budget | High | Evaluate candidate NLP libraries early in implementation; benchmark latency before committing to architecture |
| AU-002 | Architecture | Deployment platform not specified — affects polling vs. webhook (AD-2) and scheduled process implementation | Medium | Determine before implementation begins |
| AU-003 | Architecture | Data Repository technology not chosen — affects transaction semantics, unique constraint implementation, and backup strategy | High | Choose before any implementation of flows with atomicity requirements (Flows 1, 10, 11) |
| SU-001 | System (carried) | ParseAttempt expiry timeout — recommended 24 h | Medium | Confirm at implementation; make configurable |
| SU-002 | System (carried) | NLP confidence threshold — undefined | High | Define at NLP library/service selection time |
| SU-006 | System (carried) | Stale Deferred ParseAttempt cleanup window — recommended 30 days | Low | Confirm at implementation; make configurable |
| SU-007 | System (carried) | Timezone handling — UTC default confirmed; per-user timezone deferred | Low | No action required for v1 |
| SU-008 | Business (carried) | raw_input GDPR classification not formally assessed | Medium | Accept for portfolio scope; review before scaling |
