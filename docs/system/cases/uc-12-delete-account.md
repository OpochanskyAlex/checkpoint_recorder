---
doc: UC
id: UC12
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [account]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC12: Delete account

Traces to [[srs#FR16|FR16 Account deletion with grace period]], [[srs#FR18|FR18 Scheduled data purge]], [[srs#FR2|FR2 Account status gate]]. User story: [[us-6-manage-account|US6 Manage account]].

Activity tags: `@account`

## Actors

- **Primary:** End User
- **Secondary:** Scheduled Process (purge after grace period)

## Preconditions

- InternalUser.account_status = Active.

## Postconditions

### On confirmation
- `account_status = PendingDeletion`.
- `deletion_scheduled_timestamp = now() + 72h`.
- Active Pending ParseAttempts → Deferred.
- ConversationState → Idle.
- User informed of 3-day window and restoration option.

### After 72-hour grace period (Scheduled Process)
- All user data permanently and irreversibly purged (atomic per user): Metrics, Entries (including raw_input), Alerts, ParseAttempts (including raw_input), ConversationState.
- `account_status = Deleted`.
- `account_lifecycle_event` (account_purged) emitted.

### On cancellation
- No state change.

## Main flow (happy path)

1. User sends `/account_delete`.
2. Account Manager dispatches confirmation prompt.
3. User confirms.
4. Account Manager notifies ParseAttempt Manager: transition any Pending ParseAttempt to Deferred (no-op if none).
5. Account Manager sets `account_status = PendingDeletion`; `deletion_scheduled_timestamp = now() + 72h`.
6. ConversationState → Idle (if not already).
7. Account Manager dispatches 3-day notice: data will be permanently deleted; can restore by contacting the bot within 72 hours.
8. `account_lifecycle_event` (pending_deletion_scheduled) emitted.
9. [72h later] Scheduled Process identifies PendingDeletion accounts past `deletion_scheduled_timestamp`.
10. Scheduled Process executes atomic cascade purge per user. `account_status = Deleted`.
11. `account_lifecycle_event` (account_purged) + `cascade_deletion_event` emitted.

## Alternative flows

### A1 User cancels confirmation
Branches from step 3.
1. No state change. Account remains Active.

## Error paths

### E1 ParseAttempt coordination fails (step 4)
- Account Manager logs warning and proceeds. Any remaining Pending ParseAttempt is operator-detectable as a dangling record via Observability.

### E2 Scheduled Process fails at purge step (step 10)
- System response: atomic rollback per user; user data intact. `error_event` emitted. Next Scheduled Process invocation retries.

## Edge cases

- **User sends any message while PendingDeletion** → routed to UC13 (restoration flow) via FR2.
- **No grace period for restoration after Deleted** → once purge completes, no recovery path exists.

## Non-functional considerations

- BR10: Purge no earlier than 72h after `deletion_scheduled_timestamp`.
- NFR12, NFR13: Retention enforcement and grace period.
- BR8: Cascade purge atomic per user.
