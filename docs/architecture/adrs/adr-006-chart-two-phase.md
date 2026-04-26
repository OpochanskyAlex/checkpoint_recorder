---
doc: ADR
id: ADR-006
title: Two-phase chart response
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-010]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-006: Two-phase chart response

# Context

Chart generation may take up to 30s (matplotlib rendering + image encoding + Telegram image upload). NFR3 requires an acknowledgment within ≤5s of the chart request. Blocking the webhook handler for 30s would cause Telegram to timeout the webhook call and re-deliver the request, potentially generating duplicate charts.

# Decision

Chart requests use a two-phase response pattern: an immediate acknowledgment message ("generating chart…") is dispatched synchronously within ≤5s, then chart generation and image delivery are executed in a post-response fire-and-forget asyncio coroutine within ≤30s total. See also [[adr-010-chart-coroutine|ADR-010]] for the coroutine execution model.

# Alternatives Considered

## A1 Single-phase synchronous — block until chart delivered
- Pros: simpler code path; no coroutine coordination needed
- Cons: 30s handler blocks the event loop; Telegram timeouts the webhook; risk of duplicate delivery attempts; violates NFR3 (ack ≤5s)
- Why not: violates NFR3; blocks the asyncio event loop affecting all concurrent users

## A2 Two-phase async (chosen)
- Pros: acknowledgment within ≤5s; chart generation independent of webhook response; user gets immediate feedback
- Cons: if the coroutine crashes after the acknowledgment, the user is left with an ack but no chart or error (mitigated by ADR-010 exception handler); adds implementation complexity
- Why yes: only approach that satisfies both NFR3 constraints (ack ≤5s AND delivery ≤30s)

# Consequences

## Positive
- Acknowledgment ≤5s satisfied without blocking the event loop
- Chart generation fully decoupled from webhook response lifecycle
- Users receive immediate confirmation that their request was received

## Negative
- Coroutine crash after ack = user has acknowledgment but no chart and no error (if exception handler fails — see ADR-010)
- Two-phase coordination requires Telegram Gateway to support sending a follow-up message outside the request/response cycle

## Follow-ups
- Implement and enforce the mandatory top-level exception handler in the chart coroutine (ADR-010)
- Monitor `chart_invocation_event` vs. `chart_delivery_event` in Observability to detect missing delivery events

# NFRs affected

- NFR3 (Chart ack ≤5s; delivery ≤30s): this ADR is the direct implementation of both constraints
