---
doc: ADR
id: ADR-001
title: Single-process monolith architecture
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-002, ADR-003, ADR-006, ADR-010]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-001: Single-process monolith architecture

# Context

The confirmed scale ceiling is 20 concurrent users (~100 active metric time series). The system has a single operator assisted by AI agents. Distribution adds infrastructure complexity, network failure modes, and operational overhead that is disproportionate to this scale. Components still need clear boundaries to enable future extraction if scale requires it.

# Decision

Deploy the system as a single Python process with logically separated, named components communicating in-process. No microservices. No message queue. No separate worker process.

# Alternatives Considered

## A1 Microservices — each component as a separate deployable service
- Pros: independent scaling; fault isolation per service; polyglot possible
- Cons: network latency between components threatens NFR1 (≤5s entry ack); multiple deployments to manage; inter-service auth; disproportionate for ≤20 users
- Why not: operational complexity exceeds value at this scale

## A2 Serverless functions — each flow as an independent function invocation
- Pros: zero idle cost; auto-scaling
- Cons: cold starts add latency threatening NFR1; stateful in-process objects (ConversationState cache, NLP model) impossible across invocations; APScheduler incompatible
- Why not: cold start latency incompatible with ≤5s ack requirement

## A3 Single-process monolith (chosen)
- Pros: zero deployment complexity; in-process communication is nanoseconds; single Railway deployment; easy observability; clear upgrade path to service extraction
- Cons: coupled failure modes — entire process fails together; no horizontal scaling without redesign
- Why yes: matches confirmed scale; single operator; components separated logically for future extraction

# Consequences

## Positive
- Simplest Railway deployment: one Procfile entry
- In-process component communication — no serialization, no network failure modes
- APScheduler runs naturally in-process
- asyncio event loop handles all concurrency needs at ≤20 users

## Negative
- Whole process fails on any unhandled error — Railway process supervisor mitigates via restart
- Horizontal scaling requires architectural redesign at scale ceiling

## Follow-ups
- Enforce clear component interfaces in code: no direct cross-component attribute access, only method calls
- Architecture review required before exceeding 20-user ceiling

# NFRs affected

- NFR4 (Uptime ≥95%): Railway process supervisor provides restart-on-failure; single process = single restart target
- NFR14 (20 concurrent users): asyncio event loop + SQLAlchemy async connection pool handles concurrency at this scale; beyond ceiling, requires redesign
