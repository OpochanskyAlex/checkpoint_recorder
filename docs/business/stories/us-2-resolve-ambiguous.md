---
doc: US
id: US2
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

# US2: Resolve an ambiguous entry

Traces to [[brd#R3|R3]], [[brd#G1|G1]].

Activity tags: `@logging`

## Story

As a **user whose message could match multiple metrics**, I want the bot to present me with the likely candidates rather than guessing or discarding my input so that my data is never silently lost.

## Acceptance Criteria

- AC2.1 Given the system cannot parse a message with sufficient confidence, it presents a ranked list of candidate metrics within 5 seconds and does not store any entry yet.
- AC2.2 Given the user selects a metric from the list, the entry is stored against that metric using the original message timestamp and a confirmation is returned.
- AC2.3 Given the user defers resolution, the entry is preserved in a Deferred state with its original text retained; it is available for later categorization via `/deferred_list`.
- AC2.4 Given a user has an active unresolved disambiguation in progress, no new disambiguation session is started until the existing one is resolved or deferred.

## Notes

The system must never silently discard ambiguous input — RISK2 mitigation is that the user always has a path to store or explicitly abandon the entry. Deferred entries are retained until the user acts on them or the cleanup window expires.

## Open Questions

(None.)
