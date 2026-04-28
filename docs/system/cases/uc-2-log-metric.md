---
doc: UC
id: UC2
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [logging]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
updated: 2026-04-28
tags: [project-docs, use-case]
---

# UC2: Log metric (auto-parsed)

Traces to [[srs#FR4|FR4 Standard data entry]], [[srs#FR6|FR6 Metric auto-creation]], [[srs#FR12|FR12 Alert evaluation]]. User story: [[us-1-log-metric|US1 Log a metric in free text]].

Activity tags: `@logging`

## Actors

- **Primary:** End User
- **Secondary:** NLP Parsing Engine, Alert Engine, Observability Collector

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle.
- Inbound message is not a recognized `/command`.

## Postconditions

### On success
- Exactly one immutable Entry record stored with `raw_input` = verbatim message text.
- Confirmation dispatched to user (≤5s p95).
- `parse_outcome_event` emitted with outcome=success.
- Alert evaluation triggered (decoupled from entry storage success).

### On failure
- No Entry record created.
- No confirmation sent; user asked to re-submit.

## Main flow (happy path)

1. End User sends free-text message (e.g., `mood 7`).
2. Entry Processor invokes NLP Parsing Engine. NLP returns `{metric_name, value(s), dimension_assignments, confidence_score, outcome=auto-parse}`. Confidence ≥ configured threshold.
3. Entry Processor looks up Metric by `(internal_user_id, metric_name)`. Metric found — proceed to step 4. (If not found: A1.)
4. Entry Processor creates Entry record atomically: `metric_id`, `value` (or `dimension_assignments` for compound), `entry_timestamp` = message time, `stored_timestamp` = now(), `raw_input` = verbatim message.
5. Entry Processor triggers Alert Engine evaluation (post-commit event, not transactionally coupled). Alert Engine evaluates all Active alerts for this metric (→ see FR12; skips if Metric.status = Archived).
6. Entry Processor emits `parse_outcome_event` (outcome=success, entry_id) — fire-and-forget.
7. Entry Processor dispatches confirmation message to user.

## Alternative flows

### A1 Metric name unrecognized — Create button flow (FR27 → FR6)
Branches from step 3. **Note (2026-04-28 smart-metric-picker delta):** The trigger for metric auto-creation is now the explicit "Create [typed_name]" inline button dispatched by FR27 (via UC16), NOT silent auto-creation on unrecognized name. The periodicity + atomic create mechanic (steps 2–6 below) is unchanged.
1. Entry Processor determines no exact match. Zero fuzzy matches (rapidfuzz `token_set_ratio` < SU-010 threshold). UC16 (FR27) presents "Create [typed_name]" inline button. ConversationState → PendingMetricPicker.
2. User presses the Create button. UC16 A2 routes to FR6: periodicity selection prompt dispatched: "New metric `{name}` — is it tracked daily or weekly?" ConversationState → PendingPeriodicity. Metric record NOT written yet.
3. User responds with periodicity selection (Dispatcher routes via FR3).
4. Entry Processor atomically creates Metric record (with confirmed periodicity) AND Entry record in a single DB transaction.
5. ConversationState → Idle.
6. Alert evaluation triggered (step 5 of main flow). Confirmation dispatched.

### A2 Compound entry (multi-value dimensions)
Step 2 variant: NLP returns multiple `{dimension_name → value}` pairs in `dimension_assignments`. `value` is null. Steps 3–7 proceed identically; Entry stores `dimension_assignments` instead of `value`.

### A3 PendingPeriodicity timeout (SU-009 = 24h)
From A1 step 2, if user never responds:
1. Scheduled Process detects stale PendingPeriodicity state (FR18).
2. ConversationState cleared to Idle. No Metric or Entry created.
3. `periodicity_prompt_event` emitted with outcome=abandoned.

## Error paths

### E1 Entry storage fails (DB write error)
- Detected at: step 4.
- System response: no confirmation sent; user receives: "Your entry could not be saved. Please re-submit." Alert Engine is not triggered.
- Final state: no Entry stored; ConversationState remains Idle; user retries.

### E2 Alert evaluation fails (post-commit)
- Detected at: step 5.
- System response: Entry preserved (not rolled back). Failure logged to Observability. User receives confirmation normally (alert failure does not affect confirmation).
- Final state: Entry stored; alert may not have evaluated. BR1: alert remains in prior state.

### E3 Confirmation dispatch fails
- Detected at: step 7.
- System response: Entry is preserved. User does not receive confirmation (known limitation). No retry on confirmation.
- Final state: Entry stored; user may re-submit thinking it wasn't saved (idempotent risk).

### E4 Metric name found but Metric.status = Deleted
- Detected at: step 3.
- System response: treated as unrecognized name → A1 (auto-create with new record).

## Edge cases

- **PendingPeriodicity while ambiguous message arrives** → Dispatcher routes new message to Entry Processor as non-periodicity (blocked); no new ParseAttempt created. User reminded to complete periodicity selection first.
- **SU-009 timeout concurrent with user's periodicity response** → Scheduled Process clears state; user's response arrives to Idle state, treated as new free-text entry → UC2 restarts from step 1.
- **Free-text message contains a metric name with no exact match but ≥1 fuzzy match (2026-04-28)** → UC16 (smart-metric-picker) intercepts before FR4 metric lookup. Picker keyboard displayed with fuzzy-matched metrics. UC2 main flow resumes after user selects a metric via UC16 and ConversationState transitions through PendingMetricPicker → PendingPickerValue → Idle (FR29, FR30).
- **UC2 extended by UC16** — this UC is extended by [[uc-16-select-metric-picker|UC16]] when the free-text entry flow encounters a missing or fuzzy-matched metric name. Exact matches bypass UC16 entirely.

## Non-functional considerations

- NFR1: End-to-end ≤5s p95 (message received → confirmation dispatched).
- NFR5, BR2: Entry immutability — no UPDATE on Entry table after INSERT.
- NFR9: `parse_outcome_event` must be emitted for every parse attempt, including successes.
- NFR8, BR6: `raw_input` must not appear in any emitted event payload.
