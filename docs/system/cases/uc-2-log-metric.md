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
updated: 2026-04-26
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

### A1 Metric name unrecognized (metric auto-creation, FR6)
Branches from step 3.
1. Entry Processor dispatches periodicity selection prompt: "New metric `{name}` — is it tracked daily or weekly?"
2. User Session Guard sets ConversationState = PendingPeriodicity. Metric record NOT written yet.
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

## Non-functional considerations

- NFR1: End-to-end ≤5s p95 (message received → confirmation dispatched).
- NFR5, BR2: Entry immutability — no UPDATE on Entry table after INSERT.
- NFR9: `parse_outcome_event` must be emitted for every parse attempt, including successes.
- NFR8, BR6: `raw_input` must not appear in any emitted event payload.
