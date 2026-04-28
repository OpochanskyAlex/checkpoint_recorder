---
doc: FEAT
feature: smart-metric-picker
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [logging, management]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-28
tags: [project-docs, feature]
---

# Feature: Smart Metric Picker

## One-liner

When a user issues a metric-name-required command without a name, or with a fuzzy/partial name, the bot presents inline keyboard buttons listing matching metrics ordered by recency — eliminating the need to remember exact wording.

## Motivation

The existing flow (R1, R2, R3) assumes the user either types a recognizable metric name or fails NLP parsing. Neither path helps the user who simply cannot recall the exact name they used three weeks ago, or who wants to browse their own metric catalog as part of the command flow. This creates friction at the retrieval step — the opposite of the low-friction promise (G1). The smart-metric-picker removes that retrieval barrier by surfacing the metric catalog inline, ordered by the most recently recorded entry so that the most likely candidate appears first.

R3 (ParseAttempt) handles a different trigger: NLP confidence is insufficient when *something* was typed. The picker handles *both* the zero-input case (bare command) and the partial-match case (fuzzy string typed). While they share the inline-button selection mechanism, they are triggered by different conditions and serve different intents. This spec defines the picker as an independent interaction path that may share UI components with R3's candidate list.

## New Goals

No new top-level goals. This feature advances G1 (reduce tracking abandonment by reducing retrieval friction) and supports G2 (self-insight via easier access to charting and alerting commands by metric name).

## Affected Stakeholders

- SH1 Health tracker — benefits most; metrics named informally (e.g., `mood`, `sleep`, `steps`) are easy to forget exact casing or wording
- SH2 Expense/resource tracker — benefits from recency ordering when switching between multiple tracked resources
- SH3 Athlete — benefits during management commands (`/metric_archive`, `/chart`) when navigating a large metric catalog
- SH4 Bot Operator — no operational impact; picker uses in-memory fuzzy matching on existing per-user catalog; no new external dependency

## New Business Requirements

- R12 [must] @logging @management When a user issues any metric-name-required command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`, or the logging/entry flow) with no metric name argument, the system presents the user's complete metric catalog as inline keyboard buttons ordered by most-recently-recorded entry (descending) <- G1
- R13 [must] @logging @management When a user supplies a metric name argument that does not exactly match any existing metric but produces at least one fuzzy match (rapidfuzz ratio threshold TBD by SA), the system presents matched metrics as inline keyboard buttons ordered by most-recently-recorded entry <- G1
- R14 [must] @logging @management Inline keyboard buttons presenting metric choices are ordered by the timestamp of the most recent entry for each metric, descending (most recently logged first); metrics with no entries appear last, ordered alphabetically <- G1
- R15 [should] @logging @management When the number of matching metrics exceeds 4, the system displays only the top 4 matches plus an additional "Show all fits" button; pressing "Show all fits" replaces the message with an inline keyboard listing all matching metrics (native Telegram client scrolling applies; see Q-FEAT-4 for SA clarification on pagination) <- G1
- R16 [should] @logging @management After a user selects a metric via the inline picker in any metric-name-required command, the system displays the last 3 recorded values for that metric (or fewer if fewer exist, with a "no entries yet" note when count is zero) as context before proceeding with the command; in the logging/entry flow this is additionally followed by a prompt for a new value <- G1, G2
- R17 [must] @logging When the picker in the logging/entry flow finds zero fuzzy matches for a typed metric name, the system presents an explicit "Create [typed_name]" inline button instead of metric choices; pressing it initiates the periodicity selection and creation flow (R2) with the typed name pre-filled <- G1
- R18 [must] @management When the picker in any metric-name-required management command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`) finds zero fuzzy matches for a supplied metric name, the system responds with a "no matching metrics found" message and does not execute the command; no "Create" button is offered <- G1

## Impact on Existing Requirements

| Requirement | Impact |
|---|---|
| R1 @logging — free-text entry | Extended: when the text contains a metric name with a fuzzy-but-not-exact match, the picker intercepts before NLP disambiguation (R3). Exact matches continue to flow directly into R1. |
| R2 @logging — metric creation | **Modified.** The auto-create-on-unrecognized-name trigger is replaced by the explicit "Create [typed_name]" button flow (R17). The periodicity-prompt-and-atomic-create mechanism is preserved; only the trigger changes from silent/automatic to user-explicit. R2 text updated in BRD. Impact on SA: FR6 must be updated to reflect the new trigger. |
| R3 @logging — ParseAttempt fallback | Related but distinct. R3 trigger: NLP confidence insufficient on a free-text message. R12/R13 trigger: command issued with missing or fuzzy metric name argument. Both may present inline buttons for metric selection, but the conversational state they create and the data they preserve differ. SA must define whether they share a ConversationState node or operate as independent FSM branches (see Q1). |
| R6 @management — metric catalog management | Extended: `/metric_archive`, `/metric_reactivate`, `/metric_delete` now support the metric-picker flow (R12, R13) when called without a metric name. R6 text does not need to change; R12/R13 add a new entry path to R6's actions. |
| R10 @discovery — `/help` command | `/help` must be updated to reflect that metric-name arguments are now optional for the affected commands (bare command triggers picker). This is a documentation change within the existing R10 requirement; R10 wording is sufficient. |

## New User Stories

- [[us-8-metric-picker|US8 Select a metric via inline picker]] <- R12, R13, R14, R15, R16, R17, R18, @logging, @management

## New Activities

None. The picker spans the existing `@logging` and `@management` activities. No new activity slug is required.

## Out of Scope for This Feature

- Fuzzy matching across users (picker is strictly per-user)
- Sorting by metric name alphabetically as primary sort (recency is the primary sort; alphabetical only as tiebreaker for no-entry metrics)
- Inline edit of metric name from within the picker
- Multi-select (selecting multiple metrics in one picker interaction)
- Picker for the `/alert_set` sub-flow after metric selection (threshold configuration dialog is unchanged; only the metric-name resolution step is covered)
- Any changes to NLP parsing pipeline or ParseAttempt logic beyond the trigger condition distinction clarified above

## Glossary Additions

- **Smart Metric Picker** — an inline keyboard interaction that surfaces a user's metric catalog (full or fuzzy-filtered) as pressable buttons, ordered by recency, triggered when a metric-name-required command is issued without an exact metric name match
- **Fuzzy match** — a metric name whose normalized edit-distance similarity score (computed by rapidfuzz) meets or exceeds a threshold defined by SA; at least one match must exist for the picker to show filtered results
- **"Show all fits" overflow button** — an additional inline button that appears when matched metrics exceed 4; pressing it replaces the current message with a full scrollable list of all matches
- **Recency order** — metrics sorted descending by the timestamp of their most recent entry; metrics with no entries are sorted alphabetically after all metrics that have entries

## Open Questions

- Q-FEAT-1 [SA] R3 (ParseAttempt) and the picker both result in inline metric-button presentations, but they are triggered by different conditions. Does the SA define a single shared ConversationState for "awaiting metric selection" that both R3 and R12/R13 transition into, or are they separate FSM branches with separate states? Impact: if separate, the logging flow has two distinct disambiguation paths, each needing its own timeout and deferral behavior.
- Q-FEAT-2 [SA] After metric selection in the picker for the logging/entry flow (R16), showing last 3 values and asking for a new value — is "asking for a new value" a new conversational state (AwaitingNewValue) or does it re-use the existing entry submission state? Impact: determines whether the FSM gains a new node.
- Q-FEAT-3 [SA] What is the exact rapidfuzz similarity threshold that distinguishes a "fuzzy match" from "no match"? Below the threshold, R2 (auto-create) may apply instead. SA must define the numeric threshold and the scoring function (ratio, partial_ratio, token_sort_ratio) to make R13 unambiguous.
- Q-FEAT-4 [SA] The "Show all fits" overflow list is described as scrollable. Telegram inline keyboards are natively scrollable only if the list is long enough to overflow the visible area. No custom scroll implementation is possible within Telegram's API. SA should confirm whether "scrollable" means "a long inline keyboard that the user scrolls within the Telegram UI" (no implementation change) or requires pagination buttons (a new UX pattern). Impact: if pagination is required, R15 needs a [should] → implementation note added at SRS level.
- ~~Q-FEAT-5 [stakeholder]~~ **Resolved 2026-04-28:** Last-3-values context applies to ALL metric-name-required commands, not only the logging flow. R16 updated to `@logging @management`.
- ~~Q-FEAT-6 [stakeholder]~~ **Resolved 2026-04-28:** Neither auto-create nor confirm prompt. System shows an explicit "Create [typed_name]" inline button when zero fuzzy matches are found in the logging/entry flow. R17 added.

## Rollout Considerations

- The picker is a new interaction path added to existing commands; it does not break existing exact-name command invocations.
- Users who always type exact metric names see no change in behavior (R1, R6 paths remain intact).
- The rapidfuzz library is already in the agreed technology stack (memory: project_tech_stack.md); no new dependency is introduced.
- `/help` text should be updated to indicate that metric-name arguments are optional for the affected commands and that a picker will appear if omitted.
- U2 (assumption: users name metrics consistently) becomes partially mitigated by this feature — fuzzy matching reduces the friction of near-duplicate name drift.
