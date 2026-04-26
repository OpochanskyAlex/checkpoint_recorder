---
doc: UC
id: UC4
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC4: Create metric explicitly

Traces to [[srs#FR7|FR7 Explicit metric creation]]. User story: [[us-3-manage-metrics|US3 Manage metric catalog]].

Activity tags: `@management`

## Actors

- **Primary:** End User

## Preconditions

- InternalUser.account_status = Active.
- ConversationState = Idle.

## Postconditions

### On success
- Metric record created with `status = Active`.
- Confirmation with metric_id dispatched.

### On failure
- No Metric record created; validation error returned.

## Main flow (happy path)

1. User sends `/metric_create name periodicity [unit] [dimension_names...]`.
2. Metric Manager validates `name`: non-empty, ≤100 chars.
3. Metric Manager validates `periodicity` ∈ {daily, weekly} (BR9).
4. Metric Manager validates `unit` if provided: non-empty, ≤50 chars.
5. Metric Manager validates `dimension_names` if provided: non-empty list, each ≤50 chars, no duplicates within list.
6. Metric Manager inserts Metric record. DB-layer UniqueConstraint `(internal_user_id, name)` enforces uniqueness (NFR17, BR7).
7. Confirmation dispatched with `metric_id` and field summary.

## Alternative flows

### A1 Compound metric with dimension_names
Step 6 variant: Metric.dimension_names populated. Subsequent compound entries for this metric map values to these names in definition order.

### A2 Single dimension_name provided (degenerate compound)
Treated as single-value metric; dimension_names ignored.

## Error paths

### E1 Duplicate metric name for same user
- Detected at: step 6 (DB constraint violation).
- System response: "You already have a metric with this name." Suggest listing existing metrics.

### E2 Invalid periodicity value
- Detected at: step 3.
- System response: "Periodicity must be 'daily' or 'weekly'."

### E3 Duplicate dimension name within the list
- Detected at: step 5.
- System response: lists the offending duplicate names; metric not created.

## Edge cases

- **Concurrent `/metric_create` calls with same name** → DB UniqueConstraint guarantees exactly one record created; second call returns E1.

## Non-functional considerations

- NFR17, BR7: Uniqueness enforced at DB layer — application does not perform a pre-insert existence check (TOCTOU-vulnerable).
