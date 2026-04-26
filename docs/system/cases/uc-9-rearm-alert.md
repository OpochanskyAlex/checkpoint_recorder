---
doc: UC
id: UC9
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [alerting]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC9: Re-arm triggered alert

Traces to [[srs#FR13|FR13 Alert re-arming]]. User story: [[us-5-set-alerts|US5 Set and manage threshold alerts]].

Activity tags: `@alerting`

## Actors

- **Primary:** End User

## Preconditions

- Alert.status = Triggered.

## Postconditions

### On success
- Alert.status = Active.
- `last_triggered_timestamp` preserved (not cleared).
- Alert will evaluate against future entries.

## Main flow (happy path)

1. User sends `/alert_rearm alert_id`.
2. Alert Engine verifies Alert belongs to user.
3. Alert Engine verifies `Alert.status = Triggered`.
4. Alert Engine sets `Alert.status = Active`. `last_triggered_timestamp` unchanged.
5. Confirmation dispatched.

## Error paths

### E1 Alert is not in Triggered status
- Detected at: step 3.
- System response: "This alert is already Active" (if Active) or "Alert cannot be re-armed" (if Archived or Deleted).

## Edge cases

- **Re-arming at any time after firing** — no deadline; user may return weeks later and re-arm.
- **Re-arming an alert whose metric is Archived** — allowed; alert moves to Active but evaluation remains suspended until metric is reactivated (UC6).
