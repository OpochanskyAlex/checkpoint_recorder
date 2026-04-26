---
doc: ADR
id: ADR-012
title: Technology stack
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-001, ADR-002, ADR-005, ADR-007, ADR-010, ADR-011]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-012: Technology stack

# Context

Architecture v0.9 (source) deferred three technology choices as open items: AU-001 (NLP library), AU-002 (deployment platform), AU-003 (data repository). `technology.md` resolves all three and defines the full stack. This ADR formalizes those resolutions and records the rationale for the complete technology selection.

Source open items resolved by this ADR:
- ~~AU-001~~ NLP library → rapidfuzz + pint + regex (in-process)
- ~~AU-002~~ Deployment platform → Railway PaaS
- ~~AU-003~~ Data repository → Supabase managed PostgreSQL
- ~~AD-2 source~~ Polling vs. webhook → webhook ([[adr-002-telegram-gateway|ADR-002]])

> **Source discrepancy D2 (note only — do not edit code):** `technology.md` states "FSM / ConversationState: aiogram built-in FSM, Persisted via SQLAlchemy storage backend." The current `src/checkpoint_recorder/bot.py` creates a plain `Dispatcher()` with no FSM storage backend; ConversationState is managed directly as a DB row (DM6). This is an implementation-vs-plan discrepancy. Resolution deferred to bot description update per stakeholder instruction.

# Decision

**Full technology stack:**

| Concern | Choice | Rationale |
|---|---|---|
| Language | Python 3.12+ | Async support; ecosystem (aiogram, rapidfuzz, matplotlib); team familiarity |
| Telegram framework | aiogram 3.x (webhook mode) | Production-grade async bot framework; webhook support; FSM primitives |
| Hosting | Railway PaaS | Zero-ops deploys; HTTPS out of the box (required for webhook); env var management; free tier covers portfolio scale |
| Database | Supabase managed PostgreSQL | ACID transactions (ADR-007); compound unique constraints (ADR-011); concurrent reads (ADR-010); managed backups RPO ≤24h; free tier covers portfolio scale |
| Async DB driver | asyncpg + SQLAlchemy 2.x async | Non-blocking queries; ORM comfort; Alembic migrations |
| NLP — metric matching | rapidfuzz | Fuzzy string matching against user's metric vocabulary; confidence score maps to SU-002 threshold |
| NLP — value/unit extraction | pint + regex | Extracts values like `80kg`, `5 reps`, `120/80`; in-process (no external service) |
| Chart rendering | matplotlib (Agg backend) + asyncio executor | Headless PNG generation; no browser dependency; offloaded to thread executor (ADR-010) |
| Scheduled jobs | APScheduler 3.x | In-process async; satisfies ≥12h cadence; no separate worker process needed |
| Observability | structlog | Structured JSON output to stderr; events stored in PostgreSQL ObservabilityEvent table |
| Config / secrets | pydantic-settings | Typed config from environment variables; bot token never in source |

# Alternatives Considered

## A1 SQLite (originally proposed in implementation_spec.md for OI-3)
- Pros: zero setup; no external dependency; WAL mode supports concurrent reads
- Cons: not managed (no automatic backups); single-file limits multi-process access; no point-in-time recovery; not suitable for production data with 1-year retention guarantee
- Why not: Supabase PostgreSQL provides managed backups (RPO ≤24h) satisfying D-013; PostgreSQL is the natural upgrade from SQLite without schema changes

## A2 External NLP service (cloud API)
- Pros: more powerful language models
- Cons: external network round-trip adds latency threatening NFR1 (≤5s ack); cost at scale; PII in user messages sent to third-party (raw_input privacy risk); zero-cost constraint for portfolio project
- Why not: latency; cost; privacy; in-process rapidfuzz + pint is sufficient for the domain vocabulary

## A3 Heroku / Fly.io / VPS (alternative hosting)
- Pros: comparable features
- Cons: no significant advantage over Railway for this use case; stakeholder has existing Railway familiarity
- Why not: Railway is the confirmed choice; comparable alternatives not worth switching for

# Consequences

## Positive
- Full async stack: aiogram + asyncpg + SQLAlchemy async + APScheduler — no blocking I/O on the event loop
- Managed PostgreSQL eliminates backup implementation burden (RPO ≤24h automatic)
- Railway free tier + Supabase free tier covers portfolio-scale operating cost (~$0/month)
- All architecture open items resolved: no blocking uncertainties remain for implementation

## Negative
- Supabase free tier has connection limits (~60 simultaneous connections) — not a concern at ≤20 users
- Railway free tier has sleep-on-idle behavior — must configure "always on" or use paid plan for production
- rapidfuzz fuzzy matching requires tuning of NLP confidence threshold (SU-002) — start at 0.7 and adjust from production data

## Follow-ups
- Confirm Railway "always on" configuration before first production deployment
- Define and document NLP confidence threshold 0.7 as the starting value in configuration; expose as env var
- Confirm Supabase managed backup is enabled and RPO ≤24h before first production deployment

# NFRs affected

- NFR1, NFR2 (latency ≤5s): in-process NLP eliminates external service round-trip; critical for entry ack budget
- NFR4 (Uptime ≥95%): Railway process supervisor + always-on configuration
- NFR7 (Token confidentiality): pydantic-settings + Railway env var management
- NFR12, NFR13 (Data retention + grace period): Supabase managed backups + PostgreSQL ACID transactions
