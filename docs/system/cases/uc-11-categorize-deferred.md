---
doc: UC
id: UC11
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

# UC11: Categorize deferred entry

Traces to [[srs#FR15|FR15 Late categorization]]. User story: [[us-2-resolve-ambiguous|US2 Resolve an ambiguous entry]].

Activity tags: `@logging`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle.

## Postconditions

### On categorization success
- Entry created with `entry_timestamp` = original message time (not categorization time).
- ParseAttempt.status = Resolved.
- `late_categorization_event` emitted without `raw_input` in payload.

### On discard
- ParseAttempt.status = Expired. `raw_input` purged.

## Main flow (happy path — categorize)

1. User sends `/deferred_list`.
2. ParseAttempt Manager retrieves all ParseAttempts with `status = Deferred` for the user.
3. Formatted list dispatched: `raw_input` text, `created_timestamp`, `parse_attempt_id` for each.
4. User sends `/deferred_categorize pa_id metric_name`.
5. ParseAttempt Manager verifies ParseAttempt belongs to user and `status = Deferred`.
6. Metric Manager verifies target Metric belongs to user and `status = Active`.
7. Entry Processor creates Entry from `raw_input` using target metric; `entry_timestamp` = original `created_timestamp` of ParseAttempt.
8. ParseAttempt.status = Resolved.
9. Alert evaluation triggered (as UC2 step 5).
10. `late_categorization_event` emitted (parse_attempt_id, metric_id, entry_id — no raw_input).
11. Confirmation dispatched.

## Alternative flows

### A1 User discards a ParseAttempt
Step 4 variant: user sends discard command for `pa_id`.
1. ParseAttempt.status = Expired. `raw_input` field purged.
2. `parse_attempt_event` (expired, reason=user_discard) emitted.

## Error paths

### E1 No Deferred ParseAttempts
- System response: informative empty-list message.

### E2 Target metric is Archived
- Detected at: step 6.
- System response: "Cannot categorize to an Archived metric. Reactivate it first (UC6)."

### E3 ParseAttempt already Resolved or Expired
- Detected at: step 5.
- System response: error; cannot re-categorize.

### E4 Entry creation fails
- Detected at: step 7.
- System response: ParseAttempt remains Deferred; user notified to retry.

## Edge cases

- **ParseAttempt's candidate metric was deleted after deferral** → ParseAttempt already transitioned to Expired by cascade (FR10); will not appear in list.
