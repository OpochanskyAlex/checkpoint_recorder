---
doc: UC
id: UC6
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

# UC6: Archive or reactivate metric

Traces to [[srs#FR9|FR9 Metric archival and reactivation]]. User story: [[us-3-manage-metrics|US3 Manage metric catalog]].

Activity tags: `@management`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.
- For archival: Metric.status = Active.
- For reactivation: Metric.status = Archived.

## Postconditions

### Archival success
- Metric.status = Archived.
- Alert evaluation suspended for future entries on this metric (SD-004 equivalent / SU-004).
- Existing alerts and entries preserved.

### Reactivation success
- Metric.status = Active.
- Alert evaluation resumes for Active alerts on this metric.

## Main flow — Archival

1. User sends `/metric_archive metric_name`.
2. Metric Manager verifies Metric belongs to the user and `status = Active`.
3. Metric Manager sets `status = Archived`.
4. Confirmation dispatched: "Metric archived. Alerts paused. History and alerts preserved."

## Main flow — Reactivation

1. User sends `/metric_reactivate metric_name`.
2. Metric Manager verifies Metric belongs to the user and `status = Archived`.
3. Metric Manager sets `status = Active`.
4. Confirmation dispatched: "Metric reactivated. Alert evaluation resumed."

## Error paths

### E1 Metric not found or already in target state
- System response: informative message stating current state; no change made.

## Edge cases

- **Entries can still be added to Archived metrics** — archival does not block data entry (FR9 AC3); only alert evaluation is suspended.
- **Alert evaluation skip for Archived metrics** — enforced via explicit conditional check in Alert Engine, not structurally guaranteed, because entries CAN be stored (implementation clarification from implementation_spec.md §13).
- **Bare or fuzzy-name command (2026-04-28 smart-metric-picker delta)** — when `/metric_archive` or `/metric_reactivate` is issued without an exact metric name match, [[uc-16-select-metric-picker|UC16]] executes first and resolves the metric name via the inline picker before this UC's main flow begins (FR22, FR23). The main flow above assumes metric name is already resolved on entry.
