---
doc: ADR
id: ADR-009
title: ParseAttempt + prompt atomicity — compensating delete
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

# ADR-009: ParseAttempt + prompt atomicity — compensating delete

# Context

NFR16 requires zero dangling Pending ParseAttempts (no disambiguation prompt delivered). The one-active-ParseAttempt-per-user constraint means a dangling Pending record blocks the user from receiving any further disambiguation prompts. ParseAttempt creation (DB write) and disambiguation prompt dispatch (external Telegram API call) cannot be made atomic because external I/O cannot participate in a DB transaction.

# Decision

**Compensating delete pattern:** ParseAttempt Manager attempts prompt dispatch immediately after creating the ParseAttempt record. If prompt dispatch fails, the Manager deletes the ParseAttempt record (compensating write) and returns an error to the user. No dangling Pending record remains on the normal failure path.

If the compensating delete also fails: emit `dangling_parse_attempt_alert` event; operator must manually clear the record. The dangling state is detectable via Observability within `parse_attempt_dangling_detection_window` (default 30s, configurable).

# Alternatives Considered

## A1 Transactional create + dispatch — include prompt dispatch in the DB transaction
- Pros: true atomicity
- Cons: impossible — Telegram Bot API is external I/O and cannot participate in a PostgreSQL transaction; prompt dispatch is a network call that may timeout, fail with rate limits, etc.
- Why not: technically impossible

## A2 Retry dispatch on failure
- Pros: may succeed on retry
- Cons: doesn't solve the dangling record problem if all retries fail; adds latency while retrying; if the user re-sends the message during retry, a second ParseAttempt is blocked
- Why not: retry failure leaves dangling record; doesn't eliminate the root problem

## A3 Compensating delete on dispatch failure (chosen)
- Pros: normal failure path leaves no dangling record; user receives error and can retry; simplest correct approach given the constraint
- Cons: two DB writes on the failure path (create + delete); if compensating delete also fails, operator intervention required
- Why yes: eliminates the dangling record on the most common failure path; operator fallback for the rare double-failure case

# Consequences

## Positive
- Normal failure path (prompt dispatch fails): zero dangling Pending ParseAttempts
- User receives explicit error and can retry their message
- Dangling states are detectable via Observability (30s window is configurable for operational tuning)

## Negative
- Two DB writes on failure path (create then delete) — acceptable: failure path is exceptional
- If compensating delete also fails: operator must manually clear; detectable via `dangling_parse_attempt_alert` event

## Follow-ups
- Implement compensating delete in ParseAttempt Manager using try/finally or equivalent pattern
- If compensating delete fails: emit `error_event` with `error_type: "compensation_delete_failed"` and the ParseAttempt ID
- Observability query: `parse_attempt_event`(Pending) with no `prompt_dispatched` event within 30s → operator alert

# NFRs affected

- NFR16 (Zero dangling ParseAttempts): compensating delete is the primary control; 30s detection window is the secondary detection mechanism
