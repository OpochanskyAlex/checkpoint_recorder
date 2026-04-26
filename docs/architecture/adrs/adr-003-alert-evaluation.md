---
doc: ADR
id: ADR-003
title: Post-commit in-process alert evaluation
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-001, ADR-010]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-003: Post-commit in-process alert evaluation

# Context

BR1 (one-shot alert) and SRS §8.3 atomicity rules require that alert evaluation failure must never roll back a stored Entry. The entry must be durable regardless of whether alerts fire. NFR1 requires entry acknowledgment ≤5s p95. At ≤100 entries/day, a message queue or separate worker adds infrastructure complexity with no benefit.

# Decision

Alert evaluation is triggered immediately after successful Entry storage as a post-commit in-process event, decoupled from the entry storage transaction. Entry Processor must explicitly catch and log alert evaluation failures without propagating them as entry storage failures.

# Alternatives Considered

## A1 Synchronous within the same DB transaction
- Pros: atomic; consistent state
- Cons: alert failure rolls back the entry — explicitly prohibited by BR1 and SRS §8.3; violates the core invariant
- Why not: prohibited by the requirements

## A2 Async work queue (Redis + Celery, or similar)
- Pros: decoupled; retryable; formal back-pressure
- Cons: adds Redis + worker deployment; overkill at ≤20 users and ≤100 entries/day; complicates Railway deployment
- Why not: disproportionate infrastructure cost for this scale

## A3 Post-commit in-process event (chosen)
- Pros: entry always preserved on alert failure; simple; ≤60s alert dispatch budget easily met in-process; no infrastructure additions
- Cons: slow alert evaluation delays confirmation message to user (though entry is already stored); at scale, this path would require a queue
- Why yes: matches constraints (entry invariant) and scale (≤20 users)

# Consequences

## Positive
- Entry is always preserved regardless of alert outcome (BR1 respected)
- No additional infrastructure
- Alert evaluation within ≤60s budget comfortably in-process at this scale

## Negative
- A slow or failing alert evaluation path delays the confirmation message the user receives (entry is safe, but the user may wait longer for the ack)
- At scale (>20 users or alert-heavy workloads), this path would need to move to a queue

## Follow-ups
- Ensure Entry Processor wraps Alert Engine call in try/except; any exception becomes a logged failure event, not a propagated error
- Monitor alert evaluation latency in Observability; if it approaches the confirmation dispatch budget, move to a queue

# NFRs affected

- NFR10 (Alert eval coverage): every evaluation must emit `alert_evaluation_event` regardless of outcome — this must be emitted in the exception handler path too
- NFR1 (Entry ack ≤5s): alert evaluation must not block the ack path; Entry Processor sends ack after evaluation completes (or fails)
