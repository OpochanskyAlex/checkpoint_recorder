---
doc: US
id: US1
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [logging]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US1: Log a metric in free text

Traces to [[brd#R1|R1]], [[brd#R2|R2]], [[brd#G1|G1]].

Activity tags: `@logging`

## Story

As a **Telegram user tracking personal metrics**, I want to send a plain-text message to the bot with a metric name and value so that my data is stored instantly without opening a separate app or navigating any UI.

## Acceptance Criteria

- AC1.1 Given a registered user sends a message containing a recognizable metric name and numeric value (e.g., `mood 7`), the system stores the entry and returns a confirmation within 5 seconds.
- AC1.2 Given the metric name has zero fuzzy matches (fully unrecognized), the system presents a "Create [typed_name]" inline button; on user confirmation, the system prompts for periodicity (`daily` or `weekly`) and creates the metric record and stores the entry atomically on periodicity confirmation; neither is stored before periodicity is selected.
- AC1.3 Given a compound message (e.g., `bench press 80kg 5reps`), the system stores multiple dimension values under a single entry and confirms each dimension.
- AC1.4 Given any entry storage failure, the system does NOT send a confirmation and asks the user to re-submit; no silent loss.

## Notes

New metrics are created only when the user explicitly confirms via the "Create [typed_name]" inline button (R17) — silent auto-creation is not used. Periodicity selection is the required setup step after confirmation; neither metric nor entry is stored until periodicity is selected. Entry records are immutable after creation. Full picker interaction is specified in [[us-8-metric-picker|US8]].

## Open Questions

(None.)
