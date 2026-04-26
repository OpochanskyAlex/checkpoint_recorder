---
doc: ADR
id: ADR-004
title: MetricActivityStatus — lazy computation on read
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-001]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-004: MetricActivityStatus — lazy computation on read

# Context

MetricActivityStatus (periods_filled 0–5; Active if ≥4) is derived from Entry history scoped to the metric's own periodicity. It is required for FR8 (metric listing) and used to compute the `active_users_count` Observability metric (NFR4 business metric). The question is when and how to compute it.

# Decision

Lazy computation on read (FR8 invocation). MetricActivityStatus is NOT stored as a persistent row — it is computed from Entry records on demand. Recomputed if `computation_timestamp < now() - 1 periodicity unit` (24h for daily; 7 days for weekly). On each successful Entry write, Entry Processor additionally pushes `active_users_count` to ObservabilityCollector to keep the dashboard metric approximately current.

# Alternatives Considered

## A1 Event-driven — recompute on every Entry write
- Pros: always fresh; no staleness
- Cons: adds recomputation latency to every Entry write path; at ≤100 entries/day the cost is negligible, but it violates the principle of not adding complexity without value
- Why not: staleness window (24h for daily, 7 days for weekly) is acceptable for a portfolio metric; FR8 is an on-demand read

## A2 Scheduled — recompute on period boundary
- Pros: fresh at boundary; doesn't add write latency
- Cons: adds a Scheduled Process job; if Scheduled Process fails, status is stale until next run; adds complexity
- Why not: lazy computation is simpler and fresher on demand

## A3 Lazy computation on read (chosen)
- Pros: lowest complexity; fresh at the moment the user requests the list; no separate storage; no write path overhead
- Cons: slightly slower FR8 response for users with many metrics; computation_timestamp staleness window means Observability `active_users_count` may lag at period boundaries
- Why yes: at ≤100 time series, computation cost is negligible; staleness is acknowledged and accepted

# Consequences

## Positive
- No MetricActivityStatus persistence layer to maintain or migrate
- FR8 response always computed from actual Entry data at time of request
- No additional write latency on Entry creation

## Negative
- `active_users_count` in Observability may be slightly stale at period boundaries (no Entry written at midnight doesn't trigger recomputation). Acknowledged in SRS §11.1 with caveat.

## Follow-ups
- Add staleness caveat to SRS NFR mapping and Observability dashboard definition
- If metrics volume exceeds ~100 time series, profile FR8 response time

# NFRs affected

- NFR4 (Uptime ≥95%): no separate computation process to fail; computation happens in-process on FR8 call
