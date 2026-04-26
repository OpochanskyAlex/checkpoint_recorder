# Technology Stack

> **Date:** 2026-04-13
> **Status:** Agreed

---

## Basics

| Concern | Type                           | Choice                                              | Notes                                                  |
|---|--------------------------------|-----------------------------------------------------|--------------------------------------------------------|
| Language | Runtime                        | Python 3.12+                                        |
| Bot framework | Telegram                       | aiogram 3.x                                         | Webhook mode (not polling)                             |
| Bot mode | Telegram                       | Webhook                                             | Railway provides public HTTPS URL                      |
| FSM / ConversationState | Telegram                       | aiogram built-in FSM                                | Persisted via SQLAlchemy storage backend               |
| Hosting platform | Hosting & Infrastructure       | Railway                                             | Handles process supervision, restarts, env vars, HTTPS |
| Process supervisor | Hosting & Infrastructure       | Railway platform                                    | Replaces systemd / Docker                              |
| Database | Database|  Supabase (managed PostgreSQL)                      | Replaces SQLite |
| Async driver | Database| asyncpg                        | Used via SQLAlchemy async engine                    |
| ORM | Database| SQLAlchemy 2.x (async)         |                                                     |
| Migrations | Database| Alembic                        |                                                     |
| Backup / RPO | Database| Supabase managed backups       | Point-in-time recovery; satisfies RPO ≤ 24h (D-013) |


## Application Libraries

| Concern | Choice | Notes |
|---|---|---|
| NLP — metric name matching | rapidfuzz | Fuzzy match against user's metric vocabulary; confidence score maps to SU-002 threshold |
| NLP — numeric/unit extraction | pint + regex | Extracts values like `80kg`, `5 reps`, `120/80` |
| Chart rendering | matplotlib (Agg backend) | Headless PNG generation; offloaded via `asyncio.run_in_executor` |
| Scheduled jobs | APScheduler 3.x | In-process, async; satisfies ≥12h cadence requirement |
| Structured logging / observability | structlog | JSON output to stderr; events stored in PostgreSQL events table |
| Config / secrets | pydantic-settings | Typed config from environment variables; bot token never in source |

