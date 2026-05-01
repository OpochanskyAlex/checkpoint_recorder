---
doc: UC
id: UC7
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
updated: 2026-04-28
tags: [project-docs, use-case]
---

# UC7: Delete metric

Traces to [[srs#FR10|FR10 Metric deletion with cascade]], [[srs#FR3|FR3 Conversation state routing]]. User story: [[us-3-manage-metrics|US3 Manage metric catalog]].

Activity tags: `@management`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle.
- Metric.status = Active or Archived (not already Deleted).

## Postconditions

### On confirmed deletion
- Metric.status = Deleted (terminal).
- All associated Entries (including `raw_input` fields) permanently deleted.
- All associated Alerts permanently deleted (regardless of their status).
- All associated Pending/Deferred ParseAttempts transitioned to Expired; `raw_input` purged.
- Cascade is atomic — either all succeed or none (BR8).
- `cascade_deletion_event` emitted.

### On cancellation
- No changes made. ConversationState → Idle.

### On cascade failure
- Atomic rollback — no partial deletion. Metric remains in prior state.

## Main flow (happy path)

1. User sends `/metric_delete metric_name`.
2. Metric Manager identifies Metric by name for the user.
3. Metric Manager dispatches confirmation prompt specifying: metric name, entry count, alert count, pending ParseAttempt count. States explicitly that action is permanent and irreversible.
4. ConversationState → PendingMetricDeletionConfirmation.
5. User confirms (Dispatcher routes via FR3).
6. Metric Manager executes atomic cascade deletion in a single DB transaction: sets Metric.status = Deleted; deletes all Entries (including raw_input); deletes all Alerts; transitions ParseAttempts to Expired (purging raw_input).
7. ConversationState → Idle.
8. Confirmation dispatched: "Metric '{name}' and all {n} entries permanently deleted."
9. `cascade_deletion_event` emitted (with per-entity counts).

## Alternative flows

### A1 User cancels or sends non-confirmation message
Branches from step 5.
1. Metric Manager cancels deletion. ConversationState → Idle.
2. Informative message: "Deletion cancelled. Metric preserved."

## Error paths

### E1 Metric not found
- Detected at: step 2.
- System response: "No metric found with that name." ConversationState remains Idle.

### E2 Cascade deletion partially fails
- Detected at: step 6.
- System response: atomic rollback — no partial deletion visible. User notified: "Deletion could not be completed. Please try again." `error_event` emitted.

## Edge cases

- **Metric with Active alerts deleted** → Active alerts deleted without additional warning beyond the confirmation in step 3.
- **Metric with Pending ParseAttempt deleted** → ParseAttempt transitions to Expired; raw_input purged as part of cascade.
- **No grace period** — unlike account deletion, metric deletion has no grace period. Confirmation prompt is the sole protection.
- **Bare or fuzzy-name command (2026-04-28 smart-metric-picker delta)** — when `/metric_delete` is issued without an exact metric name match, [[uc-16-select-metric-picker|UC16]] executes first and resolves the metric name via the inline picker; after selection UC16 transitions ConversationState to PendingMetricDeletionConfirmation and this UC's main flow begins at step 3 (FR22, FR23, FR29).

## Non-functional considerations

- BR8: Cascade atomicity — single DB transaction; partial deletion is a data integrity failure.
- NFR15: All `raw_input` fields purged as part of cascade.
