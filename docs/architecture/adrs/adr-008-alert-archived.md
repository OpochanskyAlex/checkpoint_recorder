---
doc: ADR
id: ADR-008
title: Alert evaluation suspended for Archived metrics
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-003]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-008: Alert evaluation suspended for Archived metrics

# Context

SU-004 asked: should alert evaluation continue when a metric is Archived? FR9 states entries CAN still be stored for Archived metrics (archival does not block data entry). FR12 requires alert evaluation after every Entry storage. Without an explicit decision, the system would evaluate alerts on Archived metrics — which is semantically unexpected: the user paused the metric, not just the data entry.

**Important implementation note:** Because entries CAN be stored for Archived metrics (FR9), alert suspension is NOT structurally guaranteed. It must be an explicit conditional check in the Alert Engine (`if Metric.status == Archived: skip evaluation`). This differs from the PendingDeletion case, where no entries are stored (structural guarantee via routing).

# Decision

Alert evaluation is suspended when Metric.status = Archived. Enforced via an explicit conditional check in the Alert Engine. All Active alert records on the metric are preserved in their current status. Alert evaluation resumes when the metric is reactivated.

# Alternatives Considered

## A1 Continue evaluating alerts on Archived metrics
- Pros: no code change needed; consistent behavior
- Cons: semantically unexpected — user archived (paused) the metric and would receive alert notifications for a metric they consider dormant; poor UX
- Why not: violates user mental model of "archived = paused"

## A2 Auto-archive or auto-delete all alerts when metric is Archived
- Pros: no accidental alert firing
- Cons: destroys alert configuration; user must reconfigure all alerts after reactivation; destructive without user intent
- Why not: irreversible loss of alert configuration without explicit user action

## A3 Suspend evaluation via explicit conditional check (chosen)
- Pros: alert configuration preserved; evaluation resumes on reactivation; semantically correct; minimal code change (one guard in Alert Engine)
- Cons: requires conditional check (not structural); if the check is missing from a future code path, alerts evaluate on Archived metrics silently
- Why yes: semantically correct; preserves user configuration; explicit check is auditable

# Consequences

## Positive
- User alert configuration is preserved through archive/reactivate cycles
- Semantically matches the user's intent when archiving a metric

## Negative
- Not structurally guaranteed — relies on explicit check in Alert Engine; must be present in all Entry evaluation code paths

## Follow-ups
- Alert Engine guard must be present in the evaluation method: `if metric.status == MetricStatus.Archived: log and return`
- FR9 confirmation to users: archival confirmation message must state "alert notifications paused while metric is archived"

# NFRs affected

- NFR10 (Alert eval coverage): `alert_evaluation_event` is still emitted for skipped evaluations with `outcome = skipped_archived` to maintain 100% coverage
