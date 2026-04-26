---
doc: ADR
id: ADR-011
title: Metric name uniqueness at DB layer
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-005]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-011: Metric name uniqueness at DB layer

# Context

NFR17 requires zero duplicate `(internal_user_id, metric_name)` pairs. Duplicate metric names fragment user history into multiple separate time series and permanently corrupt the core value proposition. Two concurrent messages from the same user (e.g., rapid typing) can both pass an application-layer existence check before either insert commits — creating a duplicate despite the check. This TOCTOU (time-of-check/time-of-use) race exists even at low concurrency.

This decision parallels ADR-005 (DB boundary is safer than application-layer check).

# Decision

Metric name uniqueness per user is enforced at the database layer via a PostgreSQL UniqueConstraint on `(internal_user_id, metric_name)`. The application does NOT perform a SELECT-then-INSERT existence check. Constraint violation is caught by the application and translated to a user-friendly error message.

# Alternatives Considered

## A1 Application-layer SELECT-then-INSERT check
- Pros: can provide more informative pre-validation; no DB error to handle
- Cons: TOCTOU race — two concurrent inserts with the same (user_id, name) can both pass the SELECT check before either INSERT commits; results in duplicate records despite the check; this is a real race even at low concurrency
- Why not: TOCTOU makes uniqueness unenforceable at the application layer

## A2 DB-layer UniqueConstraint (chosen)
- Pros: atomic at the DB transaction level; no TOCTOU; eliminates the race entirely; parallels ADR-005 security principle (DB boundary enforcement); constraint violation is a clear, handleable error
- Cons: requires application to handle PostgreSQL UniqueViolation errors gracefully and translate to user messages
- Why yes: only approach that eliminates the race condition; consistent with ADR-005 principle

# Consequences

## Positive
- Metric name uniqueness is guaranteed even under concurrent creation attempts
- No TOCTOU race regardless of concurrency level
- Alembic migration includes the constraint from the first schema version

## Negative
- Application must catch and translate `asyncpg.UniqueViolationError` (or SQLAlchemy equivalent) to a user-friendly message: "You already have a metric with this name."
- Near-duplicate names (e.g., `mood` vs `Mood`) are not detected — exact-match only (SU-003, accepted limitation)

## Follow-ups
- Alembic migration must include: `UniqueConstraint("internal_user_id", "name", name="uq_metric_user_name")` — already present in `src/checkpoint_recorder/db/models.py`
- Application error handler for UniqueViolation must be present in both FR7 (explicit create) and FR6 (auto-create) paths

# NFRs affected

- NFR17 (Metric name uniqueness): DB constraint is the sole enforcement mechanism; application-layer check is absent by design
