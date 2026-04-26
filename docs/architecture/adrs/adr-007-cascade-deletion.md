---
doc: ADR
id: ADR-007
title: Cascade deletion atomicity — single DB transaction
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

# ADR-007: Cascade deletion atomicity — single DB transaction

# Context

BR8 requires cascade deletion (metric via FR10; account purge via FR18) to be atomic — either all associated records are deleted or none. NFR15 requires all `raw_input` fields to be purged as part of cascade. At ~100 time series per user, the transaction scope is small. Partial deletion is a data integrity failure that could leave orphaned records and violate the privacy promise made to users.

# Decision

All cascade deletions are executed within a single PostgreSQL database transaction. The transaction commits only when all related entities have been successfully deleted. On any failure, the transaction rolls back — no partial deletion is possible. The Data Repository exposes a transactional cascade delete operation as a first-class method.

# Alternatives Considered

## A1 Soft-delete + background vacuum worker
- Pros: non-blocking; records physically present until vacuum runs
- Cons: `raw_input` physically remains until vacuum (PII exposure window); violates NFR15; user told their data is deleted when it physically is not; vacuum failure leaves data indefinitely
- Why not: unacceptable PII retention window; violates user privacy promise

## A2 Application-level multi-step deletion with compensating writes
- Pros: could handle very large cascades without long-running transactions
- Cons: inconsistent state if any compensation step fails; coordination complexity; unnecessary at ~100 time series per user
- Why not: adds coordination complexity that the single-transaction approach eliminates

## A3 Single DB transaction (chosen)
- Pros: atomicity guaranteed by PostgreSQL; rollback on any failure; simplest correct approach; at ~100 time series per user, transaction duration is negligible
- Cons: long-running transaction holds locks; not a concern at portfolio scale
- Why yes: simplest correct approach; matches scale; atomicity is non-negotiable

# Consequences

## Positive
- Partial deletion is impossible — either complete or nothing
- Raw_input purge is guaranteed to happen as part of the same commit
- Idempotent: rollback means the delete can be retried safely

## Negative
- Requires PostgreSQL to support transactions (confirmed — Supabase PostgreSQL)
- Very large cascades could cause long-running transactions at scale — not a concern at ≤20 users

## Follow-ups
- Data Repository must expose a `cascade_delete_user` and `cascade_delete_metric` method that wraps the entire delete in a single transaction
- Scheduled Process purge of PendingDeletion accounts must use this method per user (not a single transaction spanning all users — each user is atomic independently)

# NFRs affected

- NFR15 (raw_input purge): guaranteed by single transaction scope — raw_input fields included in the same DELETE
- NFR12, NFR13 (data retention): cascade atomicity ensures no partially-purged user state violates retention commitments
