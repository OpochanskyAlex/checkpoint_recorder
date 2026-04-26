---
doc: OVERVIEW
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [logging, management, analytics, alerting, account, discovery, General]
refs: []
updated: 2026-04-26
tags: [project-docs, overview]
---

# Checkpoint Recorder

A Telegram bot for personal metric tracking. Users send free-text messages (`mood 7`, `bench press 80kg 5reps`, `fuel 40L`) and the bot stores, visualizes, and alerts on any self-defined metric — all without leaving Telegram. Designed for people who abandon dedicated tracking apps due to the friction of switching context. Built as a portfolio project demonstrating NLP parsing, multi-tenancy, async Python architecture, and structured observability.

## Status

| Doc | Version | Status | Last review score |
|---|---|---|---|
| [[brd\|Business Requirements]] | 0.1 | draft | — |
| [[srs\|System Requirements]] | — | — | — |
| [[overview\|Architecture Overview]] | — | — | — |
| [[plan\|Project Plan]] | — | — | — |

## User Activities

Canonical activity taxonomy used in `@` tags across all requirements. Owned by business-analyst.

- **@logging** — free-text data entry, metric auto-creation on first entry, parse disambiguation, compound multi-value entries, late categorization of deferred entries
- **@management** — metric catalog management (list, archive, reactivate, delete), alert listing and deletion
- **@analytics** — trend chart generation, history viewing, period comparison
- **@alerting** — alert configuration, threshold evaluation, notification dispatch, alert re-arming
- **@account** — user registration, onboarding, account deletion with grace period, account restoration
- **@discovery** — /help command, command discoverability, self-service onboarding
- **@General** — cross-cutting concerns (per-user data isolation, data retention, availability, observability)

## Business

- **BRD:** [[brd|Business Requirements]]
- **User stories by activity:**
  - **@logging:** [[us-1-log-metric|US1 Log a metric in free text]] · [[us-2-resolve-ambiguous|US2 Resolve an ambiguous entry]]
  - **@management:** [[us-3-manage-metrics|US3 Manage metric catalog]]
  - **@analytics:** [[us-4-view-charts|US4 View trend charts]]
  - **@alerting:** [[us-5-set-alerts|US5 Set and manage threshold alerts]]
  - **@account:** [[us-6-manage-account|US6 Manage account]]
  - **@discovery:** [[us-7-discover-commands|US7 Discover available commands]]
  - **@General:** <none>

## System

- **SRS:** [[srs|System Requirements]]
- **Use case diagram:** [[use-case-diagram]]
- **Use cases by activity:**
  - **@account:** [[uc-1-onboard|UC1 Onboard]] · [[uc-12-delete-account|UC12 Delete account]] · [[uc-13-restore-account|UC13 Restore account]]
  - **@logging:** [[uc-2-log-metric|UC2 Log metric]] · [[uc-3-resolve-ambiguous|UC3 Resolve ambiguous entry]] · [[uc-11-categorize-deferred|UC11 Categorize deferred entry]]
  - **@management:** [[uc-4-create-metric|UC4 Create metric]] · [[uc-5-list-metrics|UC5 List metrics]] · [[uc-6-archive-metric|UC6 Archive/reactivate]] · [[uc-7-delete-metric|UC7 Delete metric]] · [[uc-15-manage-alerts|UC15 Manage alerts]]
  - **@alerting:** [[uc-8-configure-alert|UC8 Configure alert]] · [[uc-9-rearm-alert|UC9 Re-arm alert]]
  - **@analytics:** [[uc-10-request-chart|UC10 Request chart]]
  - **@discovery:** [[uc-14-request-help|UC14 Request help]]
  - **@General:** <none>

## Architecture

- **Overview:** [[overview|Architecture Overview]]
- **ADRs:**
  - [[adr-001-monolith|ADR-001 Single-process monolith]] · [[adr-002-telegram-gateway|ADR-002 Webhook mode]] · [[adr-003-alert-evaluation|ADR-003 Post-commit alert eval]]
  - [[adr-004-metric-activity-status|ADR-004 MetricActivityStatus lazy]] · [[adr-005-user-isolation|ADR-005 Repository-layer isolation]] · [[adr-006-chart-two-phase|ADR-006 Two-phase chart]]
  - [[adr-007-cascade-deletion|ADR-007 Cascade delete atomicity]] · [[adr-008-alert-archived|ADR-008 Alert on Archived suspension]] · [[adr-009-parse-attempt-atomicity|ADR-009 ParseAttempt atomicity]]
  - [[adr-010-chart-coroutine|ADR-010 Chart fire-and-forget coroutine]] · [[adr-011-metric-name-uniqueness|ADR-011 Metric name uniqueness]] · [[adr-012-technology-stack|ADR-012 Technology stack]]
- **Diagrams folder:** `architecture/diagrams/`

## Project Plan

- **Plan:** [[plan|Project Plan]] — 4 milestones, 13 tasks, T-shirt + token sizing
- **Risks:** [[risks|Risk Register]] — 11 risks across business, technical, external, compliance categories

## Open Questions (aggregated)

_(None at BRD stage — all source questions resolved.)_

## Reading Order

For first-time readers:
1. This file
2. [[brd]] — what's needed and why
3. [[srs]] — what the system does and to what standard
4. [[use-case-diagram]] — who interacts with what
5. Specific [[us-1-log-metric|US]] or UC files as needed
6. [[overview|architecture overview]] — how it's built
7. [[plan]] if project plan was produced
