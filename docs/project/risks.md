---
doc: PLAN
project: checkpoint_recorder
version: 0.1
status: draft
owner: project-manager
reviewed_by: null
score: null
activities: []
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: arch, version: 0.1}
updated: 2026-04-26
tags: [project-docs, risks]
---

# Risk Register

Risks inherited from [[brd|BRD]] (RISK1–RISK8) plus architecture and delivery risks (RISK9–RISK11).

**Probability scale:** Low / Medium / High
**Impact scale:** Low / Medium / High / Critical

| ID | Risk | Category | Probability | Impact | Status | Owner | Mitigation | Residual |
|---|---|---|---|---|---|---|---|---|
| RISK1 | Core friction hypothesis wrong — tracking abandonment driven by motivation, not app-switching friction | Business | Medium | High | **Accepted** | Operator | Treat as project premise; monitor tracking retention >40% target in production; below target → revisit hypothesis | If hypothesis wrong, product may not achieve retention goals |
| RISK2 | Free-text parsing ambiguity causes incorrect immutable entry storage | Technical | High | High | **Mitigated** | Operator | ParseAttempt fallback for ambiguous inputs (FR5, BR3); compensating delete prevents dangling records (ADR-009) | ~15% incorrect entries at 85% parse accuracy; entry immutability amplifies over time |
| RISK3 | Metric name collision / near-duplicates fragment user history | Technical | High | Medium | **Accepted** | Operator | Near-duplicate detection deferred; DB UniqueConstraint (ADR-011) prevents exact duplicates; users informed at onboarding | Users with inconsistent naming will accumulate fragmented time series |
| RISK4 | Telegram API policy change restricts bot behavior | External | Low–Medium | High | **Accepted** | Operator | No in-scope mitigation; accepted platform dependency | Full service disruption on policy change |
| RISK5 | Cross-user data leak due to implementation error | Technical | Low | Critical | **Mitigated** | Operator | Repository-layer mandatory user_id scoping (ADR-005); integration tests with mismatched user_id required | Requires correct implementation — not a structural guarantee against all coding errors |
| RISK6 | No data export → total data loss on account deletion or Telegram access loss | Business | Medium | Medium | **Accepted** | Operator | Users informed at onboarding (BR11); 1-year retention + 72h grace period provide partial mitigation | Users who lose Telegram access lose their data |
| RISK7 | GDPR / raw_input residual personal data exposure | Compliance | Low–Medium | Medium | **Mitigated** | Operator | No identity fields stored (BR5); raw_input purged on account/metric deletion (NFR15); users informed (BR11); SU-008 accepted for portfolio scope | raw_input may contain health/financial data; no formal legal assessment done |
| RISK8 | Single operator bus factor — unavailability halts all operational roles | Business | Medium | Medium | **Accepted** | Operator | AI agent assistance reduces per-task burden; acceptable for portfolio scope (D-005 in BRD) | Any operator unavailability = no incident response |
| RISK9 | Supabase free tier connection limits (~60 simultaneous) exceeded | Technical | Low | Medium | **Monitored** | Operator | ≤20 concurrent users well within limit; SQLAlchemy connection pool size configurable | If bot usage scales beyond cohort, connection pool must be tuned |
| RISK10 | Railway free tier sleep-on-idle causes bot downtime | Technical | Low–Medium | Medium | **Mitigated** | Operator | Configure "always on" on Railway before M4 completion; affects uptime SLO (NFR4 ≥95%) | Must be confirmed active in production; free tier sleep = bot unresponsive |
| RISK11 | NLP confidence threshold miscalibrated — too low (false auto-parses) or too high (excessive ParseAttempts) | Technical | Medium | High | **Monitored** | Operator | Start at 0.7 (configurable env var); tune from production `parse_outcome_event` data; trigger review if auto-parse error rate >15% | Core >85% parse success rate target (NFR9) at risk until threshold is tuned |

## Risk summary by category

| Category | Count | Highest impact |
|---|---|---|
| Business | 3 | RISK1 (High), RISK6 (Medium), RISK8 (Medium) |
| Technical | 5 | RISK2 (High), RISK5 (Critical), RISK11 (High) |
| External | 1 | RISK4 (High) |
| Compliance | 1 | RISK7 (Medium) |
| **Total** | **11** | **RISK5 (Critical — mitigated)** |

## Top 3 active risks requiring monitoring

1. **RISK2** (Parse accuracy) — monitor `parse_success_rate` in Observability; alert if falls below 85%.
2. **RISK11** (NLP threshold miscalibration) — tune confidence threshold in first 2 weeks of production; review if parse error rate exceeds 15%.
3. **RISK10** (Railway sleep-on-idle) — verify "always on" configuration before declaring M4 complete.
