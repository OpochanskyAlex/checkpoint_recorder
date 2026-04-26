---
doc: UC
id: UC14
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [discovery]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC14: Request help

Traces to [[srs#FR19|FR19 /help command]]. User story: [[us-7-discover-commands|US7 Discover available commands]].

Activity tags: `@discovery`

## Actors

- **Primary:** End User (registered or unregistered)

## Preconditions

- None — available to any user including unregistered.

## Postconditions

- Formatted command reference delivered.
- No state changes, no entity created or modified, no event emitted.

## Main flow

1. Any user sends `/help`.
2. System constructs and dispatches a formatted static message listing all available bot commands with brief descriptions.
3. No registration check; no ConversationState consultation; no side effects.

## Edge cases

- **Registered user in non-Idle ConversationState sends `/help`** → help response dispatched without interrupting the active conversation state. (Behavior is informational; does not affect state routing.)
- **Help text must stay synchronized** with implemented command set. When FR20, FR21 or future commands are added, help text must be updated (AC7.3).
