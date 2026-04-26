---
doc: UC
id: UC15
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
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC15: List and delete alerts

Traces to [[srs#FR20|FR20 Alert listing]], [[srs#FR21|FR21 Alert deletion]]. User stories: [[us-5-set-alerts|US5 Set and manage threshold alerts]], [[us-3-manage-metrics|US3 Manage metric catalog]].

Activity tags: `@management`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.

## Postconditions

### Alert listing
- Formatted list of all non-Deleted alerts returned with metric name, target dimension, condition, threshold, and current status.

### Alert deletion success
- Alert.status = Deleted (terminal).
- Deletion is immediate and irreversible; no grace period.

## Main flow — List

1. User sends `/alert_list`.
2. Alert Engine retrieves all Alert records where `status ≠ Deleted` for the user.
3. Formatted list dispatched: metric name, target dimension (if compound), condition, threshold, status (Active/Triggered).
4. If no alerts: informative empty-list message.

## Main flow — Delete

1. User sends `/alert_delete alert_id`.
2. Alert Engine verifies Alert belongs to user.
3. Alert Engine dispatches single-step confirmation prompt.
4. User confirms.
5. Alert Engine sets `Alert.status = Deleted` (permanent).
6. Confirmation dispatched.

## Alternative flows

### A1 User cancels deletion
Branches from step 4.
1. No change. Alert preserved in prior status.

## Error paths

### E1 Alert not found for this user
- System response: "No alert found with that ID."

## Edge cases

- **Deleting a Triggered alert** — allowed; user is not blocked from deleting a Triggered alert.
- **No grace period** — alert deletion is immediate and irreversible. Single-step confirmation is the sole protection (contrast with UC12 account deletion which has a 72-hour grace period). This is an explicit design decision per system_analysis.md Flow 9.

## Open Questions

- Q3 (from SRS): Confirm exact command names (`/alert_list`, `/alert_delete`) and response format with stakeholder.
