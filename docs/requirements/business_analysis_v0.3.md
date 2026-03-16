# Business Analysis Document

> **Version:** v0.3
> **Status:** Revised — incorporating review feedback from v0.2 review report
> **Blocking items:** 4 items below (marked **[BLOCKING]**) must be resolved by the stakeholder before system modeling may begin.

---

## 1. Problem Statement

**[Fact]** People who wish to track personal metrics (health, finances, fitness, etc.) are forced to use multiple dedicated applications, each requiring deliberate context-switching and manual navigation.

**[Fact]** Telegram is already an active daily-use communication tool for the target audience.

**[Hypothesis — UNVALIDATED, requires validation before design phase]** The friction of switching to a dedicated tracking app is the primary driver of tracking abandonment — not lack of motivation.

> **Risk note:** This hypothesis is the entire product premise. If the primary driver of abandonment is motivation rather than friction, the product solves the wrong problem. All downstream sections that reference "reducing friction" inherit this unvalidated premise. No evidence, user research, or proxy data has been cited to support it. A validation plan is required (see §9).

**The core problem:** There is no lightweight, low-friction way to log arbitrary personal metrics within a tool users already open dozens of times per day. As a result, tracking is inconsistently maintained or abandoned entirely.

**Who is affected:** Individuals attempting self-directed tracking of health, fitness, or financial data — specifically those with low tolerance for app-switching overhead.

**Measurability gap:** The document does not quantify how often tracking is abandoned, how many users are affected, or what the typical tracking lifecycle looks like before abandonment. This is a data gap.

---

## 2. Business Impact

**[Assumption]** The product is being built as a personal or portfolio project, not a funded commercial venture. No revenue model is mentioned.

**[BLOCKING — U-001]** The stakeholder must confirm project intent: personal/portfolio project, commercial product, or open-source tool. This decision determines how success is defined, what scale planning is needed, and whether legal compliance applies. No downstream success metrics or scale estimates can be finalized without this answer.

**[Hypothesis]** If commercial intent exists, the market is the personal productivity / quantified-self segment, which is competitive and fragmented.

**[Competitive landscape — acknowledged gap]** The document asserts the market is competitive and fragmented but does not name or evaluate competitors. Known incumbent tools include Notion (with bots/integrations), Obsidian (with plugins), dedicated fitness apps, spreadsheet-based tracking, and habit-tracking apps. No differentiation analysis has been conducted. This absence weakens the strategic justification for building a new tool.

**[Opportunity cost — unresolved]** The choice of Telegram as the delivery mechanism has not been validated against alternatives (mobile widget, WhatsApp bot, Notion integration, iMessage shortcut). No evidence confirms the target audience uses Telegram. If the audience is primarily iOS users in North America, Telegram penetration may be too low to support adoption.

**Current cost of inaction:**
- Users continue relying on fragmented tools or abandon tracking altogether
- No consolidated personal data history → no actionable self-insight
- **[Uncertainty]** No data is provided on the size of the affected user base or willingness to adopt a new tool

---

## 3. Stakeholders

| Stakeholder | Role | Interest | Risk Exposure |
|---|---|---|---|
| End User (health tracker) | Primary user | Low-friction logging, data privacy, chart clarity | Data loss, privacy breach |
| End User (expense tracker) | Primary user | Flexible parameter naming, history access | Loss of financial records |
| End User (athlete) | Primary user | Multi-value entries (e.g., `80kg 5reps`), trend visibility | Incorrect parsing of compound entries |
| Bot Owner / Operator | System owner | Stable operation, user isolation, scalability | Service downtime, data leakage between users |
| **Operational Owner / Maintainer** | **[NEW — required]** Infrastructure and operational accountability | Uptime, cost absorption, incident response, maintenance continuity | Unplanned costs, service instability, no accountability path |
| Telegram platform | Infrastructure dependency | N/A | API policy changes, rate limits, bot restrictions |

> **[Open — required]** The Operational Owner role must be assigned to a named individual or team. Who is responsible for uptime, infrastructure cost, maintenance, and incident response? Without this, there is no accountability for service continuity.

---

## 4. Constraints

- **Platform:** Input exclusively via Telegram — no web, mobile app, or other interface
- **Data model:** No predefined categories; user defines parameters freely on first use
- **Multi-tenancy:** Single bot instance, multiple users; data isolation is mandatory
- **[Assumption]** Budget constraint exists (solo/small team project) — no enterprise infrastructure is expected
- **[Assumption]** No regulatory constraint (GDPR, HIPAA) has been identified — **this is a pre-launch blocker** if health or financial data is stored (see Risks §7)

**Out-of-scope items with rationale:**

| Out-of-Scope Item | Rationale |
|---|---|
| ML predictions / trend inference | Requires labelled training data and model infrastructure not available in a solo/portfolio project at this stage; adds complexity without validating core value proposition first |
| Multi-language support | Adds NLP complexity disproportionate to the expected initial user base, which is assumed to be a single language cohort; deferred pending user research |
| Voice input | Requires speech-to-text integration adding external API dependency; not aligned with keyboard-first Telegram usage patterns |
| External API integrations (e.g., fitness wearables) | Significantly increases scope and maintenance burden; the core value prop is manual low-friction input, not data aggregation |

> If any out-of-scope item turns out to be expected by target users, the scope boundary must be renegotiated before system design.

---

## 5. Success Metrics

> **[BLOCKING — U-005]** All metric targets below are undefined. Metrics without targets cannot determine success or failure. The stakeholder must assign concrete target values before system modeling. This is a hard block on proceeding.

**Active user definition — required for retention measurement:**

> **[BLOCKING — U-006]** "Active user" is undefined. The retention metric is unmeasurable without a definition. Proposed definition (pending stakeholder confirmation): *a user who has submitted at least one successfully parsed entry in the measurement window.* Stakeholder must confirm or revise this definition.

| Metric | Definition | Target                | Measurement Method |
|---|---|-----------------------|---|
| Tracking retention | % of active users still logging after 14 days | >40%                  | Count of active users with entries in days 8–14 |
| Data input success rate | % of free-text entries correctly parsed and stored | >85%                  | Parsed entries / total entries received |
| Feature adoption — charts | % of active users who request at least one chart | >25%                  | Chart command invocations / active users |
| Alert delivery accuracy | Threshold alerts fired correctly vs. expected | >95%                  | Manual or automated test log review |
| User data isolation integrity | Zero incidents of cross-user data visibility | 100% — non-negotiable | Audit log review, test cases |

---

## 6. Assumptions

1. **Users are already Telegram users.**
   - *Why it exists:* The bot is exclusively Telegram-based.
   - *If false:* Adoption ceiling is defined by Telegram penetration in the target market — product fails if users are not on Telegram.

2. **Free-text entry is sufficient for capturing user intent without structured forms.**
   - *Why it exists:* Convenience is the core value proposition.
   - *If false:* Ambiguous or inconsistently formatted entries will result in parsing failures and user frustration, undermining the core value.

3. **Users will define their own parameter names consistently over time.**
   - *Why it exists:* The system auto-creates parameters on first entry.
   - *If false:* Users will accumulate duplicate/misspelled parameters (e.g., `mood`, `Mood`, `moood`) and history will be fragmented.

4. **A single Telegram bot can scale to the anticipated user volume without architectural changes.**
   - *Why it exists:* No scaling or infrastructure scope is mentioned.
   - *If false:* Performance degradation or rate-limit violations under load.

5. **No regulatory compliance is required for stored personal/health/financial data.**
   - *Why it exists:* No mention of compliance requirements in the document.
   - *If false:* Legal exposure depending on jurisdiction (GDPR, HIPAA analog, etc.) — **see Risk R-006, which is a pre-launch blocker.**

6. **Users accept that Telegram mediates all access to their data.**
   - *Why it exists:* No export, web access, or backup mechanism is in scope.
   - *If false:* Users who lose Telegram access lose all their tracking history — no recovery path exists.
   - *Acceptance status:* **Pending stakeholder sign-off** — this risk cannot be accepted by the analyst alone (see Risk R-005).

---

## 7. Risks

> **Risk acceptance policy:** Risk acceptance decisions marked **[Pending stakeholder sign-off]** must be explicitly confirmed by the stakeholder in writing. They cannot be defaulted by the analyst.

| ID | Risk | Impact | Probability | Mitigation Strategy |
|---|---|---|---|---|
| R-001 | **[BLOCKING]** Core friction hypothesis is wrong — abandonment is driven by motivation, not friction | Critical — product solves the wrong problem | Medium — hypothesis is entirely unvalidated | Conduct user research before proceeding to system design (see §9 — Hypothesis Validation Plan) |
| R-002 | Free-text parsing ambiguity causes incorrect data storage | High — corrupts user history | High — natural language is inherently ambiguous | Needs a defined parsing strategy and explicit error-response contract (open question Q-003) |
| R-003 | Parameter name collision / duplicates per user | Medium — fragmented history | High — users are inconsistent typers | Deduplication or alias mechanism required; not in scope yet |
| R-004 | Telegram API policy change restricts bot behavior | High — full service disruption | Low–Medium | No mitigation in scope; acknowledged dependency |
| R-005 | Cross-user data leak due to implementation error | Critical — trust destruction | Low (if built carefully) | Strict user isolation requirement must be enforced and tested; 100% target in metrics |
| R-006 | **[PRE-LAUNCH BLOCKER]** No data export → total data loss on account deletion | Medium — user data unrecoverable | Medium | Risk acceptance **pending stakeholder sign-off**. Users must be explicitly informed of this limitation before onboarding. Cannot be accepted by analyst alone. |
| R-007 | **[PRE-LAUNCH BLOCKER]** GDPR / data privacy non-compliance | High — legal liability | Medium if EU users or health/financial data involved | **Legal review must be completed before system design begins.** Owner: [to be assigned]. Deadline: [to be assigned]. Resolution condition: written legal clearance or confirmed scope exclusion of EU users and sensitive data categories. This is not a deferred concern — it is a blocking condition. |
| R-008 | No operational owner defined | Medium — service instability, no accountability | Medium | Assign an operational owner before launch (see §3) |

---

## 8. Open Questions

**Blocking (must be resolved before system modeling):**

1. **[BLOCKING]** Is there a defined monetization model, or is this a personal/portfolio project, or open-source? (Affects how success is measured, what scale matters, and whether compliance applies.) — *U-001*
2. **[BLOCKING]** What are the concrete target values for each success metric? (Metrics without targets cannot determine success.) — *U-005*
3. **[BLOCKING]** What is the definition of "active user" for retention measurement? — *U-006*
4. **[BLOCKING]** Who is the operational owner responsible for uptime, infrastructure cost, maintenance, and incident response?

**High priority (inform system design):**

5. What is the expected number of users at launch and at steady state? (Affects isolation and scale requirements.) — *U-002*
6. Has any user research been conducted to validate that friction — not motivation — is the primary driver of tracking abandonment? — *U-003*
7. Has any user research been conducted to validate Telegram as the preferred channel for the target audience? — *U-003*
8. Are there any regulatory environments (EU users → GDPR; health data → HIPAA analog) where the bot may be used? — *U-004*

**Design-level (can be resolved in parallel with early design):**

9. What happens when a user sends an entry the bot cannot parse — is there an error response contract?
10. What are the data retention policies? How long is user history stored? Can users export their data?
11. Does the stakeholder explicitly accept the risk that users have no data export or recovery path (R-006)?

---

## 9. Hypothesis Validation Plan

> **This section is new in v0.3, addressing the mandatory revision to validate the core hypothesis.**

**Hypothesis to validate:** "The friction of switching to a dedicated tracking app is the primary driver of tracking abandonment — not lack of motivation."

**Minimum validation required before system design:**

| Validation Method | Description | Minimum Sample | Acceptable Evidence |
|---|---|---|---|
| User interviews | 5–10 structured interviews with people who have tried and abandoned personal tracking tools | 5 users | Majority cite friction/context-switching (not motivation loss) as primary reason for abandonment |
| Survey | Short-form survey targeting the expected demographic | 20+ responses | > 50% identify convenience/friction as primary barrier |
| Proxy data | Reference published research or public datasets on habit-tracking abandonment patterns | N/A | At least one credible source supporting the friction hypothesis |

**If the hypothesis cannot be validated:** The product premise must be reconsidered before committing to a Telegram bot architecture. The opportunity cost of building on the wrong premise is 100% of development investment.

---

## Version

v0.3

## Based on

version v0.2

## Changes Introduced

- Marked 4 blocking items (U-001, U-005, U-006, Operational Owner) with explicit BLOCKING labels
- Added pre-launch blocker designation and owner/deadline/condition requirements to GDPR risk (R-007)
- Added pending stakeholder sign-off requirement to data export risk (R-006) — removed analyst-defaulted acceptance
- Added Operational Owner / Maintainer row to Stakeholders table
- Added competitive landscape acknowledgment and opportunity cost note to Business Impact
- Added rationale column to out-of-scope items in Constraints
- Added "active user" definition requirement to Success Metrics
- Added example target values (as illustrations) to metric targets to clarify what is needed
- Added risk IDs to Risks table for traceability
- Reordered Open Questions into blocking vs. high-priority vs. design-level tiers
- Added §9 Hypothesis Validation Plan (new section)
- Flagged friction hypothesis inheritance throughout document where downstream sections rely on it
- Updated Decision Log and Uncertainty Register

---

## Decision Log

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-001 | Treat unversioned input as v0.1 | No version was specified; analyst assigned initial version | v0.2 | Pending confirmation |
| D-002 | No architecture proposed | Operating rules prohibit technical proposals at this stage | v0.2 | Confirmed |
| D-003 | Escalate GDPR risk to pre-launch blocker | Review identified that deferral without owner/deadline/condition is insufficient for a product that may store health or financial data | v0.3 | Confirmed |
| D-004 | Require stakeholder sign-off for risk R-006 (no data export) | Risk acceptance cannot be defaulted by the analyst; must be a stakeholder decision | v0.3 | Pending stakeholder confirmation |
| D-005 | Add Hypothesis Validation Plan (§9) | Core hypothesis was identified as entirely unvalidated; proceeding without validation is a critical risk | v0.3 | Confirmed |

---

## Uncertainty Register

| ID | Type | Description | Impact | Validation Plan | Status |
|---|---|---|---|---|---|
| U-001 | Business | No monetization model stated | Cannot define commercial success metrics | Ask stakeholder directly | **[BLOCKING — unresolved]** |
| U-002 | Business | No user volume estimate provided | Cannot assess scale requirements | Stakeholder interview | Open |
| U-003 | Factual | No evidence of user research validating Telegram as preferred channel or friction as primary abandonment driver | Core value prop may be misaligned | User survey or interviews — see §9 | **[BLOCKING — unresolved]** |
| U-004 | Business | Regulatory exposure (GDPR, health data) not assessed | Potential legal liability — pre-launch blocker | Legal review required; owner and deadline must be assigned | **[PRE-LAUNCH BLOCKER — unresolved]** |
| U-005 | Business | All success metric targets are undefined | Cannot evaluate success or failure | Stakeholder must assign concrete targets | **[BLOCKING — unresolved]** |
| U-006 | Business | "Active user" is undefined | Retention metric is unmeasurable | Propose definition, confirm with stakeholder | **[BLOCKING — unresolved]** |

---

## Traceability

| Business Goal | Linked Metric | Risk |
|---|---|---|
| Reduce tracking abandonment | Tracking retention at 14 days | R-001: Friction hypothesis may be wrong; R-002: Free-text parsing failures drive churn |
| Enable self-insight through history | Feature adoption — charts | R-006: No export = data locked in platform |
| User data privacy and trust | Cross-user isolation integrity | R-005: Implementation error → critical trust failure; R-007: GDPR non-compliance |
| Service continuity | Operational Owner assignment | R-008: No owner = no accountability for uptime |