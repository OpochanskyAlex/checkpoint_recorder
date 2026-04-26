---
doc: ADR
id: ADR-002
title: Telegram Gateway — webhook mode
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: []
refs:
  - {doc: srs, version: 0.1}
related: [ADR-001, ADR-012]
updated: 2026-04-26
tags: [project-docs, adr]
---

# ADR-002: Telegram Gateway — webhook mode

# Context

The original architecture document (v0.9 AD-2) deferred the polling vs. webhook decision to deployment context. `technology.md` resolved it: Railway PaaS provides a public HTTPS endpoint automatically, eliminating the requirement for polling. This ADR records the resolved decision.

> Source discrepancy D3 (accepted): `architecture.md` AD-2 deferred this choice. `technology.md` resolved to webhook. Accepted as true per stakeholder confirmation.

# Decision

Use aiogram webhook mode. The bot registers its HTTPS webhook URL (Railway-assigned endpoint) at startup. Telegram pushes inbound events to the webhook endpoint. Health proxy: absence of successful webhook deliveries beyond a configured interval triggers Railway health check failure → restart.

# Alternatives Considered

## A1 Long-polling (getUpdates loop)
- Pros: no public HTTPS endpoint required; simpler local development; no webhook registration needed
- Cons: adds ~1s average latency to the entry ack budget; wastes Telegram API calls (constant polling); slightly less efficient at scale
- Why not: webhook is available (Railway provides HTTPS); webhook is strictly better given the infrastructure

## A2 Webhook (chosen)
- Pros: near-zero inbound latency; no polling overhead; Railway provides HTTPS endpoint automatically; push-based (no constant API calls); enables accurate health proxy (absence of events = bot offline)
- Cons: requires stable HTTPS endpoint; Railway must maintain the HTTPS tunnel; webhook registration at startup (one-time network call)
- Why yes: Railway PaaS provides all prerequisites; lower latency; more efficient

# Consequences

## Positive
- Inbound message latency reduced by ~1s vs. polling
- No wasted Telegram API calls
- Railway HTTPS endpoint is automatically provisioned and maintained

## Negative
- Webhook registration at startup: if Telegram API is unreachable at startup, bot cannot register and will not receive messages
- Health proxy depends on Telegram message activity — low-traffic periods may produce false health signals

## Follow-ups
- Implement startup retry for webhook registration with exponential backoff
- Consider a keep-alive mechanism (empty webhook test call) for health checking during low-traffic periods

# NFRs affected

- NFR1 (Entry ack ≤5s): webhook eliminates polling interval latency; entry ack budget fully available for processing
- NFR4 (Uptime ≥95%): webhook absence detection enables proactive Railway health check; polling mode would require a separate health endpoint
