---
doc: US
id: US5
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [alerting]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US5: Set and manage threshold alerts

Traces to [[brd#R5|R5]], [[brd#G2|G2]].

Activity tags: `@alerting`

## Story

As a **user monitoring a metric for a threshold condition**, I want to configure an alert that notifies me in Telegram when the condition is met so that I don't have to manually watch the metric.

## Acceptance Criteria

- AC5.1 Given the user configures an alert with a metric, condition (above/below), and numeric threshold, an Active alert is created and will evaluate on the next entry for that metric.
- AC5.2 Given an entry is stored that meets an Active alert's condition, the user receives a Telegram notification within 60 seconds; the alert transitions to Triggered and does not fire again automatically.
- AC5.3 Given the user re-arms a Triggered alert, it returns to Active and will evaluate future entries.
- AC5.4 Given alert evaluation fails after an entry is stored, the entry is not rolled back or affected.

## Notes

One-shot behavior (D-012): alerts fire once and require explicit re-arming. Users are informed of this at onboarding. Alert evaluation is skipped for archived metrics. Alerts on compound-metric entries target a specific named dimension.

## Open Questions

(None.)
