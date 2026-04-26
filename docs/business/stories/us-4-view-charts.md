---
doc: US
id: US4
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [analytics]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US4: View trend charts

Traces to [[brd#R4|R4]], [[brd#G2|G2]].

Activity tags: `@analytics`

## Story

As a **user who wants to understand patterns in my tracked data**, I want to request a time-series chart for any of my metrics and receive it as an image in Telegram so that I can visually assess trends without leaving the chat.

## Acceptance Criteria

- AC4.1 Given the user requests a chart for a metric with at least 2 stored entries, an acknowledgment message is returned within 5 seconds.
- AC4.2 Given the acknowledgment is sent, a time-series chart image is delivered within 30 seconds of the original request.
- AC4.3 Given the user requests a chart for a metric with no entries, an informative error is returned instead of an empty chart.
- AC4.4 Given chart generation or delivery fails, the user receives an error message; they may retry.

## Notes

Chart delivery uses a two-phase pattern: immediate acknowledgment (≤5s) followed by async image delivery (≤30s). No text-summary fallback is defined at portfolio scope.

## Open Questions

(None.)
