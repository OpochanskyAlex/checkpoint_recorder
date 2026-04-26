# Business Analysis Document

> **Version:** v0.5
> **Status:** All open questions resolved — ready for system design
> **Blocking items:** None

---

## 1. Problem Statement

**[Fact]** People who wish to track personal metrics (health, finances, fitness, etc.) are forced to use multiple dedicated applications, each requiring deliberate context-switching and manual navigation.

**[Fact]** Telegram is already an active daily-use communication tool for the target audience.

**[Stakeholder Statement — accepted as project premise, no validation planned]** The friction of switching to a dedicated tracking app is the primary driver of tracking abandonment — not lack of motivation.

> **Note:** The stakeholder has explicitly accepted this as a working premise for the project rather than a hypothesis requiring research validation. This constitutes a conscious business risk accepted by the project owner. The premise is recorded here for traceability — if it proves incorrect, the product design may need to be reconsidered.

**The core problem:** There is no lightweight, low-friction way to log arbitrary personal metrics within a tool users already open dozens of times per day. As a result, tracking is inconsistently maintained or abandoned entirely.

**Who is affected:** Individuals attempting self-directed tracking of health, fitness, or financial data — specifically those with low tolerance for app-switching overhead.

**Measurability gap:** The document does not quantify how often tracking is abandoned across the general population. For this project, success is scoped to the stakeholder's own usage and a small initial cohort (see §5).

---

## 2. Business Impact

**[Confirmed — U-001]** This is an educational and portfolio project. There is no monetization intent at this stage. Success is defined in terms of personal learning, functional product delivery, and demonstrated portfolio value — not revenue or commercial growth.

> Commercial-intent analysis (competitive landscape, market sizing, willingness-to-pay) is not applicable at this stage. The notes are retained below for reference in case project intent changes.

**[Reference — competitive landscape, not blocking]** Known incumbent tools in the personal-tracking space include Notion (with bots/integrations), Obsidian (with plugins), dedicated fitness apps, spreadsheet-based tracking, and habit-tracking apps. This project differentiates by embedding tracking directly inside an existing messaging tool, reducing the activation threshold.

**[Stakeholder Statement — Telegram platform choice]** The choice of Telegram as the delivery mechanism is accepted as a project premise. No comparative platform analysis is required.

**Scope of impact:**
- Stakeholder (primary user) gains a consolidated, low-friction personal tracking history within an existing daily-use tool
- Small initial cohort (target: ~10 first-touch users) can evaluate the tool
- Success at portfolio level: functional, deployed bot demonstrating NLP parsing, multi-tenancy, and data visualization

**Estimated user volume — confirmed (U-002):**
- Target user volume: approximately **10 users**, each tracking approximately **10 metrics**
- This equates to ~100 active metric time series at steady state
- Scale implications: minimal infrastructure requirements; a single-instance deployment is sufficient

---

## 3. Stakeholders

| Stakeholder | Role | Interest | Risk Exposure |
|---|---|---|---|
| End User (health tracker) | Primary user | Low-friction logging, data privacy, chart clarity | Data loss, privacy breach |
| End User (expense tracker) | Primary user | Flexible parameter naming, history access | Loss of financial records |
| End User (athlete) | Primary user | Multi-value entries (e.g., `80kg 5reps`), trend visibility | Incorrect parsing of compound entries |
| Bot Owner / Operator | System owner | Stable operation, user isolation, scalability | Service downtime, data leakage between users |
| Operational Owner / Maintainer | Single person operating all roles, assisted by AI agents | Uptime, cost absorption, incident response, maintenance continuity | Capacity overload (single point of failure for all operational responsibilities) |
| Telegram platform | Infrastructure dependency | N/A | API policy changes, rate limits, bot restrictions |

---

## 4. Constraints

- **Platform:** Input exclusively via Telegram — no web, mobile app, or other interface
- **Data model:** No predefined categories; user defines parameters freely on first use
- **Multi-tenancy:** Single bot instance, multiple users; data isolation is mandatory
- **Budget:** Solo project; no enterprise infrastructure. Lightweight, low-cost deployment.
- **Privacy by design (confirmed — U-004):** The system stores only a de-personalized internal user ID. No personal data (name, email, phone number, Telegram username) is persisted. All stored records are keyed to an opaque internal identifier only.
- **Team:** Single person, multiple roles, AI-agent assisted
- **Parse failure behavior (confirmed — Q-009):** When the system cannot automatically identify the target metric from a free-text entry, it does not silently fail or discard the input. Instead, it presents the user with a manual selection prompt listing candidate metrics to choose from. This is a required fallback for all ambiguous or unrecognized input.
- **Data retention policy (confirmed — Q-010):**
  - *Guaranteed:* User data is retained for a minimum of **1 year after the user's last interaction** with the service.
  - *Actual practice:* Data is stored for the **lifetime** of the service beyond the guaranteed window, unless the user explicitly deletes their account.
  - This policy must be communicated to users at onboarding.

- **Command discoverability:** The system must provide in-context documentation of all available commands via a `/help` command. This is required to reduce user confusion and support self-service onboarding without external documentation.

**Out-of-scope items with rationale:**

| Out-of-Scope Item | Rationale |
|---|---|
| ML predictions / trend inference | Requires labelled training data and model infrastructure not available in a solo/portfolio project at this stage; adds complexity without validating core value proposition first |
| Multi-language support | Adds NLP complexity disproportionate to the expected initial user base, assumed to be a single-language cohort; deferred until scale justifies it |
| Voice input | Requires speech-to-text integration adding an external API dependency; not aligned with keyboard-first Telegram usage patterns |
| External API integrations (e.g., fitness wearables) | Significantly increases scope and maintenance burden; core value prop is manual low-friction input, not data aggregation |
| Data export | Explicitly out of scope; risk accepted by stakeholder (see R-006) |

---

## 5. Success Metrics

**Business success threshold (stakeholder-defined):**
- **Minimum success:** 2 active users (by the definition below)
- **First-touch target:** approximately 10 users who try the bot at least once

**Active user definition — confirmed (U-006):**

A **tracking metric** is considered *active* if the user has not missed it more than once across the last 5 periods of that metric's own periodicity.

- Each metric has an individual periodicity **defined by the user at metric creation time** (confirmed — Q-011)
- Periodicity examples: daily, weekly — set once during the metric creation flow, not inferred by the system
- Active threshold: ≥ 4 entries out of the last 5 periods
- Example (weekly metric): active if the user logged it in at least 4 of the last 5 weeks
- Example (daily metric): active if the user logged it on at least 4 of the last 5 days

An **active user** is any user who has at least one active metric.

> **Alignment note:** The tracking retention metric below uses a 14-day window, which aligns with daily-period metrics. For weekly-period metrics, the equivalent window is 5 weeks. Measurement tooling must account for per-metric periodicity.

| Metric | Definition | Target | Measurement Method |
|---|---|---|---|
| Tracking retention | % of active users still logging after 14 days (daily metrics) or 5 periods (per metric's own period) | > 40% | Count of active users with entries in days 8–14 (or 4 of last 5 periods) |
| Data input success rate | % of free-text entries correctly parsed and stored | > 85% | Parsed entries / total entries received |
| Feature adoption — charts | % of active users who request at least one chart | > 25% | Chart command invocations / active users |
| Alert delivery accuracy | Threshold alerts fired correctly vs. expected | > 95% | Manual or automated test log review |
| User data isolation integrity | Zero incidents of cross-user data visibility | 100% — non-negotiable | Audit log review, test cases |

---

## 6. Assumptions

1. **Users are already Telegram users.**
   - *Why it exists:* The bot is exclusively Telegram-based.
   - *If false:* Adoption ceiling is defined by Telegram penetration in the target market — product fails if users are not on Telegram.

2. **Free-text entry is sufficient for capturing user intent without structured forms.**
   - *Why it exists:* Convenience is the core value proposition.
   - *If false:* Ambiguous or inconsistently formatted entries will result in parsing failures; the manual selection fallback (§4) mitigates but does not eliminate this risk.

3. **Users will define their own parameter names consistently over time.**
   - *Why it exists:* The system auto-creates parameters on first entry.
   - *If false:* Users will accumulate duplicate/misspelled parameters (e.g., `mood`, `Mood`, `moood`) and history will be fragmented.

4. **A single Telegram bot instance can serve the anticipated user volume without architectural changes.**
   - *Why it exists:* Target volume is ~10 users / ~100 metric time series.
   - *If false:* Performance degradation or rate-limit violations under load — unlikely at this scale.

5. **[Resolved — U-004] No regulatory compliance is required because no personal data is stored.**
   - *Stakeholder decision:* System stores only a de-personalized internal ID. No personal data (name, contact, etc.) is persisted.
   - *Residual risk:* Telegram platform itself holds user identity. The bot has no control over what Telegram retains. This risk is accepted and out of scope for this product.

6. **Users accept that Telegram mediates all access to their data and that no export mechanism exists.**
   - *Stakeholder decision:* Accepted. No export is planned. Users will be informed of this limitation and the data retention policy at onboarding.
   - *If false:* Users who lose Telegram access lose their tracking history — no recovery path exists within the 1-year guarantee window.

---

## 7. Risks

> **Risk acceptance policy:** Risks marked **[Accepted by stakeholder]** have been explicitly confirmed by the project owner.

| ID | Risk | Impact | Probability | Mitigation Strategy |
|---|---|---|---|---|
| R-001 | Core friction hypothesis is wrong — abandonment is driven by motivation, not friction | High — product solves the wrong problem | Low–Medium (accepted as premise for portfolio scope) | **[Accepted by stakeholder]** Treated as a project premise. If the product fails to retain users, this hypothesis is the first area to re-examine. |
| R-002 | Free-text parsing ambiguity causes incorrect data storage | High — corrupts user history | High — natural language is inherently ambiguous | **Partially mitigated:** when automatic parsing fails, system presents manual selection prompt to the user (confirmed behavior — Q-009). Parsing strategy and full error-response contract to be defined in system design. |
| R-003 | Parameter name collision / duplicates per user | Medium — fragmented history | High — users are inconsistent typers | Deduplication or alias mechanism required; to be addressed in system design |
| R-004 | Telegram API policy change restricts bot behavior | High — full service disruption | Low–Medium | Accepted dependency; no mitigation in scope |
| R-005 | Cross-user data leak due to implementation error | Critical — trust destruction | Low (if built carefully) | Strict user isolation must be enforced and tested; 100% target in metrics |
| R-006 | No data export → total data loss on account deletion | Medium — user data unrecoverable | Medium | **[Accepted by stakeholder]** No export is in scope. Users will be explicitly informed at onboarding. 1-year retention guarantee provides a recovery window if Telegram account is restored. |
| R-007 | GDPR / data privacy exposure | Low — significantly mitigated by design | Low | **[Mitigated by design]** System stores only de-personalized internal IDs; no personal data retained. Residual risk: Telegram holds user identity outside this system's control. |
| R-008 | Single operational owner creates bus-factor risk | Medium — any unavailability halts operations | Medium (solo project) | **[Accepted by stakeholder]** AI agent assistance reduces per-task burden. Acceptable risk for a portfolio project. |

---

## 8. Open Questions

All open questions are resolved.

| # | Question | Resolution |
|---|---|---|
| Q-001 | Monetization model? | Educational/portfolio project. No monetization. |
| Q-002 | Metric targets? | Defined in §5: >40%, >85%, >25%, >95%, 100% |
| Q-003 | Active user definition? | Defined in §5: at least one metric active (≥4/5 periods) |
| Q-004 | Operational owner? | Single person, AI-agent assisted |
| Q-005 | Expected user volume? | ~10 users, each tracking ~10 metrics |
| Q-006 | User research on friction hypothesis? | Accepted as project premise — no research planned |
| Q-007 | Telegram platform validation? | Accepted as project premise — no comparative research planned |
| Q-008 | Regulatory environment? | Mitigated by design — no personal data stored |
| Q-009 | Parse failure behavior? | System presents manual selection prompt when automatic parsing fails |
| Q-010 | Data retention policy? | 1 year guaranteed after last interaction; lifetime storage in practice |
| Q-011 | How are metric periodicities set? | User defines periodicity during metric creation flow |

---

## 9. Hypothesis Statement

> **Recorded in v0.4, unchanged in v0.5.**

**Statement accepted:** "The friction of switching to a dedicated tracking app is the primary driver of tracking abandonment — not lack of motivation."

**Accepted by:** Project owner / stakeholder
**Basis:** Personal experience and project intent (educational/portfolio)
**Risk accepted:** If this premise is incorrect, the product may not achieve its retention targets. For a portfolio project at this scale, the stakeholder has judged the research cost to be disproportionate to the risk.

**Residual signal to watch:** If tracking retention falls below the 40% target during live operation, the motivation hypothesis should be reconsidered as an alternative explanation.

---

## Version

v0.6

## Based on

v0.5

## Changes Introduced in v0.6

- Added command discoverability constraint (§4): system must provide a `/help` command listing all available commands with descriptions
- Decision Log: D-015 added

## Changes Introduced in v0.5

- Resolved Q-009: Parse failure behavior confirmed — system presents manual selection prompt; §4 constraint added, R-002 mitigation updated
- Resolved Q-010: Data retention policy confirmed — 1 year guaranteed after last interaction, lifetime in practice; §4 constraint added, assumption 6 and R-006 updated to reference retention window
- Resolved Q-011: Metric periodicity is set by the user during metric creation; §5 active user definition updated
- All open questions are now resolved; §8 "Still open" section removed

---

## Decision Log

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-001 | Treat unversioned input as v0.1 | No version was specified; analyst assigned initial version | v0.2 | Confirmed |
| D-002 | No architecture proposed | Operating rules prohibit technical proposals at this stage | v0.2 | Confirmed |
| D-003 | Escalate GDPR risk to pre-launch blocker | Review identified deferral without owner/deadline/condition as insufficient | v0.3 | Superseded by D-008 |
| D-004 | Require stakeholder sign-off for no-data-export risk | Risk acceptance cannot be defaulted by the analyst | v0.3 | Confirmed — sign-off received in v0.4 |
| D-005 | Add Hypothesis Validation Plan | Core hypothesis was entirely unvalidated | v0.3 | Superseded by D-009 |
| D-006 | Project intent confirmed as educational/portfolio | Stakeholder response to U-001 | v0.4 | Confirmed |
| D-007 | Privacy by design: store only de-personalized internal IDs | Stakeholder response to U-004; eliminates GDPR/HIPAA personal-data risk | v0.4 | Confirmed |
| D-008 | Downgrade GDPR risk from pre-launch blocker to residual | Resolved by D-007; no personal data stored | v0.4 | Confirmed |
| D-009 | Accept friction hypothesis as project premise, no validation planned | Stakeholder decision; portfolio scope makes research cost disproportionate | v0.4 | Confirmed |
| D-010 | Accept no-export risk on behalf of users | Stakeholder decision; users to be informed at onboarding | v0.4 | Confirmed |
| D-011 | Single person with AI agents as operational owner | Stakeholder response to Q-004 | v0.4 | Confirmed |
| D-012 | Parse failure uses manual selection fallback | Stakeholder response to Q-009; preserves data integrity over silent failure | v0.5 | Confirmed |
| D-013 | Data retention: 1 year guaranteed, lifetime in practice | Stakeholder response to Q-010 | v0.5 | Confirmed |
| D-014 | Metric periodicity set at creation time by user | Stakeholder response to Q-011; periodicity is explicit, not inferred | v0.5 | Confirmed |
| D-015 | `/help` command is a required feature for in-context discoverability | Without self-service documentation, users unfamiliar with commands will abandon the bot rather than experiment; reduces onboarding friction | v0.6 | Confirmed |

---

## Uncertainty Register

| ID | Type | Description | Impact | Resolution | Status |
|---|---|---|---|---|---|
| U-001 | Business | No monetization model stated | Cannot define commercial success metrics | Educational/portfolio project confirmed | **[Resolved — v0.4]** |
| U-002 | Business | No user volume estimate provided | Cannot assess scale requirements | ~10 users, ~10 metrics each | **[Resolved — v0.4]** |
| U-003 | Factual | No evidence validating Telegram channel or friction hypothesis | Core value prop may be misaligned | Accepted as project premise by stakeholder | **[Resolved — v0.4]** |
| U-004 | Business | Regulatory exposure (GDPR, health data) not assessed | Potential legal liability | Mitigated by design: only de-personalized IDs stored | **[Resolved — v0.4]** |
| U-005 | Business | All success metric targets undefined | Cannot evaluate success or failure | Targets confirmed (see §5) | **[Resolved — v0.4]** |
| U-006 | Business | "Active user" undefined | Retention metric unmeasurable | Definition confirmed: user with ≥1 active metric (≥4/5 periods filled) | **[Resolved — v0.4]** |

---

## Traceability

| Business Goal | Linked Metric | Risk |
|---|---|---|
| Reduce tracking abandonment | Tracking retention (>40% at 14 days / 5 periods) | R-001: Friction hypothesis may be wrong; R-002: Parsing failures mitigated by manual selection fallback |
| Enable self-insight through history | Feature adoption — charts (>25%) | R-006: No export accepted; 1-year retention guarantee limits data-loss window |
| User data privacy and trust | Cross-user isolation integrity (100%) | R-005: Implementation error → critical trust failure; R-007: Telegram holds user identity (residual) |
| Service continuity | Operational Owner (single person + AI agents) | R-008: Single-person bus factor accepted |
| Portfolio demonstration | All metrics at target | R-003: Parameter collisions fragment history |