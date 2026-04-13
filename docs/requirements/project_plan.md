# Delivery Plan

---

## 1. Requirements Index

| # | Requirement |
|---|-------------|
| R-1 | FR-1: Idempotent User Registration (Onboarding) |
| R-2 | FR-2: Account Status Gate |
| R-3 | FR-3: Conversation State Routing |
| R-4 | FR-4: Standard Data Entry (Auto-Parsed) |
| R-5 | FR-5: Ambiguous Entry — ParseAttempt Lifecycle |
| R-6 | FR-6: Metric Auto-Creation (on first entry for unrecognized name) |
| R-7 | FR-7: Explicit Metric Creation |
| R-8 | FR-8: Metric Listing |
| R-9 | FR-9: Metric Archival and Reactivation |
| R-10 | FR-10: Metric Deletion with Cascade |
| R-11 | FR-11: Alert Configuration |
| R-12 | FR-12: Alert Evaluation (Post-Entry) |
| R-13 | FR-13: Alert Re-arming |
| R-14 | FR-14: Chart Generation and Delivery |
| R-15 | FR-15: Late Categorization of Deferred ParseAttempts |
| R-16 | FR-16: Account Deletion with Grace Period |
| R-17 | FR-17: Account Restoration |
| R-18 | FR-18: Scheduled Data Purge and Retention Enforcement |
| NFR-1 | Entry acknowledgment latency ≤5s p95 |
| NFR-2 | Disambiguation prompt latency ≤5s p95 |
| NFR-3 | Chart acknowledgment latency ≤5s p95 |
| NFR-4 | Chart delivery latency ≤30s p95 |
| NFR-5 | Monthly uptime ≥95% |
| NFR-6 | Entry immutability — no UPDATE on Entry table |
| NFR-7 | Per-user data isolation — all queries scoped by internal_user_id |
| NFR-8 | Telegram token confidentiality — token never in source, logs, or observability |
| NFR-9 | raw_input exclusion from observability events |
| NFR-10 | 100% of NLP attempts emit parse_outcome_event |
| NFR-11 | 100% of alert evaluations emit alert_evaluation_event |
| NFR-12 | One scheduler heartbeat per interval; gap = incident |
| NFR-13 | No Active user data purged before 1 year |
| NFR-14 | Purge no earlier than 72h after deletion_scheduled_timestamp |
| NFR-15 | Stable at 20 concurrent users |
| NFR-16 | All raw_input fields purged on cascade deletion |
| NFR-17 | Zero dangling Pending ParseAttempts after detection window |
| NFR-18 | Zero duplicate (internal_user_id, metric_name) pairs |

---

## 2. Dependency Map

| Requirement | Depends On | Reason |
|-------------|------------|--------|
| R-2 | R-1 | Account Status Gate presupposes InternalUser records exist |
| R-3 | R-1 | Conversation State Routing presupposes users are registered |
| R-4 | R-1, R-2, R-3 | Data Entry requires a registered user, status gate, and state routing |
| R-5 | R-3, R-4 | ParseAttempt Lifecycle is a branching outcome of the entry path; requires state routing |
| R-6 | R-3, R-4 | Metric auto-creation is triggered during the data entry flow |
| R-7 | R-1, R-2 | Explicit Metric Creation requires a registered, active user |
| R-8 | R-7 | Metric Listing is only meaningful once metrics can exist |
| R-9 | R-7 | Archival and Reactivation operate on existing Metric records |
| R-10 | R-7, R-3 | Metric Deletion requires Metric records and conversation state for confirmation |
| R-11 | R-7 | Alert Configuration targets a named Metric |
| R-12 | R-4, R-11 | Alert Evaluation fires after an Entry is stored and requires Alert records |
| R-13 | R-12 | Re-arming targets an Alert in Triggered status, which only Alert Evaluation produces |
| R-14 | R-4 | Chart requires Entry history to exist |
| R-15 | R-5 | Late Categorization operates on Deferred ParseAttempts |
| R-16 | R-1, R-2, R-3 | Account Deletion requires a registered user, status gate, and state routing |
| R-17 | R-16 | Restoration is only reachable from PendingDeletion state |
| R-18 | R-1, R-5, R-6, R-16 | Purge jobs target records created by registration, ParseAttempts, periodicity flows, and deletion requests |

---

## 3. Delivery Stages

---

### Stage 1: Core Registration and Auto-Parsed Entry

**Goal:**
A user can send a message to the bot, be registered automatically, and log a numeric entry against a known metric end-to-end.

**Functional Scope:**

| Req | Requirement (verbatim) | Included / Partial | Notes                                                                                                                                                                  |
|-----|------------------------|--------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| R-1 | FR-1: Idempotent User Registration (Onboarding) | Included | Full atomic check-and-create; onboarding message dispatched; fallback to FR-4 if first message is parseable                                                            |
| R-2 | FR-2: Account Status Gate | Included | Guard runs on every inbound message from this stage forward                                                                                                            |
| R-3 | FR-3: Conversation State Routing | Partial | Idle stasave te and PendingPeriodicity routing only; PendingDisambiguation, PendingMetricDeletionConfirmation, PendingRestorationConfirmation deferred to later stages |
| R-4 | FR-4: Standard Data Entry (Auto-Parsed) | Included | Full happy path including auto-create flow, atomic Entry creation, Alert Engine trigger stub (no alerts yet), parse_outcome_event emission, confirmation dispatch      |
| R-6 | FR-6: Metric Auto-Creation (on first entry for unrecognized name) | Included | Periodicity prompt, PendingPeriodicity state, atomic Metric + Entry creation, SU-009 timeout cleanup stub                                                              |
| R-7 | FR-7: Explicit Metric Creation | Included | /metric_create command with full field validation and confirmation                                                                                                     |
| NFR-6 | Entry immutability — no UPDATE on Entry table | Included | Schema enforced from first migration; measurable from this stage                                                                                                       |
| NFR-7 | Per-user data isolation — all queries scoped by internal_user_id | Included | Applied to all queries from first persistence layer; measurable from this stage                                                                                        |
| NFR-8 | Telegram token confidentiality | Included | Environment-variable loading enforced from initial setup; measurable from this stage                                                                                   |
| NFR-10 | 100% of NLP attempts emit parse_outcome_event | Included | parse_outcome_event emitted on every auto-parse outcome; measurable from this stage                                                                                    |
| NFR-15 | Stable at 20 concurrent users | Partial | Concurrency controls (SQLite WAL, atomic check-and-create) in place; load verification deferred to Stage 4                                                             |
| NFR-18 | Zero duplicate (internal_user_id, metric_name) pairs | Included | Unique constraint in schema from first migration; measurable from this stage                                                                                           |

**Working Condition:**
A real Telegram user can send a free-text message containing a numeric value to the bot, be registered on first contact, receive an onboarding message, and receive a confirmation that the entry was logged. A user can also issue /metric_create to explicitly define a metric before entering data. The bot rejects messages from unknown states gracefully and persists all state across restarts.

**Deliverable:**
A runnable single-process bot binary connected to a SQLite database. A developer or stakeholder can start the process, open Telegram, and walk through registration and entry logging without any manual setup beyond providing the bot token.

**Acceptance Criteria:**

1. Given a Telegram user whose ID is not in the InternalUser store, when they send any first message, then exactly one InternalUser record is created with account_status = Active, no personal data stored, and an onboarding message is dispatched.
2. Given two concurrent first messages from the same Telegram user ID, when both are processed simultaneously, then exactly one InternalUser record exists afterward (no duplicate).
3. Given a registered user whose first message is parseable as a data entry, when onboarding succeeds, then FR-4 processing is attempted and the user receives a confirmation or a re-submit notice.
4. Given a registered Active user with an existing Metric, when they send a free-text message with NLP confidence >= threshold, then an Entry record is created atomically, a parse_outcome_event is emitted, and a confirmation message is dispatched within 5 seconds (p95).
5. Given a registered Active user whose free-text message names an unrecognized metric, when the bot processes the message, then a periodicity prompt is dispatched, ConversationState is set to PendingPeriodicity, and on the user's periodicity reply the Metric and Entry are created atomically.
6. Given a PendingPeriodicity state that has not been resolved within SU-009 timeout (24h), when the scheduler or timeout handler fires, then ConversationState is cleared and no Metric or Entry record exists.
7. Given a registered user issuing /metric_create with valid name, periodicity, optional unit and dimension_names, when the command is processed, then a Metric record with status = Active is created and a confirmation with metric_id is returned.
8. Given /metric_create with a name that duplicates an existing (internal_user_id, metric_name) pair, when the command is processed, then no duplicate Metric is created and an appropriate error is returned.
9. Given any inbound message, when the bot reads the Entry table logs, then no UPDATE statement is present against any Entry row.
10. Given any query in the persistence layer, when executed, then internal_user_id is present as a filter on every query touching user-owned data.
11. Given the running process, when the environment is inspected (source code, log output, observability events), then the Telegram bot token does not appear in any of them.
12. Given any NLP parsing attempt, when the outcome is determined, then a parse_outcome_event is emitted and raw_input does not appear in the event payload.

**Excluded from this stage:**
R-5 (Ambiguous Entry), R-8 (Metric Listing), R-9 (Archival/Reactivation), R-10 (Metric Deletion), R-11 (Alert Configuration), R-12 (Alert Evaluation), R-13 (Alert Re-arming), R-14 (Chart Generation), R-15 (Late Categorization), R-16 (Account Deletion), R-17 (Account Restoration), R-18 (Scheduled Purge), PendingDisambiguation/PendingMetricDeletionConfirmation/PendingRestorationConfirmation routing branches of R-3.

---

### Stage 2: Ambiguous Entry, Metric Management, and Deferred Categorization

**Goal:**
Users can handle NLP ambiguity through a disambiguation flow, manage their metric catalogue (list, archive, reactivate, delete), and retroactively categorize deferred entries.

**Functional Scope:**

| Req | Requirement (verbatim) | Included / Partial | Notes |
|-----|------------------------|--------------------|-------|
| R-3 | FR-3: Conversation State Routing | Partial (completing) | PendingDisambiguation and PendingMetricDeletionConfirmation routing branches added; PendingRestorationConfirmation deferred to Stage 3 |
| R-5 | FR-5: Ambiguous Entry — ParseAttempt Lifecycle | Included | Full lifecycle: ParseAttempt creation, disambiguation prompt, PendingDisambiguation state, resolution paths (Resolved/Deferred/expiry), atomicity compensation on prompt failure, parse_outcome_event |
| R-8 | FR-8: Metric Listing | Included | /metric_list with MetricActivityStatus computation (5-period window, periods_filled, Active/Inactive label) |
| R-9 | FR-9: Metric Archival and Reactivation | Included | /metric_archive and /metric_reactivate with alert evaluation suspension/resumption semantics |
| R-10 | FR-10: Metric Deletion with Cascade | Included | /metric_delete confirmation flow, PendingMetricDeletionConfirmation state, atomic cascade, rollback on any write failure, cascade deletion event |
| R-15 | FR-15: Late Categorization of Deferred ParseAttempts | Included | /deferred_list and /deferred_categorize commands, Entry creation from Deferred ParseAttempt, late_categorization_event |
| NFR-2 | Disambiguation prompt latency ≤5s p95 | Included | Measurable from this stage when disambiguation path is exercised |
| NFR-9 | raw_input exclusion from observability events | Partial (completing) | ParseAttempt and late_categorization_event added; raw_input exclusion verified across all new events |
| NFR-16 | All raw_input fields purged on cascade deletion | Included | Cascade deletion in R-10 covers Entry.raw_input, ParseAttempt.raw_input; verifiable from this stage |
| NFR-17 | Zero dangling Pending ParseAttempts after detection window | Included | Atomicity compensation on prompt failure prevents dangling Pending records; verifiable from this stage |

**Working Condition:**
A user whose free-text input is ambiguous receives a disambiguation prompt and can either select a metric (creating an Entry) or defer the attempt. The user can list all their metrics with activity indicators, archive or reactivate metrics, delete a metric with all its cascade data, and retroactively assign a deferred entry to a metric.

**Deliverable:**
An updated bot process. A stakeholder can test every metric management command and walk through the ambiguous entry resolution paths end-to-end in Telegram.

**Acceptance Criteria:**

1. Given a registered Active user whose free-text message produces NLP confidence < threshold or outcome = ambiguous, when the bot processes the message, then a ParseAttempt with status = Pending is created, a disambiguation prompt is dispatched, and ConversationState is set to PendingDisambiguation within 5 seconds (p95).
2. Given a disambiguation prompt dispatch failure, when the failure is detected, then the ParseAttempt is deleted atomically (no dangling Pending ParseAttempts remain).
3. Given a user in PendingDisambiguation state who selects a metric, when the response is processed, then an Entry is created, ParseAttempt status = Resolved, and ConversationState returns to Idle.
4. Given a user in PendingDisambiguation state who defers, or a ParseAttempt whose expiry (24h) passes, when processed, then ParseAttempt status = Deferred and ConversationState returns to Idle.
5. Given a registered user issuing /metric_list, when the command is processed, then all Active and Archived Metrics are returned with name, periodicity, unit, MetricActivityStatus (periods_filled count, Active if ≥4 of last 5 periods filled).
6. Given a registered user issuing /metric_archive on an Active metric, when processed, then Metric status changes and alert evaluation is suspended for that metric.
7. Given a registered user issuing /metric_reactivate on an Archived metric, when processed, then Metric status is restored and alert evaluation resumes.
8. Given a registered user issuing /metric_delete, when the confirmation prompt is dispatched and confirmed, then the Metric record, all Entries (including raw_input), all Alerts, all ParseAttempts (including raw_input), and MetricActivityStatus are deleted atomically; a cascade deletion event is emitted.
9. Given a metric deletion where any individual write in the cascade fails, when the failure occurs, then all writes are rolled back and no partial deletion state exists.
10. Given a registered user issuing /deferred_list, when processed, then all Deferred ParseAttempts are returned with raw_input and created_timestamp.
11. Given a registered user issuing /deferred_categorize with a valid Deferred ParseAttempt and Active Metric, when processed, then an Entry is created, ParseAttempt status = Resolved, and a late_categorization_event is emitted without raw_input in the payload.
12. Given any new observability event emitted in this stage, when the payload is inspected, then raw_input does not appear in any field.

**Excluded from this stage:**
R-11 (Alert Configuration), R-12 (Alert Evaluation), R-13 (Alert Re-arming), R-14 (Chart Generation), R-16 (Account Deletion), R-17 (Account Restoration), R-18 (Scheduled Purge), PendingRestorationConfirmation routing branch of R-3.

---

### Stage 3: Alerting, Account Lifecycle, and Restoration

**Goal:**
Users can configure threshold alerts on metrics, receive automated notifications when thresholds are breached, re-arm fired alerts, and manage their account deletion and restoration within the 72-hour grace window.

**Functional Scope:**

| Req | Requirement (verbatim) | Included / Partial | Notes |
|-----|------------------------|--------------------|-------|
| R-3 | FR-3: Conversation State Routing | Included (completing) | PendingRestorationConfirmation routing branch added; all four non-Idle states now handled |
| R-11 | FR-11: Alert Configuration | Included | /alert_set with metric, target_dimension, condition, threshold_value validation; Alert record creation; confirmation |
| R-12 | FR-12: Alert Evaluation (Post-Entry) | Included | Post-commit trigger, Active Alert retrieval, condition evaluation, Triggered status update, notification dispatch with single retry, alert_evaluation_event, non-rollback guarantee on failure |
| R-13 | FR-13: Alert Re-arming | Included | /alert_rearm on Triggered Alert; status reset to Active; last_triggered_timestamp retained; confirmation |
| R-16 | FR-16: Account Deletion with Grace Period | Included | /account_delete confirmation, PendingDeletion status, deletion_scheduled_timestamp = now() + 72h, active Pending ParseAttempts transitioned to Deferred |
| R-17 | FR-17: Account Restoration | Included | PendingDeletion message routing to restoration prompt, PendingRestorationConfirmation state, on confirmation account_status = Active and deletion_scheduled_timestamp cleared |
| NFR-11 | 100% of alert evaluations emit alert_evaluation_event | Included | Measurable from this stage |
| NFR-14 | Purge no earlier than 72h after deletion_scheduled_timestamp | Partial | Grace period is set correctly here; enforcement verified in Stage 4 when the scheduler runs |

**Working Condition:**
A user can set an alert on a metric and receive a Telegram notification the next time an entry breaches the threshold. They can re-arm the alert after it fires. A user who requests account deletion enters a grace period and can restore their account by sending any message within 72 hours. Messages from PendingDeletion users are intercepted and routed to the restoration prompt.

**Deliverable:**
An updated bot process. A stakeholder can configure alerts, trigger them by logging entries, verify notification delivery, test re-arming, and walk through the account deletion and restoration flow in Telegram.

**Acceptance Criteria:**

1. Given a registered user issuing /alert_set with valid metric, condition (above|below), and numeric finite threshold_value, when processed, then an Alert record with status = Active is created and a confirmation is returned.
2. Given /alert_set with an invalid field (non-finite threshold, missing required target_dimension for compound metric, unrecognized condition), when processed, then no Alert is created and a validation error is returned.
3. Given an Entry is committed for a metric with an Active Alert whose condition is met, when alert evaluation runs, then the Alert status is set to Triggered, last_triggered_timestamp is set, a notification is dispatched (with one retry on failure), and an alert_evaluation_event is emitted without raw_input.
4. Given an Entry is committed for a metric with an Active Alert whose condition is not met, when alert evaluation runs, then Alert status remains Active and no notification is dispatched.
5. Given alert evaluation fails (notification error, database error), when the failure is handled, then the Entry record is not rolled back.
6. Given an Entry is committed for an Archived metric with alerts, when alert evaluation runs, then no alerts are evaluated and no notifications are dispatched.
7. Given 100 Entry submissions each triggering alert evaluation, when logs are inspected, then exactly 100 alert_evaluation_events were emitted.
8. Given a registered user issuing /alert_rearm with a Triggered alert_id, when processed, then Alert status = Active, last_triggered_timestamp is unchanged, and a confirmation is returned.
9. Given /alert_rearm with an alert_id whose status is Active (not Triggered), when processed, then an appropriate error is returned.
10. Given a registered Active user issuing /account_delete and confirming, when processed, then account_status = PendingDeletion, deletion_scheduled_timestamp = now() + 72h, and any active Pending ParseAttempts are transitioned to Deferred.
11. Given a user with account_status = PendingDeletion who sends any message, when processed, then the message is routed to a restoration prompt regardless of message content.
12. Given a PendingDeletion user who confirms restoration, when processed, then account_status = Active, deletion_scheduled_timestamp is cleared, and the user can immediately log entries.
13. Given a PendingDeletion user whose grace period has not expired, when they send any message and confirm restoration, then restoration succeeds; given the grace period has expired, then restoration is impossible.

**Excluded from this stage:**
R-14 (Chart Generation), R-18 (Scheduled Purge). Full enforcement of NFR-14 purge timing deferred to Stage 4.

---

### Stage 4: Chart Generation, Scheduled Purge, and Observability Completion

**Goal:**
Users receive visual time-series charts of their metric history, and the system self-maintains through a scheduled purge job that enforces retention policy, cleans stale records, and emits heartbeats.

**Functional Scope:**

| Req | Requirement (verbatim) | Included / Partial | Notes |
|-----|------------------------|--------------------|-------|
| R-14 | FR-14: Chart Generation and Delivery | Included | /chart command, immediate acknowledgment ≤5s, background coroutine, time-series image generation, Telegram delivery ≤30s, error dispatch on failure, chart_invocation_event and chart_delivery_outcome_event |
| R-18 | FR-18: Scheduled Data Purge and Retention Enforcement | Included | Scheduled interval ≤12h, run-lock, four purge jobs (PendingDeletion cascade, 1-year retention review event, stale Deferred ParseAttempt cleanup, stale PendingPeriodicity cleanup), scheduler_heartbeat, idempotency |
| NFR-1 | Entry acknowledgment latency ≤5s p95 | Included (verifying) | Formal latency measurement under concurrent load; first stage where all entry paths exist to measure holistically |
| NFR-2 | Disambiguation prompt latency ≤5s p95 | Included (verifying) | Same rationale |
| NFR-3 | Chart acknowledgment latency ≤5s p95 | Included | Measurable from this stage |
| NFR-4 | Chart delivery latency ≤30s p95 | Included | Measurable from this stage |
| NFR-5 | Monthly uptime ≥95% | Included (verifying) | Monitoring and uptime tracking established; baseline measurable once the complete system is deployed |
| NFR-12 | One scheduler heartbeat per interval; gap = incident | Included | Heartbeat emitted per run; gap detection alerting wired |
| NFR-13 | No Active user data purged before 1 year | Included | Retention review event confirms no auto-deletion; verifiable in purge job logic |
| NFR-14 | Purge no earlier than 72h after deletion_scheduled_timestamp | Included (completing) | Purge job enforces timestamp guard; verifiable |
| NFR-15 | Stable at 20 concurrent users | Included (completing) | Load test with 20 concurrent users across all paths |

**Working Condition:**
A user can request a chart of any metric and receive a time-series image in Telegram. The system automatically purges accounts past their deletion grace period, cleans stale ParseAttempts and periodicity states, emits a retention review event for long-lived data, and emits a heartbeat every scheduled interval. The complete system is stable under 20 concurrent users.

**Deliverable:**
The complete, production-ready bot process. All functional requirements are implemented. A stakeholder can use every command, receive charts, and observe the scheduler heartbeat and purge activity in the event log.

**Acceptance Criteria:**

1. Given a registered user issuing /chart with a valid metric and optional time range, when the command is processed, then an acknowledgment message is dispatched within 5 seconds (p95).
2. Given the background chart coroutine completes successfully, when it finishes, then a time-series chart image is delivered to the user via Telegram within 30 seconds (p95) of the /chart command, and a chart_delivery_outcome_event is emitted without raw_input.
3. Given the background chart coroutine fails, when the failure is detected, then an error message is dispatched to the user.
4. Given a chart_invocation_event and chart_delivery_outcome_event, when their payloads are inspected, then raw_input does not appear in any field.
5. Given the scheduler runs, when at any run interval ≤12h, then a run-lock prevents any concurrent invocation of the same job.
6. Given an InternalUser with account_status = PendingDeletion and deletion_scheduled_timestamp ≤ now(), when the purge job runs, then the user record and all associated data are deleted atomically (cascade).
7. Given an InternalUser with account_status = PendingDeletion and deletion_scheduled_timestamp > now(), when the purge job runs, then the user record is not deleted.
8. Given an Active InternalUser whose last_interaction_timestamp is ≥1 year ago, when the purge job runs, then a retention_review_event is emitted and the user record is not deleted.
9. Given a Deferred ParseAttempt older than SU-006 default (30 days), when the purge job runs, then that ParseAttempt is transitioned to Expired.
10. Given a PendingPeriodicity state older than SU-009 default (24h), when the purge job runs, then that state is cleared and no Metric or Entry was created.
11. Given every successful scheduler run, when the run completes, then exactly one scheduler_heartbeat event is emitted; given two consecutive heartbeats with a gap exceeding the scheduled interval, then an incident condition is detectable.
12. Given 20 concurrent users each submitting entries and commands simultaneously, when load is sustained, then the system remains stable (no crashes, no data corruption, no duplicate records), and NFR-1 and NFR-2 latency targets are met.
13. Given all purge job operations, when any individual operation is re-run (idempotency test), then no additional deletions or state changes occur.

**Excluded from this stage:**
Nothing. All requirements are covered by the end of this stage.

---

## 4. Stage Summary Table

| Stage | Title | Requirements Covered | Key Deliverable |
|-------|-------|----------------------|-----------------|
| 1 | Core Registration and Auto-Parsed Entry | R-1, R-2, R-3 (partial), R-4, R-6, R-7, NFR-6, NFR-7, NFR-8, NFR-10, NFR-15 (partial), NFR-18 | Runnable bot: register and log entries end-to-end |
| 2 | Ambiguous Entry, Metric Management, and Deferred Categorization | R-3 (partial completion), R-5, R-8, R-9, R-10, R-15, NFR-2, NFR-9 (completion), NFR-16, NFR-17 | Full metric catalogue management and ambiguity resolution |
| 3 | Alerting, Account Lifecycle, and Restoration | R-3 (completion), R-11, R-12, R-13, R-16, R-17, NFR-11, NFR-14 (partial) | Threshold alerts, notifications, and account grace period flow |
| 4 | Chart Generation, Scheduled Purge, and Observability Completion | R-14, R-18, NFR-1, NFR-2, NFR-3, NFR-4, NFR-5, NFR-12, NFR-13, NFR-14 (completion), NFR-15 (completion) | Complete production system with charts, purge scheduler, and load verification |

---

## 5. Unplaceable Requirements

All requirements placed.

---

## 6. Planning Assumptions

1. **OI-3 resolved as SQLite with WAL mode.** The spec recommends SQLite with WAL mode (ACID, unique constraints, atomic check-and-set, ConversationState persistence). This assumption is required because no persistence layer component can be designed or staged without a concrete data store. If this assumption is wrong and a different database is chosen, the concurrency model, migration tooling, run-lock mechanism (FR-18), and the atomic check-and-create pattern (FR-1, FR-6) may require redesign, which could add effort to Stage 1 and alter the Stage 4 purge lock implementation.

2. **OI-2 resolved as a rule-based NLP parser (no external service).** The spec recommends a zero-cost, local rule-based parser. This assumption is required because FR-4 and FR-5 branch on NLP confidence scores and parse outcomes, so the parser interface must be defined before any entry processing can be implemented. If this assumption is wrong and an external NLP service is chosen instead, FR-4 and FR-5 gain an external network dependency, the confidence threshold model changes, data-transfer privacy constraints apply to raw_input (see NFR-9), and Stage 1 scope expands to include service integration and failure-mode handling.

3. **ConversationState is stored in the SQLite database, not in process memory.** FR-3 requires state to survive process restarts. This is achievable only if state is persisted externally to the process. The SQLite assumption (PA-1) makes this natural, but the assumption is stated explicitly because it governs every state transition across all stages. If state were stored in memory only, FR-3 would be violated on any restart, and Stages 2 and 3 conversation flows would produce inconsistent behavior.

4. **"Single retry" in FR-12 means one additional attempt immediately after the first failure, with no backoff queue.** This is the simplest interpretation consistent with the monolith architecture and ≤20 user target. If the intended behavior is a durable retry queue or exponential backoff, the alert notification subsystem in Stage 3 would require a job queue component not currently described in the spec.

5. **Scheduler_lock (FR-18 run-lock) is implemented as an atomic check-and-set on the scheduler_lock entity in SQLite.** This is consistent with the monolith target and SQLite WAL recommendation. If the system is ever horizontally scaled beyond one process, this lock mechanism would be insufficient and would need replacement with a distributed lock.

6. **MetricActivityStatus (FR-8) is computed on read, not stored as a persistent materialized record.** The data model lists MetricActivityStatus as an entity, but the requirement describes it purely as a derived computation over Entry history (last 5 periods). It is treated as a computed view. If it must be stored and separately maintained, an update trigger mechanism would be needed and its cascade deletion in FR-10 would gain meaning as a persistent row deletion rather than a no-op.

---

## 7. Open Questions

1. **What is the unit of "period" for MetricActivityStatus computation in FR-8?**
   Affected stages: Stage 2.
   FR-8 states "count distinct periods with ≥1 entry in last 5 periods" and "periods_filled 0–5." It is not specified whether "period" means the metric's own periodicity (daily or weekly as defined in FR-7) or a fixed calendar window. Resolution A: period = the metric's configured periodicity (daily metric uses calendar days, weekly metric uses calendar weeks) — this is the most coherent interpretation and aligns with FR-7's periodicity field. Resolution B: period is a fixed unit (e.g., always a calendar week) — this would make MetricActivityStatus independent of periodicity but inconsistent with a daily-tracked metric. If Resolution B is intended, the computation logic and the meaning of "Active" status change materially.

2. **Does FR-12 alert evaluation apply to Entries added to Archived metrics via FR-9 ("Entries can still be added to Archived metrics")?**
   Affected stages: Stage 2, Stage 3.
   FR-9 states entries can still be added to Archived metrics. FR-12 states "Skip if Metric.status = Archived." This means alerts are never evaluated for Archived metrics even when new entries arrive — which is the literal reading of both requirements and is planned accordingly. However, if the intent is that archival only suspends periodic alert evaluation but not entry-triggered evaluation, Stage 3's alert evaluation logic would need a conditional and the acceptance criteria for FR-9 archival behavior would change.

3. **What is the scope of "target_dimension = null for single-value" in FR-11?**
   Affected stages: Stage 3.
   FR-11 states target_dimension is null for single-value metrics and required for compound metrics. The data model references dimension_names in FR-7 but does not define what a "compound metric" is structurally (a metric with multiple named dimensions vs. a metric with a vector-valued entry). If compound metrics are multi-dimensional entries each stored as a separate Entry row, the alert evaluation logic in FR-12 is straightforward. If a compound Entry stores multiple values in a single row, FR-12's "compare entry value against threshold" requires a dimension extraction step that is not described. This would affect the Entry schema and the alert evaluation implementation in Stage 3.

---

## Governance Block

### Plan Version
v1.0

### Based On
Requirements as provided (verbatim, no changes). Source: implementation_spec.md v1.0, dated 2026-04-12.

### Change Summary
First version.

### Decision Log

| ID | Decision | Rationale | Stage Affected |
|----|----------|-----------|----------------|
| D-1 | OI-2 and OI-3 treated as planning assumptions, not blocking items | Per instruction: they are technology choices, not functional gaps; spec provides recommended resolutions | All stages |
| D-2 | R-3 (Conversation State Routing) split across Stages 1, 2, and 3 | Each stage introduces the specific non-Idle states it requires; no stage depends on a routing branch it has not yet introduced | Stages 1, 2, 3 |
| D-3 | NFRs assigned to the earliest stage at which they first become measurable or verifiable | NFRs are cross-cutting; assigning them to the stage where they are first exercised gives the earliest possible feedback signal | All stages |
| D-4 | Stage count set to four | Three stages produced unbalanced load (Stage 2 was too large); five stages produced micro-stages with insufficient functional density; four stages balance scope and coherence | All stages |
| D-5 | MetricActivityStatus treated as a computed view, not a persisted row | FR-8 describes only a derived computation; storing it separately would require trigger logic not described in any requirement; see Planning Assumption 6 | Stage 2 |
