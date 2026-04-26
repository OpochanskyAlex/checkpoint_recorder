---
doc: UC
id: UC3
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [logging]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC3: Resolve ambiguous entry

Traces to [[srs#FR5|FR5 Ambiguous entry]], [[srs#FR15|FR15 Late categorization]], [[srs#FR3|FR3 Conversation state routing]]. User story: [[us-2-resolve-ambiguous|US2 Resolve an ambiguous entry]].

Activity tags: `@logging`

## Actors

- **Primary:** End User
- **Secondary:** NLP Parsing Engine, ParseAttempt Manager, Observability Collector

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle (no existing Pending ParseAttempt).
- NLP Parsing Engine returns outcome=ambiguous or confidence < threshold.

## Postconditions

### On success (user resolves)
- ParseAttempt.status = Resolved.
- Entry record created with `entry_timestamp` = original message time.
- ConversationState = Idle.
- `parse_outcome_event` (ambiguous) and `parse_attempt_event` (resolved) emitted.

### On deferral
- ParseAttempt.status = Deferred.
- `raw_input` retained; entry not stored.
- ConversationState = Idle.
- Available for late categorization via UC11.

### On failure (prompt dispatch failure)
- ParseAttempt record deleted (compensating delete — AD-9).
- ConversationState remains Idle.
- User receives error message.

## Main flow (happy path — user resolves)

1. End User sends ambiguous free-text message (e.g., `82`).
2. NLP Parsing Engine returns outcome=ambiguous with a ranked `candidate_metrics` list.
3. ParseAttempt Manager confirms user has no existing Pending ParseAttempt.
4. ParseAttempt Manager creates ParseAttempt record: `raw_input`, `candidate_metrics`, `status = Pending`, `expiry_timestamp = now() + 24h`.
5. ParseAttempt Manager dispatches disambiguation prompt listing candidate metrics (formatted distinctly from alert notifications).
6. ConversationState → PendingDisambiguation.
7. ParseAttempt Manager emits `parse_outcome_event` (outcome=ambiguous) — fire-and-forget.
8. User responds with metric selection (Dispatcher routes via FR3).
9. ParseAttempt Manager resolves selection → ParseAttempt.status = Resolved.
10. Entry Processor creates Entry using selected metric and `raw_input`; `entry_timestamp` = original message time (not resolution time).
11. Alert evaluation triggered (as UC2 step 5).
12. ConversationState → Idle. Confirmation dispatched.

## Alternative flows

### A1 User explicitly defers
Branches from step 8.
1. User sends defer command instead of metric selection.
2. ParseAttempt.status = Deferred. ConversationState → Idle.
3. `parse_attempt_event` (deferred) emitted. Raw_input retained.

### A2 Expiry timeout (SU-001 = 24h)
Triggered by Scheduled Process.
1. ParseAttempt.status = Pending → Deferred. ConversationState → Idle.
2. `parse_attempt_event` (deferred, reason=expiry) emitted.

### A3 Account enters PendingDeletion while ParseAttempt is Pending
1. Account Manager notifies ParseAttempt Manager before PendingDeletion transition.
2. ParseAttempt.status = Pending → Deferred. (No-op if no active ParseAttempt.)
3. Subsequent messages routed to restoration flow (FR2).

## Error paths

### E1 Disambiguation prompt dispatch fails after ParseAttempt creation (atomicity compensation)
- Detected at: step 5.
- System response: ParseAttempt Manager deletes ParseAttempt record (compensating delete). If compensating delete also fails: emits `dangling_parse_attempt_alert` event; operator must manually clear.
- Final state: no ParseAttempt record (or dangling detected via Observability within 30s window). User receives error; retries by sending message again.

### E2 User in non-Idle state when ambiguous message arrives
- Detected at: step 3.
- System response: Dispatcher routes to active state handler (blocked). User informed to resolve existing pending prompt first. No new ParseAttempt created.

### E3 New ambiguous message arrives while ParseAttempt is Pending
- Same as E2: blocked. User must resolve or defer existing ParseAttempt.

## Edge cases

- **Alert fires while disambiguation is Pending** → Alert notification dispatched immediately (not suppressed). Formatted as a distinct block ("Alert fired:") with no selectable options, to prevent confusion with disambiguation selection prompt.
- **Deferred ParseAttempt's target metric is later deleted** → ParseAttempt transitions to Expired as part of metric cascade delete (FR10). Will not appear in /deferred_list.

## Non-functional considerations

- NFR2: Disambiguation prompt dispatch ≤5s p95 from message receipt.
- NFR9: `parse_outcome_event` emitted for every ambiguous parse.
- NFR16, BR3: Zero dangling Pending ParseAttempts after `parse_attempt_dangling_detection_window` (30s).
