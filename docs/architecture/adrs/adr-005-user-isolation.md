---
doc: ADR
id: ADR-005
title: Repository-layer user isolation
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-011]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-005: Repository-layer user isolation

# Context

NFR6 requires zero cross-user data visibility incidents (100% non-negotiable). RISK5 classifies cross-user data leakage as critical. BR4 requires all queries to be scoped by `internal_user_id` at the persistence layer, not the application filtering layer. The "miss one call" failure mode — where a developer forgets to filter results and returns all users' data — must be architecturally eliminated, not just discouraged.

# Decision

All Data Repository methods include `internal_user_id` as a mandatory typed parameter at the function signature level. No "get all" or "list" operations exist in the public repository interface that are not scoped by `internal_user_id`. The application layer does not receive unscoped results and then filter them — the query itself is always scoped.

# Alternatives Considered

## A1 Application-layer result filtering — queries return all data; application filters by user_id
- Pros: simpler repository interface; fewer parameters to thread through
- Cons: a single missing filter clause exposes all users' data; not detectable without exhaustive code review; runtime failure is silent (no exception, just wrong data returned)
- Why not: "miss one call" = critical trust failure (RISK5); this failure mode cannot be accepted

## A2 Repository-layer mandatory scoping (chosen)
- Pros: impossible to make an unscoped call by accident — the method signature enforces the parameter; testable (integration tests call with mismatched user_id, assert empty); eliminates the failure mode structurally
- Cons: every repository method requires `internal_user_id` parameter; more verbose interface
- Why yes: structural elimination of the failure mode is worth the interface verbosity

# Consequences

## Positive
- Cross-user data leakage is structurally impossible via the repository interface
- Testable: every read operation can be integration-tested with a mismatched user_id asserting empty/not-found

## Negative
- Repository interface is more verbose — `internal_user_id` must be threaded through every call
- Internal repository operations (e.g., Scheduled Process batch purge by timestamp) require careful scoping to avoid processing one user's data as another's

## Follow-ups
- Integration test suite MUST verify every read operation with a mismatched `internal_user_id` returns empty or not-found
- Code review checklist: any new repository method that does not include `internal_user_id` as a mandatory parameter requires explicit architectural justification

# NFRs affected

- NFR6 (Per-user isolation): structural enforcement at repository layer is the primary control; this ADR is the implementation of that NFR
