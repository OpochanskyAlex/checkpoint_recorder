# Universal Parameter Tracker — Project Overview

> A Telegram bot that lets you log anything in free text and see your trends over time.
> Built end-to-end with AI-agent-assisted documentation and code generation.

---

## The Idea

Most people quit tracking habits not because they lack motivation — but because switching to a dedicated app feels like too much friction. This project tests a simple hypothesis: **if logging lives inside Telegram, a tool you already open dozens of times a day, people will actually stick to it.**

You send the bot a plain message like `mood 7` or `bench press 80kg 5reps`. It stores it, builds a time series, renders charts on demand, and fires alerts when you cross a threshold. No sign-up screens. No categories to configure in advance. The bot creates your metrics on the fly, on first use.

---

## Example Conversations

```
You:   fuel 40L
Bot:   ✅ New parameter created: fuel
       Recorded 40 L for fuel. Entry #1.

You:   mood 7
Bot:   ✅ Recorded 7 for mood. Running average: 7.0

You:   bench press 80kg 5reps
Bot:   ✅ Recorded for bench press — weight: 80 kg · reps: 5

You:   /chart mood
Bot:   [sends a line chart image of your mood over time]

You:   training
Bot:   ⚠️ I couldn't identify the metric automatically.
       Did you mean:
         1. training weight
         2. training duration
       Reply with a number, or /skip to save for later.

You:   /list
Bot:   Your tracked parameters (4):
         • fuel  (weekly)
         • mood  (daily) ← active
         • bench press  (weekly) ← active
         • calories  (daily)

You:   /help
Bot:   Available commands:
         /list     — show all your parameters
         /chart    — plot a metric trend
         /delete   — remove a metric and its history
         /alert    — set a threshold alert
         /history  — last N entries for a metric
         /account  — account settings and deletion
```

---

## Key Features

| Feature | How it works |
|---|---|
| **Free-text logging** | Type anything natural; NLP parser extracts metric name + value(s) |
| **Auto-created parameters** | First time you log a metric, it's created — no setup needed |
| **Multi-value entries** | Compound entries like `80kg 5reps` are split into dimensions |
| **Parse disambiguation** | If input is ambiguous, bot asks you to clarify — never silently drops data |
| **Trend charts** | On-demand time-series images sent directly in chat |
| **Threshold alerts** | One-shot alerts when a value crosses your defined limit |
| **Data isolation** | Each user's data is completely private — no cross-user visibility |
| **Account lifecycle** | Delete with 3-day grace period; data retained 1 year after last use |

---

## Documentation Generated (Input Files)

All documents were produced by AI agents from a single 1-page brief (`initial_task_setup.md`) through a multi-stage pipeline:

| Document | File | Versions | Description |
|---|---|---|---|
| **Seed brief** | `initial_task_setup.md` | v1 | Original hand-written idea — 1 page |
| **Business Analysis** | `business_analysis.md` | v0.1 → v0.6 | Problem, stakeholders, success metrics, risks, decisions |
| **System Context** | `system_analysis.md` | v0.1 → v0.8 | Actors, boundaries, flows, entities, states |
| **Architecture Overview** | `architecture.md` | v0.1 → v0.9 | Components, interaction patterns, NFRs, failure scenarios |
| **Architecture Review** | `architecture_review.md` | v0.8, v0.9 | Critic-scored review with mandatory revisions |
| **Implementation Spec** | `implementation_spec.md` | v1.0 | Functional requirements, validation rules, error contracts |
| **Delivery Plan** | `project_plan.md` | v1.0 | 18 FRs + 14 NFRs staged into delivery batches |

The pipeline ran **6 document iterations with critic review gates** before implementation began. A new version was only promoted when the critic score exceeded 40/50.

---

## Technology Stack

| Layer | Technology | Why |
|---|---|---|
| **Language** | Python 3.12+ | Ecosystem + async support |
| **Telegram framework** | aiogram 3.x (webhook mode) | Production-grade async bot framework |
| **Hosting** | Railway (PaaS) | Zero-ops deploys, HTTPS out of the box |
| **Database** | Supabase (managed PostgreSQL) | Managed backups, free tier covers this scale |
| **Async DB driver** | asyncpg + SQLAlchemy 2.x async | Non-blocking queries with ORM comfort |
| **Migrations** | Alembic | Schema versioning |
| **NLP parsing** | rapidfuzz + pint + custom scoring | Fuzzy metric matching + unit parsing, in-process |
| **Charts** | matplotlib (Agg backend) + asyncio executor | No browser dependency; runs in background thread |
| **Scheduled jobs** | APScheduler 3.x | In-process async scheduler for retention/cleanup |
| **Observability** | structlog + PostgreSQL events table | Structured logs; all 5 success metrics measurable |
| **Config / secrets** | pydantic-settings + env vars | 12-factor, Railway native |

---

## Token Usage

Total AI tokens consumed across the project: **~45 million**

| Phase | Sessions | Tokens | Share |
|---|---|---|---|
| **Requirements** (business analysis, system design, architecture, reviews, implementation spec) | 7 sessions | ~8.7M | 19% |
| **Development** (Stage 1–4 implementation, deployment, help command) | 4 sessions | ~36.1M | 81% |

> **Why is development so much larger?**  
> Each development session loaded the full documentation corpus (7 files × long docs) plus growing code files as context on every turn. The architecture document alone is ~15,000 words. By Stage 4, the context per turn was enormous.

**Approximate cost at Sonnet 4.6 pricing:** ~$40–50 USD for the full project.

---
## What's not perfect

### 1. Duplicated requirements across architecture.md, system_analysis.md and implementation_spec.md
Could be adjusted by explicitly tell agent not to duplicate info, but give links

### 2. Documents are too big and they are loading  each time
Split documentation into smaller chunks. e.g. each UC in a separate file

### 3. Agent lost focus, start developing small unimportant features
Review requirements generated by afgent

### 4. Challenging to add new functionality, takes time and long circle
Split flows for initial setup and adding functionality.
Implement skills for this flows
Assign chipper LLMs for picking scenery docs

### 5. Sometime I do not functionality, because it's too much to read
Create summaries and split documents

### 6. No testing
Add agents to build test, better ahead before even development


## What Could Be Done Better Next Time

### 1. Self-iterating document loops
The architecture went through 9 manual versions. This could be fully automated: a designer agent drafts, a critic scores, a reviser addresses every mandatory item — looping until score ≥ 45/50 with no human handoffs between versions.

### 2. Always specify the exact output file path upfront
Several sessions required a second message to correct the filename or folder after Claude saved to the wrong place. A single line like `"save to docs/output/architecture_v0.2.md"` in every prompt would eliminate this.

### 3. Explicit scope guard in every prompt
Claude occasionally over-expanded (e.g., launching a full business analysis when only a small update was requested). Opening every prompt with *"Do only X. Do not modify any other files."* prevents scope creep before it starts.

### 4. Batch development stages
Stages 2, 3, and 4 were sequential manual sessions. A single prompt like *"implement stages 2–4 from the plan, run tests after each, commit per stage, stop on first failure"* would have collapsed three sessions into one.

### 5. Context compression earlier
By Stage 4, each turn loaded ~15,000 words of documentation that the code didn't need. Keeping a short 1-page architecture summary for development sessions — separate from the full spec — would cut input tokens by ~60% and speed up responses.

### 6. Define abbreviations upfront in every prompt
Claude used `JD` without defining it in one session, causing confusion. A style rule of *"no abbreviations unless defined on first use"* in CLAUDE.md would eliminate this class of issue.

---

## Project Timeline

| Date | Milestone |
|---|---|
| Mar 15 | Business analysis started |
| Mar 16 | Business analysis complete (v0.6) |
| Mar 17 | System context started |
| Mar 29 | System context complete (v0.8) |
| Apr 1–5 | Architecture design sessions |
| Apr 12 | Architecture finalized (v0.9), implementation spec written |
| Apr 13 | Stage 1 — scaffold, DB models, bot skeleton |
| Apr 14 | Stages 2–4 — all handlers, charts, alerts, persistence |
| Apr 15 | Help command + deployment fixes + this presentation |

**Total wall-clock time:** ~30 days (part-time, evenings)

---

*Built with Claude Code · Sonnet 4.6 · April 2026*
