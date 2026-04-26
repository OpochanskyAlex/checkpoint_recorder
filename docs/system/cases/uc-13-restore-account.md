---
doc: UC
id: UC13
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

# UC13: Restore account

Traces to [[srs#FR17|FR17 Account restoration]], [[srs#FR2|FR2 Account status gate]]. User story: [[us-6-manage-account|US6 Manage account]].

Activity tags: `@account`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = PendingDeletion.
- `deletion_scheduled_timestamp > now()` (within 72-hour window).

## Postconditions

### On confirmed restoration
- `account_status = Active`.
- `deletion_scheduled_timestamp` cleared.
- All data preserved.
- ConversationState → Idle.
- `account_lifecycle_event` (account_restored) emitted.

### On non-confirmation
- Account remains PendingDeletion. User informed.

## Main flow (happy path)

1. User sends any message while `account_status = PendingDeletion`.
2. FR2 account status gate routes all messages to Account Manager restoration handler.
3. Account Manager dispatches: "Your account is pending deletion in N hours. Reply to restore it."
4. ConversationState → PendingRestorationConfirmation.
5. User confirms restoration.
6. Account Manager sets `account_status = Active`; clears `deletion_scheduled_timestamp`.
7. ConversationState → Idle.
8. Confirmation dispatched: "Account fully restored. All data preserved."
9. `account_lifecycle_event` (account_restored) emitted.

## Alternative flows

### A1 User does not confirm (sends other message or ignores)
Branches from step 5.
1. Account Manager informs user account remains pending deletion; ConversationState → Idle.
2. Account remains PendingDeletion; scheduled purge proceeds.

## Error paths

### E1 DB write failure during restoration
- Detected at: step 6.
- System response: error returned to user; account remains PendingDeletion (safe resting state). User retries.

### E2 Grace period expires before user restores
- Precondition fails: Scheduled Process has already purged the account. Any subsequent message treated as first contact → UC1 (new registration).

## Edge cases

- **User confirms restoration multiple times** → idempotent — second confirmation returns "already Active" with no side effects.
