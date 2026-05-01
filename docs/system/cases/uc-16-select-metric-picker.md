---
doc: UC
id: UC16
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [logging, management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
updated: 2026-05-01
tags: [project-docs, use-case]
---

# UC16: Select metric via inline picker

Traces to [[srs#FR22|FR22 Picker bare-command trigger]], [[srs#FR23|FR23 Picker fuzzy-name trigger]], [[srs#FR24|FR24 Recency ordering]], [[srs#FR25|FR25 Overflow "Show all fits"]], [[srs#FR26|FR26 Last-3-values context]], [[srs#FR27|FR27 Create button zero-match logging]], [[srs#FR28|FR28 Management zero-match message]], [[srs#FR29|FR29 PendingMetricPicker state]], [[srs#FR30|FR30 PendingPickerValue state]], [[srs#FR32|FR32 Cancel button on picker keyboard]]. User story: [[us-8-metric-picker|US8 Select a metric via inline picker]].

Activity tags: `@logging`, `@management`

## Actors

- **Primary:** End User
- **Secondary:** Metric Picker Engine (in-process), Data Repository

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle (only one non-Idle state per user at any time — BR13).
- Trigger: a metric-name-required command is issued with a missing or non-exact metric name argument. Specifically, one of:
  - (T1) Bare command: `/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete` issued with no `metric_name` argument; OR free-text entry flow where NLP cannot identify a metric name token.
  - (T2) Fuzzy name: a `metric_name` argument is present but has no exact match in the user's metric catalog, and rapidfuzz `token_set_ratio` (case-insensitive, threshold SU-010 = 70) returns ≥1 match.
- Exact metric name matches bypass this UC entirely and proceed directly to the originating command's normal flow.

## Postconditions

### On metric selected (management commands)
- ConversationState = Idle (picker resolved).
- Last-3-values context displayed.
- Originating management command proceeds with the selected metric: UC6 (archive/reactivate), UC7 (delete), UC8 (configure alert), UC10 (request chart).

### On metric selected (logging flow)
- ConversationState = PendingPickerValue.
- Last-3-values context displayed.
- System awaits numeric value from user; on receipt, Entry created (FR4 path via FR30).
- On value received: ConversationState → Idle. Entry stored. Confirmation dispatched.

### On Create button pressed (logging zero-match only)
- ConversationState → PendingPeriodicity (FR6 flow begins with typed_name pre-filled).
- No metric or entry created at this point.

### On timeout or cancellation
- ConversationState → Idle.
- No entry stored; no command executed.
- User informed of cancellation.
- Cancel button pressed on picker keyboard: same as /cancel (FR31, FR32) — ConversationState → Idle; no entry stored; no command executed; reply = "Cancelled. You're back to the main menu."

### On management zero-match
- ConversationState remains Idle.
- "No matching metrics found" message dispatched.
- Command not executed.

## Main flow — Trigger T1: bare command (no metric name)

1. User issues a metric-name-required command with no `metric_name` argument (e.g., `/chart`, or a free-text entry with no parseable metric name).
2. Dispatcher detects missing metric name. Routes to Metric Picker Engine.
3. Metric Picker Engine queries all user metrics (Active + Archived). If user has zero metrics → A5.
4. Metric Picker Engine sorts metrics by FR24 recency ordering: descending by `MAX(entry_timestamp)`; zero-entry metrics alphabetically last.
5. If total metrics > 4: display top 4 + "Show all fits" button (FR25). Otherwise display all.
6. Picker keyboard sent to user as inline keyboard message. `command_context` and `typed_name = null` stored in `state_data`.
7. ConversationState → PendingMetricPicker (FR29).
8. User presses a metric button → step 9. (If user presses "Show all fits" → A1. If user does not respond → A4. If user presses Cancel button → A6.)
9. Metric Picker Engine identifies selected metric by `metric_id` from callback data.
10. Last-3-values context assembled: fetch up to 3 most recent Entries for `(internal_user_id, metric_id)`; format as readable summary ("no entries yet" if count = 0).
11. Selection confirmation + last-3-values context dispatched as a **single message** (FR26, Q11 resolved).
12. Route based on `command_context`:
    - `logging`: ConversationState → PendingPickerValue, `state_data = {metric_id, metric_name}`. System sends prompt: "Enter value for [metric_name]:". → A3.
    - `chart`: ConversationState → Idle. UC10 proceeds with resolved metric.
    - `alert_set`: ConversationState → Idle. UC8 proceeds with resolved metric.
    - `metric_archive` / `metric_reactivate`: ConversationState → Idle. UC6 proceeds with resolved metric.
    - `metric_delete`: ConversationState → PendingMetricDeletionConfirmation. UC7 proceeds with resolved metric.

## Main flow — Trigger T2: fuzzy name supplied

1. User issues a metric-name-required command with a `metric_name` argument that has no exact match.
2. Dispatcher / NLP Parsing Engine hands off to Metric Picker Engine with the typed name.
3. Metric Picker Engine runs rapidfuzz `token_set_ratio` against all user metric names (case-insensitive). Threshold: SU-010 (default 70).
4. If ≥1 match: sort by FR24 recency ordering. If > 4 matches → apply FR25 overflow. Display picker keyboard with original typed name shown in message. ConversationState → PendingMetricPicker, `state_data = {command_context, typed_name}`.
5. If zero matches:
   - `command_context = logging`: FR27 — display "Create [typed_name]" inline button. ConversationState → PendingMetricPicker, `state_data = {command_context: "logging", typed_name: "<typed>"}`. → A2.
   - `command_context = management command`: FR28 — dispatch "No matching metrics found" message. ConversationState remains Idle. UC ends.
6. User presses a metric button → steps 9–12 of Main flow T1. (If user presses "Show all fits" → A1. If user does not respond → A4. If user presses Cancel button → A6.)

## Alternative flows

### A1 User presses "Show all fits" (FR25)
Branches from step 5 of T1 or step 4 of T2.
1. Metric Picker Engine fetches full matching metric list (all user metrics for bare command; all fuzzy matches for typed name).
2. Current message replaced with full inline keyboard listing all metrics in FR24 order.
3. State remains PendingMetricPicker. User proceeds with metric selection as in step 8 of T1 main flow.
4. Cancel button remains present on the expanded keyboard; pressing it → A6.

### A2 Create button pressed — logging zero-match (FR27)
Branches from T2 step 5 (`command_context = logging`).
1. User presses "Create [typed_name]" inline button.
2. ConversationState → PendingPeriodicity (FR6 path begins).
3. Metric Picker Engine passes `typed_name` pre-filled to periodicity prompt: "New metric `[typed_name]` — tracked daily or weekly?"
4. FR6 flow continues unchanged: periodicity confirmed → Metric + Entry created atomically.
5. ConversationState → Idle on periodicity confirmation or SU-009 timeout.
6. Cancel button is present alongside the Create button; pressing it → A6.

### A3 PendingPickerValue — value received (logging flow post-selection)
Branches from step 12 of T1/T2 main flow, `command_context = logging`.
1. User sends numeric value message (e.g., `7`).
2. Dispatcher routes to Entry Processor via PendingPickerValue state (FR30).
3. Entry Processor validates value: must be numeric (finite). If not: E4.
4. Entry Processor creates Entry atomically: `metric_id` from `state_data`, `value`, `entry_timestamp` = message time, `raw_input` = verbatim.
5. Alert evaluation triggered (FR12 path, post-commit).
6. ConversationState → Idle. Confirmation dispatched.

### A4 Picker timeout — no user interaction (FR29 / SU-009 = 24h)
1. Scheduled Process detects PendingMetricPicker state older than SU-009.
2. ConversationState → Idle.
3. User notified: "Metric selection timed out. No action was taken."
4. No entry stored; no command executed.

### A5 User has zero metrics (bare command)
Branches from T1 step 3.
1. Metric Picker Engine detects zero metrics in user catalog.
2. Message dispatched: "You have no metrics yet. Send a free-text message like `mood 7` to create your first metric."
3. ConversationState remains Idle. No picker displayed.

### A6 Cancel button pressed on picker keyboard (FR32)
Branches from T1 step 8, T2 step 4 or 6, A1, A2, or any non-Idle ConversationState (e.g., PendingPickerValue — stale picker keyboard still visible).
1. User presses the Cancel button (`callback_data = "cancel"`) on the picker keyboard.
2. Callback handler calls `answer_callback_query` unconditionally (ADR-013).
3. Picker keyboard message is edited to remove the inline keyboard (reply_markup set to null); on Telegram edit failure, log error and continue — cancellation proceeds regardless.
4. ConversationState → Idle. `state_data` cleared.
5. Reply dispatched: "Cancelled. You're back to the main menu." (identical to FR31 outcome).
6. No metric selected. No entry stored. No command executed.

## Error paths

### E1 Picker keyboard dispatch fails
- Detected at: step 6 of T1 (or step 4 of T2) — Telegram Gateway returns error.
- System response: ConversationState remains Idle. User receives generic error: "Could not display metric picker. Please try again."
- Final state: no picker session created. No entry stored.

### E2 "Show all fits" message replacement fails
- Detected at: A1 step 2.
- System response: original picker message remains. User may select from the visible 4. Error logged to Observability.

### E3 Inline callback received in unexpected state
- Detected at: callback handler — ConversationState ≠ PendingMetricPicker.
- Exception: `callback_data = "cancel"` is routed to the FR31/FR32 Idle-transition path from ANY non-Idle ConversationState (including PendingPickerValue); it is never treated as stale.
- System response for non-cancel callbacks: stale or duplicate callback; ignored or user notified "Session expired. Please re-issue the command."

### E4 Non-numeric value received in PendingPickerValue (A3 step 3)
- System response: "Please enter a numeric value (e.g., `7` or `82.5`)." ConversationState remains PendingPickerValue. User re-prompted. Timeout still applies.

### E5 PendingPickerValue timeout (SU-009 = 24h)
- Scheduled Process detects PendingPickerValue state older than SU-009.
- ConversationState → Idle. User notified: "Value entry timed out. No entry was stored."
- No entry created.

## Edge cases

- **User sends free-text while PendingMetricPicker** — Dispatcher receives a non-callback message while state = PendingMetricPicker; show reminder: "Please select a metric from the keyboard above, or use /cancel to cancel action." State not cleared (Q10 resolved).
- **Metric archived or deleted between picker display and button press** — Metric Picker Engine validates selected metric still exists and is accessible at step 9 of T1. If metric no longer valid: inform user, clear PendingMetricPicker state, return to Idle.
- **command_context = metric_delete with PendingMetricPicker timeout** — ConversationState never reached PendingMetricDeletionConfirmation; no confirmation prompt was issued; no delete risk. Idle on timeout.
- **Picker for a user with exactly 4 metrics** — no "Show all fits" button shown; all 4 displayed directly (FR25 overflow triggers at > 4, not ≥ 4).
- **Rapidfuzz matches archived metrics** — archived metrics are included in the fuzzy match pool; archival does not hide metrics from the picker. User selects an archived metric → originating command proceeds; command-level validation handles archived-metric constraints (e.g., UC8 E1 rejects alert_set on archived metric).

## Non-functional considerations

- NFR18: Picker keyboard presented ≤5s p95 from command receipt or NLP parse completion.
- NFR6, BR4: Metric catalog query scoped to `internal_user_id` — no cross-user metrics visible in picker.
- BR13: At most one PendingMetricPicker per user at any time (FR3 / DM6 constraint).
- BR14: No metric created without explicit Create button press; picker display alone does not trigger creation.
- SU-010: Rapidfuzz threshold and scoring function are configurable; default values documented here are not final until production tuning.
