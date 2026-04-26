---
doc: US
id: US7
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [discovery]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US7: Discover available commands

Traces to [[brd#R10|R10]], [[brd#G1|G1]].

Activity tags: `@discovery`

## Story

As a **user unfamiliar with the bot's commands**, I want to type `/help` and receive a complete list of all available commands with brief descriptions so that I can self-serve without reading external documentation.

## Acceptance Criteria

- AC7.1 Given any user (registered or not) sends `/help`, a formatted list of all available commands with descriptions is returned.
- AC7.2 Given `/help` is sent, no state changes occur, no data is modified, and no events are emitted.
- AC7.3 Given new commands are added to the bot, the `/help` response is updated to include them.

## Notes

The help response is static and does not personalize based on the user's registration status or current metrics. Available without registration to reduce onboarding friction (D-011).

## Open Questions

(None.)
