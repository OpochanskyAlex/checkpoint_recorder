---
doc: US
id: US8
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [logging, management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
updated: 2026-05-01
tags: [project-docs, user-story]
---

# US8: Select a metric via inline picker

Traces to [[brd#R12|R12]], [[brd#R13|R13]], [[brd#R14|R14]], [[brd#R15|R15]], [[brd#R16|R16]], [[brd#R17|R17]], [[brd#R18|R18]], [[brd#R19|R19]], [[brd#G1|G1]], [[brd#G2|G2]].

Activity tags: `@logging`, `@management`

## Story

As a **user issuing a metric-name-required command**, I want the bot to show me my metrics as tappable inline buttons when I do not type — or cannot recall — the exact metric name, so that I can complete the command without memorizing exact wording or abandoning the action.

## Acceptance Criteria

**Bare command (no metric name provided):**
- AC8.1 Given a registered user sends `/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`, or triggers the logging/entry flow without a metric name, the system responds within 5 seconds with an inline keyboard listing all of the user's metrics as buttons, ordered by most-recently-recorded entry descending; metrics with no entries appear last, ordered alphabetically.
- AC8.2 Given the user has more than 4 metrics and issues a bare command, the system displays the 4 most-recently-recorded metrics plus a "Show all fits" button; pressing "Show all fits" replaces the message with an inline keyboard listing all of the user's metrics.
- AC8.3 Given the user has no metrics registered, the system responds with a message explaining that no metrics exist yet and how to create one (via free-text entry); no inline keyboard is shown.

**Fuzzy name match (partial or misspelled metric name provided):**
- AC8.4 Given a user supplies a metric name argument that does not exactly match any existing metric and produces one or more fuzzy matches above the system similarity threshold, the system responds within 5 seconds with an inline keyboard of matching metrics ordered by most-recently-recorded entry descending; the original typed name is shown in the message for reference.
- AC8.5 Given the fuzzy search produces more than 4 matches, the top 4 are shown plus a "Show all fits" button following the same behavior as AC8.2.
- AC8.6 Given the fuzzy search produces zero matches in the **logging/entry flow**, the system displays an explicit "Create [typed_name]" inline button; pressing it initiates the periodicity selection flow (R2) with the typed name pre-filled; R2 auto-create does not fire silently.
- AC8.6b Given the fuzzy search produces zero matches for a **management command** (`/chart`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`, `/alert_set`), the system responds with a "no matching metrics found" message; no picker or Create button is shown.

**Metric selection:**
- AC8.7 Given the user presses a metric button in the inline keyboard, the bot acknowledges the selection and proceeds with the chosen command using the selected metric name; the inline keyboard is dismissed or replaced.
- AC8.8 Given the user presses a metric button, the bot displays the last 3 recorded values for that metric (or fewer if fewer exist, including a "no entries yet" note when count is zero) as context before proceeding with the command.
- AC8.8b Given the user presses a metric button in the **logging/entry flow specifically**, after showing last 3 values the bot additionally prompts the user to enter a new value.
- AC8.9 Given the user does not press any button and the picker interaction times out (timeout duration defined by SA), the interaction is cancelled and the user is informed; no entry is stored and no command is executed.

**Recency ordering:**
- AC8.10 Given two metrics where metric A has its most recent entry more recent than metric B, metric A appears before metric B in the picker list.
- AC8.11 Given two metrics both have no entries, they appear after all metrics-with-entries and are ordered alphabetically by metric name (case-insensitive).
- AC8.12 Given the user presses the Cancel button on any picker keyboard (bare command, fuzzy match, overflow, or zero-match Create-button display), the picker is dismissed, the conversation state returns to Idle, and the reply is identical to the /cancel command response; no metric is selected and no command is executed.

## Notes

- The picker is a proactive UX shortcut distinct from R3 (ParseAttempt). R3 fires when NLP confidence is insufficient on a free-text message; the picker fires when a metric-name-required command is invoked with a missing or fuzzy argument. The triggers are different even though the presentation (inline buttons) is similar.
- Fuzzy matching uses rapidfuzz (already in the technology stack). The exact similarity threshold and scoring function are deferred to SA (Q-FEAT-3).
- R2 metric creation does not fire silently. Per R17, when fuzzy matching yields zero results in the logging/entry flow the system presents an explicit "Create [typed_name]" inline button; pressing it initiates periodicity selection and atomic metric+entry creation (R2). For management commands with zero matches, R18 applies — a "no matching metrics found" message is shown with no Create option.
- Exact metric name matches bypass the picker entirely and flow directly into the normal command path (R1, R6).

## Open Questions

- Q-FEAT-1 (SA): Shared vs. separate ConversationState for picker and ParseAttempt. See feature spec.
- Q-FEAT-2 (SA): Whether "asking for a new value" after picker selection in the logging flow is a new FSM state or re-uses existing entry state.
- ~~Q-FEAT-5~~ **Resolved 2026-04-28:** Last-3-values context applies to ALL metric-name-required commands. AC8.8 updated.
- ~~Q-FEAT-6~~ **Resolved 2026-04-28:** Explicit "Create [typed_name]" button on zero-match in logging flow. AC8.6 updated. R17 added to BRD.
