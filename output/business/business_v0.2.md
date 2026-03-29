# Business Analysis Document

## 1. Problem Statement

Personal metric tracking is fragmented across multiple dedicated applications, creating friction that leads to inconsistent logging and eventual abandonment. Individuals who wish to monitor personal parameters — such as health indicators, financial data, or athletic performance — must context-switch between their primary communication tools and separate tracking applications.

This project addresses that friction for a specific, bounded population: the developer and a small, known circle of friends (maximum approximately 100 users), all of whom use Telegram as a primary messaging platform.

The problem manifests as:

- Low logging consistency due to the inconvenience of opening dedicated apps
- No single interface for tracking heterogeneous, user-defined parameters
- Data siloed across unrelated tools with no unified view of trends

The problem is measurable through: user logging frequency per parameter, parameter abandonment rate over time, and the number of distinct parameters a user actively maintains.

**Scope clarification (Fact):** This is a personal portfolio project with dual intent — developer learning and personal utility. It is not a public-facing product and does not target market acquisition.

---

## 2. Business Impact

**Note:** Impact estimates below are framed relative to the actual project context: a personal and portfolio use case at near-zero budget and maximum 100 users. Financial impact in a commercial sense is not applicable.

- **Personal utility value:** The developer and their social circle gain a unified tracking interface within Telegram, eliminating the need for separate apps.
- **Portfolio value (Fact):** The project produces a demonstrable, functional system that the developer can reference as evidence of technical and product capability.
- **Cost of inaction:** Without this tool, users continue with fragmented tracking or abandon tracking altogether. At this scale, the cost is personal inconvenience rather than financial loss.
- **Infrastructure cost (Fact):** Near-zero ongoing operational cost. Free hosting tiers will be used. Some paid services may be used during development only and are not expected to persist.
- **Monetization:** Not applicable. No revenue model is planned or required. This is a deliberate decision, not an open item.
- **Competitive displacement:** Not a project goal. No prior competitive analysis was conducted and none is required. The project exists as a utility for a closed group, not as a market entrant.

---

## 3. Stakeholders

| Stakeholder | Role | Interest | Risk Exposure |
|---|---|---|---|
| Developer / Bot Owner | Builder and operator | Portfolio value, personal utility, system reliability, learning outcomes | Time investment yields no functional system; data isolation failure across users |
| End Users (friends, closed group) | Primary users, max ~100 | Convenient, reliable logging within Telegram; correct data returned | Data loss if history is not preserved; confusion if parse failures are not handled gracefully |
| Telegram Platform | Infrastructure dependency | Platform policy compliance | Bot suspension if Telegram terms of service are violated |

**Note:** No enterprise, organizational, or commercial stakeholders exist. No external investor, sponsor, or paying customer is involved.

---

## 4. Constraints

**Scale (Fact):**
- Maximum anticipated user base is approximately 100 individuals, all personally known to the developer.
- No public launch, onboarding funnel, or user acquisition effort is planned.

**Budget (Fact):**
- Near-zero budget. Free hosting tiers are the operational baseline.
- Paid services used during development are considered temporary and will not contribute to ongoing cost.

**Timeline:**
- Not specified. No deadline has been provided. This remains an open item.

**Input channel (Fact):**
- All user interaction is exclusively through Telegram. No web interface, mobile app, or email fallback is in scope.

**Parameter model (Fact):**
- No predefined categories. Users define all parameters freely via natural free-text input.

**Multi-tenancy (Fact):**
- The bot serves multiple users simultaneously. User data must be fully isolated per Telegram user ID.

**Identity model (Fact):**
- Users are identified solely by their Telegram ID. No names, emails, or additional personal data are collected. Users are effectively anonymous to the system.

**Regulatory:**
- Because no personally identifiable information beyond Telegram ID is collected, and the system serves a closed group of known individuals rather than the general public, formal GDPR obligations are unlikely to apply in a material way. However, this has not been verified with legal counsel.
- Assumption: the scale, anonymity model, and non-commercial nature of this project place it outside the practical enforcement scope of major data privacy regulations. If this assumption is false, additional compliance measures would be required.

**Out of scope (Fact, from input document):**
- External API integrations (fitness trackers, etc.)
- Voice input
- Multi-language support
- ML-based predictions

---

## 5. Success Metrics

**Note:** All targets below are hypotheses. No historical baseline or user research data exists for this project. Validation will occur through direct observation during use by the closed user group.

| Metric | Definition | Target (Hypothesis) | Measurement Method |
|---|---|---|---|
| Developer Learning Outcome | Developer can describe and demonstrate system design decisions made during the project | Achieved by project completion | Self-assessment and portfolio documentation |
| System Functionality | Bot accepts input, stores data, and returns history and chart within Telegram | All core flows functional at launch | Manual testing against defined scenarios |
| User Logging Consistency | Average entries per active user per week during first 30 days | At least 3 entries/week per active user | Server-side log count per Telegram ID per week |
| Parameter Retention Rate | Percentage of created parameters with at least one entry in the past 14 days | Greater than 50% of parameters remain active at 30 days | Count of parameters with recent entries vs. total created |
| Parse Failure Handling | Percentage of failed automatic parses that result in a successful manual categorisation prompt | Greater than 80% of parse failures resolved via manual prompt | Log of parse failure events vs. subsequent successful manual entries |
| User Return Rate | Percentage of users who log data in week 2 after first use | Greater than 40% return in week 2 | Cohort tracking by first-use date |

**Restatement on parse accuracy:** Parse accuracy is not a hard constraint. Automatic parsing failures are acceptable provided the fallback prompt (manual categorisation) successfully captures the intended entry. The metric above tracks fallback resolution, not raw parse accuracy.

---

## 6. Assumptions

1. **Telegram as sole interface is sufficient for this user group.**
   - Why it exists: The developer and their friends already use Telegram daily.
   - If false: Users who do not use Telegram cannot participate. At this scale, non-participation by individuals is acceptable.

2. **Free-text parsing will extract parameter name and value with acceptable frequency; failures are handled gracefully via manual fallback.**
   - Why it exists: Natural language input reduces friction. The stakeholder has confirmed that parse failures are fully acceptable provided a fallback prompt exists.
   - If false: If the fallback prompt itself fails to guide users, entry rates will drop. This is mitigated by the fallback design.

3. **Users are willing to self-define all parameters without predefined templates.**
   - Why it exists: The input document specifies no predefined categories.
   - If false: Users may struggle to begin. This is partially mitigated by the onboarding experience (see Section 8, Onboarding).

4. **Data isolation between users is achievable using Telegram user IDs as the sole identifier.**
   - Why it exists: Telegram IDs are unique per user and accessible to bots without additional registration.
   - If false: Data cross-contamination would be a critical failure. This is a must-hold assumption.

5. **No monetization is required at any stage of this project.**
   - Why it exists: Confirmed by the project owner. This is a deliberate scope decision.
   - If false: The entire project structure would require re-evaluation. Not anticipated.

6. **The user base consists solely of individuals known personally to the developer; no public access is intended.**
   - Why it exists: Confirmed by the project owner.
   - If false: Regulatory, scaling, and security considerations would increase substantially.

7. **Telegram's bot platform policies permit persistent per-user data storage and scheduled alert delivery for this use case.**
   - Why it exists: These are core functional requirements of the system.
   - If false: The entire delivery channel would need to be reconsidered.

8. **Near-zero infrastructure cost is sustainable on free hosting tiers for up to 100 users.**
   - Why it exists: Confirmed budget constraint from project owner.
   - If false: The project may require re-scoping or accepting a small ongoing cost that was not planned.

9. **The onboarding flow (demo parameters with fake historical data, then guided first real parameter entry) is sufficient to orient new users without additional documentation.**
   - Why it exists: Confirmed by the project owner as the intended first-time experience.
   - If false: Users may not understand the system without additional guidance, increasing abandonment before first real use.

---

## 7. Risks

| Risk | Impact | Probability | Mitigation Strategy |
|---|---|---|---|
| Telegram platform policy change or bot suspension | High — entire system becomes unavailable | Low — bot is low-traffic and non-commercial | Monitor Telegram bot API terms; design data layer to be exportable |
| Free hosting tier limitations (rate limits, downtime, storage caps) | Medium — degraded reliability for users | Medium — free tiers have known constraints | Select hosting with sufficient free-tier limits for 100 users; document known limits |
| Parse failure rate too high, fallback prompt confuses users | Medium — users abandon logging | Medium — natural language parsing is inherently imprecise | Invest in clear fallback prompt design; log failure patterns to improve over time |
| Data loss due to lack of backup on free infrastructure | High — users lose historical tracking data | Medium — free tiers may lack redundancy | Implement periodic data export or backup mechanism within free-tier constraints |
| Scope creep beyond portfolio and personal utility intent | Low impact on users, medium impact on developer time | Medium — feature requests from friends are likely | Developer maintains explicit scope boundary; new features evaluated against portfolio and utility value only |
| Onboarding demo data misleads users about system behaviour | Low — users may form incorrect expectations | Low — demo is clearly framed as illustrative | Ensure demo data is visually or contextually distinct from real data |

---

## 8. Open Questions

1. **Timeline:** No deadline has been provided. When does the developer intend to have a functional first version available to the closed user group?

2. **Data backup and export:** Is there a minimum acceptable data retention guarantee for users? What happens to user data if the hosting provider discontinues the free tier?

3. **Onboarding scope:** Is the demo-parameter onboarding flow the only planned onboarding mechanism, or will there be any in-bot help commands or documentation?

4. **Alert mechanism:** Threshold-based alerts were mentioned in the original input. Are alerts still in scope, and if so, what defines a threshold (user-defined, system-defined, or both)?

5. **Telegram policy verification:** Has the developer reviewed current Telegram bot API terms of service to confirm that persistent storage and scheduled messaging are permitted under the intended usage pattern?

6. **Charting capability:** The stakeholder confirmed users can view history and a chart via the in-app Telegram viewer. What format is the chart expected to take (image, inline data table, or other), and is this constrained by what Telegram natively supports?

---

## Version

v0.2

## Based on

v0.1

## Changes Introduced

- **Problem Statement:** Added explicit scope framing — personal portfolio project for a closed group of maximum ~100 users. Removed implied public-product framing.
- **Business Impact:** Replaced commercial impact framing with portfolio and personal utility framing. Confirmed monetization is not applicable. Removed competitive displacement as a goal.
- **Stakeholders:** Collapsed to three stakeholders reflecting actual project context. Removed commercial and enterprise stakeholder archetypes.
- **Constraints:** Added confirmed facts on scale, budget, identity model, and regulatory posture. Regulatory section reframed around actual data collection scope (Telegram ID only, anonymous, closed group).
- **Success Metrics:** Lowered targets to reflect realistic scale. Reframed all targets as hypotheses. Replaced parse accuracy metric with parse failure handling metric. Added developer learning outcome and system functionality metrics.
- **Assumptions:** Expanded from 7 to 9. Added assumptions on infrastructure cost sustainability and onboarding sufficiency. Incorporated confirmed stakeholder facts.
- **Risks:** Fully populated (v0.1 deferred this section). Added hosting tier risk, scope creep risk, and onboarding risk.
- **Open Questions:** Fully populated (v0.1 deferred this section). Added questions on timeline, data backup, onboarding scope, alert mechanism, Telegram policy verification, and charting format.

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-01 | No monetization model | Confirmed by project owner — this is a portfolio and personal utility project | v0.2 | Closed |
| D-02 | Identity model is Telegram ID only — no PII collected | Confirmed by project owner | v0.2 | Closed |
| D-03 | Parse failure is acceptable — fallback to manual categorisation prompt | Confirmed by project owner | v0.2 | Closed |
| D-04 | Onboarding via demo parameters with fake historical data | Confirmed by project owner as intended first-time experience | v0.2 | Closed |
| D-05 | No public access — closed group of personally known users only | Confirmed by project owner | v0.2 | Closed |
| D-06 | Near-zero budget — free hosting tiers as operational baseline | Confirmed by project owner | v0.2 | Closed |

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| U-01 | Business | No timeline defined for first functional version | Medium — affects prioritisation of features | Ask project owner to define a target milestone |
| U-02 | System | Free hosting tier limits not yet evaluated against expected load | Medium — could constrain reliability | Evaluate specific hosting options against 100-user usage profile |
| U-03 | Behavioral | Unknown whether onboarding flow is sufficient for non-technical friends | Medium — affects early retention | Observe first 5 users through onboarding; adjust if confusion is observed |
| U-04 | Business | Telegram policy compliance not yet verified for persistent storage and scheduled alerts | High — if non-compliant, delivery channel fails | Developer to review Telegram bot API terms before development begins |
| U-05 | System | Charting format and Telegram display constraints not yet defined | Medium — affects feature scope | Determine what Telegram natively supports for inline media before committing to chart feature |

## Traceability Updates

| Business Goal | Linked Metric | Risk |
|---|---|---|
| Developer builds demonstrable portfolio project | Developer Learning Outcome | Scope creep diverts time from core learning objectives |
| Users track personal metrics consistently within Telegram | User Logging Consistency, Parameter Retention Rate | Parse failures or poor onboarding reduce early adoption |
| System handles parse failures without data loss | Parse Failure Handling Rate | Fallback prompt design is insufficient; users abandon entry |
| System is reliable within free-tier infrastructure | System Functionality | Hosting tier limitations cause downtime or data loss |
| User data remains isolated and anonymous | Data isolation (must-hold assumption) | Identity model failure leads to cross-user data exposure |
