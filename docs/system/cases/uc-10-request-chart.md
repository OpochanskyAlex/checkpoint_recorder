---
doc: UC
id: UC10
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [analytics]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC10: Request trend chart

Traces to [[srs#FR14|FR14 Chart generation and delivery]]. User story: [[us-4-view-charts|US4 View trend charts]].

Activity tags: `@analytics`

## Actors

- **Primary:** End User
- **Secondary:** Chart Generator (background coroutine), Telegram Gateway

## Preconditions

- InternalUser.account_status = Active.
- Metric.status = Active or Archived.

## Postconditions

### On success
- Immediate acknowledgment dispatched (≤5s).
- Time-series chart image delivered via Telegram (≤30s from request).
- `chart_invocation_event` and `chart_delivery_event` (outcome=delivered) emitted.

### On failure
- Acknowledgment dispatched (≤5s).
- Error message dispatched as second Telegram message.
- `chart_delivery_event` (outcome=failed) emitted.

## Main flow (happy path)

1. User sends `/chart metric_name [time_range]`.
2. Chart Generator verifies Metric belongs to user (`status ∈ {Active, Archived}`).
3. Chart Generator verifies at least 2 Entry records exist in the requested range. (If not: E1.)
4. Chart Generator dispatches acknowledgment message immediately (≤5s from step 1). `chart_invocation_event` emitted.
5. Background coroutine launched (fire-and-forget): retrieves Entry history; renders time-series PNG chart (one series per dimension for compound metrics; default range: last 30 days unless specified — Q4).
6. Background coroutine delivers chart image via Telegram Gateway (≤30s from step 1).
7. `chart_delivery_event` (outcome=delivered) emitted.

## Error paths

### E1 Metric has no entries (or fewer than 2 in range)
- Detected at: step 3.
- System response: informative error returned; no acknowledgment or chart.

### E2 Chart rendering or delivery fails (in background coroutine)
- Detected at: step 5 or 6.
- System response: coroutine catches exception; dispatches second Telegram message with error description. `chart_delivery_event` (outcome=failed) emitted.
- Final state: user has acknowledgment + error message; may retry.

### E3 Background coroutine crashes silently (exception not caught)
- Final state: user receives acknowledgment but no chart and no error (known limitation — AD-10). Operator-detectable via `chart_invocation_event` present but `chart_delivery_event` absent.

## Edge cases

- **Very large time range** → large image may fail Telegram delivery; coroutine should cap chart size or warn user.
- **Compound metric** → one line per dimension in the chart; axes: entry_timestamp (x), dimension value (y).

## Non-functional considerations

- NFR3: Acknowledgment ≤5s p95; full delivery ≤30s p95.
- The two-phase pattern (acknowledgment + async delivery) is mandatory to avoid Telegram bot timeout perception.
