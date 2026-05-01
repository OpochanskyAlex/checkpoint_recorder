---
doc: UC
id: UC8
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
  - {doc: feat-smart-metric-picker, version: 0.1}
updated: 2026-04-28
tags: [project-docs, use-case]
---

# UC8: Configure threshold alert

Traces to [[srs#FR11|FR11 Alert configuration]], [[srs#FR12|FR12 Alert evaluation]]. User story: [[us-5-set-alerts|US5 Set and manage threshold alerts]].

Activity tags: `@alerting`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.
- Metric.status = Active (not Archived or Deleted).

## Postconditions

### On success
- Alert record created with `status = Active`.
- Alert will evaluate on next Entry stored for this metric.

## Main flow (happy path)

1. User sends `/alert_set metric_name condition threshold [dimension]`.
2. Alert Engine verifies Metric exists for user and `status = Active`.
3. For compound metrics: verifies `target_dimension` is a valid dimension name present in at least one stored Entry for this metric.
4. For single-value metrics: `target_dimension = null`.
5. Validates `condition ∈ {above, below}`.
6. Validates `threshold_value` is finite numeric (not NaN, not ±Infinity).
7. Creates Alert record: `status = Active`, `last_triggered_timestamp = null`.
8. Confirmation dispatched with alert summary.

## Error paths

### E1 Metric is Archived
- Detected at: step 2.
- System response: "Alerts cannot be set on an archived metric. Reactivate it first."

### E2 target_dimension not in Metric's known dimensions
- Detected at: step 3.
- System response: "Dimension '{name}' has not been logged for this metric. Log an entry with this dimension first."

### E3 Non-finite threshold value
- Detected at: step 6.
- System response: validation error specifying the constraint.

## Edge cases

- **Multiple alerts on same metric/dimension** → allowed; no uniqueness constraint on alerts per metric/dimension pair.
- **Threshold = 0** → allowed.
- **Alert set on metric that later becomes Archived** → existing alert preserved in Active status; evaluation suspended for new entries until reactivation (UC6).
- **Bare or fuzzy-name command (2026-04-28 smart-metric-picker delta)** — when `/alert_set` is issued without an exact metric name match, [[uc-16-select-metric-picker|UC16]] executes first and resolves the metric name via the inline picker before this UC's main flow begins at step 2 (FR22, FR23). If zero fuzzy matches: FR28 delivers "no matching metrics found" and `/alert_set` is not executed.
