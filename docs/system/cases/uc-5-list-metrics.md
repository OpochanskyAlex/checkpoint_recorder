---
doc: UC
id: UC5
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

# UC5: List metrics

Traces to [[srs#FR8|FR8 Metric listing]]. User story: [[us-3-manage-metrics|US3 Manage metric catalog]].

Activity tags: `@management`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.

## Postconditions

### On success
- Formatted list of all Active and Archived metrics returned with name, periodicity, unit, status, and MetricActivityStatus.

## Main flow (happy path)

1. User sends `/metric_list`.
2. Metric Manager retrieves all Metric records where `status ∈ {Active, Archived}` for the user.
3. For each Metric, MetricActivityStatus is lazily computed on read: count distinct periods with ≥1 Entry in last 5 periods of the metric's own periodicity. `periods_filled` ∈ [0, 5]; `status = Active` if `periods_filled ≥ 4`.
4. Formatted list dispatched: metric name, periodicity, unit (if set), status (Active/Archived), MetricActivityStatus (Active/Inactive, periods_filled/5).

## Error paths

### E1 No metrics exist
- System response: informative empty-list message with guidance to create one (via UC4 or free-text entry).

## Edge cases

- **Metric with zero entries** → `periods_filled = 0`, MetricActivityStatus = Inactive.
- **MetricActivityStatus stale** → recomputed if `computation_timestamp < now() - 1 periodicity unit` (SU-005, Q2).
