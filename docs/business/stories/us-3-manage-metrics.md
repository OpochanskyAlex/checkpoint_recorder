---
doc: US
id: US3
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [management]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US3: Manage metric catalog

Traces to [[brd#R6|R6]], [[brd#G1|G1]], [[brd#G2|G2]].

Activity tags: `@management`

## Story

As a **user with multiple tracked metrics**, I want to view my full metric list, pause tracking for a metric without losing its history, and permanently delete a metric I no longer need so that my tracking catalog stays meaningful and uncluttered.

## Acceptance Criteria

- AC3.1 Given the user requests their metric list, all active and archived metrics are shown with name, periodicity, unit (if set), and current activity status (active if ≥4 of last 5 periods filled).
- AC3.2 Given the user archives a metric, new threshold alerts no longer fire for it; existing entries and alert configuration are preserved.
- AC3.3 Given the user reactivates an archived metric, threshold alert evaluation resumes for future entries.
- AC3.4 Given the user issues a delete command for a metric, they receive an explicit confirmation prompt listing what will be deleted (entry count, alert count); deletion is irreversible and executes only after confirmation.
- AC3.5 Given the user confirms metric deletion, all associated entries, alerts, and deferred entries are permanently removed atomically; no partial state is left behind.

## Notes

Archival is the non-destructive pause option. Deletion is permanent with no grace period — the confirmation prompt is the sole protection. Alert evaluation is suspended for archived metrics as a structural consequence of the archival state, not a conditional check.

## Open Questions

(None.)
