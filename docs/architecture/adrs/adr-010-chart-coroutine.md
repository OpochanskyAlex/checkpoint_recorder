---
doc: ADR
id: ADR-010
title: Async chart execution — fire-and-forget coroutine
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-006, ADR-001]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-010: Async chart execution — fire-and-forget coroutine

# Context

ADR-006 establishes the two-phase chart response pattern. The second phase (chart generation + delivery) must run asynchronously after the acknowledgment is sent. At ≤20 users with occasional chart requests, formal task queue infrastructure is unnecessary. matplotlib is CPU-bound and must run in a thread executor to avoid blocking the asyncio event loop.

# Decision

Chart generation is implemented as a post-response fire-and-forget asyncio coroutine. The coroutine: (a) uses `asyncio.run_in_executor` for the matplotlib rendering (CPU-bound); (b) catches all exceptions with a top-level try/except; (c) on any failure, dispatches an error message to the user as a second Telegram message; (d) emits `chart_delivery_event` with outcome "delivered" or "failed" regardless of success or failure.

# Alternatives Considered

## A1 Dedicated background thread pool
- Pros: controllable concurrency limit; back-pressure mechanism
- Cons: thread management overhead; adds complexity; not needed at ≤20 users with occasional chart requests
- Why not: unnecessary complexity for a single async concern

## A2 In-process async task queue (e.g., asyncio.Queue)
- Pros: formal back-pressure; FIFO ordering; retryable
- Cons: adds queue management code; overkill for occasional chart requests from ≤20 users
- Why not: no back-pressure need at this scale; no retry requirement defined

## A3 Fire-and-forget asyncio coroutine (chosen)
- Pros: minimum viable implementation; asyncio-native; no additional infrastructure; CPU-bound rendering handled by executor
- Cons: no formal back-pressure; coroutine crash after ack means user gets ack + no chart + no error unless the mandatory top-level exception handler catches it
- Why yes: mandatory exception handler mitigates the crash case; coroutine is read-only relative to mutable state

# Consequences

## Positive
- Minimum viable async implementation for a single async concern in a monolith
- asyncio-native; no threads except for the matplotlib executor
- Top-level exception handler + `chart_delivery_event`(failed) ensures operator visibility on failure

## Negative
- If the top-level exception handler itself fails (coding error), user receives ack but no chart and no error — known limitation, operator-detectable via Observability
- Coroutine accesses Data Repository in read-only mode; concurrent reads assumed safe with asyncpg (confirmed for PostgreSQL)

## Follow-ups
- Coroutine must include a try/except covering the entire body: `async def _generate_and_deliver_chart(...):`
- Chart delivery failure must dispatch a second Telegram message to the user: "Chart generation failed. Please try again."
- `chart_delivery_event` must be emitted in both success and failure branches, including the exception handler

# NFRs affected

- NFR3 (Chart ack ≤5s; delivery ≤30s): coroutine executes after ack is sent; delivery target is ≤30s from the original request, measured by `chart_delivery_event` timestamp delta
