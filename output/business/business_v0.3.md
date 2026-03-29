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

| Impact Area | Description | Classification |
|---|---|---|
| Personal utility | Reduces friction for daily self-tracking via a tool already open on the developer's device | Fact |
| Developer learning | Demonstrates hands-on ability to design, build, and ship a stateful, multi-user conversational system end-to-end | Fact |
| Portfolio value | Intended audience is potential employers or collaborators in software engineering roles. The project demonstrates: stateful bot architecture, natural-language parsing, multi-user data isolation, and chart generation delivered as static images | Assumption — portfolio reception is unvalidated until the project is shown to reviewers |
| Infrastructure cost | Near-zero. Free hosting tiers are available and sufficient at the target scale of ~100 users | Fact |
| Monetization | None. No revenue model exists or is planned | Fact |
| Cost of inaction | Developer continues using fragmented tools or spreadsheets with no portfolio artifact produced | Fact |
| Developer time investment | Estimated 40–80 hours total effort across design, development, testing, and iteration. This is an explicit, non-trivial personal cost even if no financial cost exists | Assumption — actual hours will vary with scope decisions and learning curve |

---

## 3. Stakeholders

| Stakeholder | Role | Interest | Risk Exposure |
|---|---|---|---|
| Developer / Bot Owner | Builder, primary user, infrastructure operator | Learning outcome, personal utility, portfolio artifact | Highest — bears all time, effort, and maintenance cost |
| End Users (friends, max ~100) | Voluntary participants, closed group | Convenient tracking with no install friction | Low — no financial exposure; risk is data loss or bot unavailability |
| Telegram Platform | Delivery infrastructure | Terms of service compliance | External — bot suspension risk falls on the developer |

---

## 4. Constraints

| Constraint | Description | Classification |
|---|---|---|
| Scale | Maximum approximately 100 users, all personally known to the developer | Fact |
| Budget | Near-zero; project must operate within free hosting tiers | Fact |
| Input channel | Telegram only — all user interaction occurs within Telegram | Design Decision (see Decision Log) |
| Parameter model | User-defined parameters with no predefined categories | Fact |
| Multi-tenancy | User data isolated per Telegram ID | Fact |
| Identity model | Telegram ID only; no personally identifiable information collected or stored | Fact |
| Charts | Static PNG images generated and sent directly in the Telegram chat | Design Decision (see Decision Log) |
| Out of scope | External data source integrations, voice input, multi-language support, ML-based predictions, threshold alerts, image recognition | Fact |

---

## 5. Success Metrics

| Metric | Definition | Target | Measurement Method | Classification |
|---|---|---|---|---|
| Developer Learning Outcome | Developer can articulate design decisions and tradeoffs for the system when presenting it | Able to present and discuss the system coherently within 3 months of project start | Self-assessment against a checklist of intended skills | Hypothesis |
| System Functionality | Core flows (log, query, chart) work without critical failure for at least 30 consecutive days post-launch | Zero critical failures in 30-day window | Manual monitoring and error log review | Hypothesis |
| User Logging Consistency | Active users log at least one value per tracked parameter per week | At least 3 of any active users meet this threshold in any given week | Count of log entries per user per parameter per week | Hypothesis |
| Parameter Retention Rate | Proportion of created parameters that still receive log entries after 30 days | Greater than 50% of parameters active at day 30 | Count of parameters with at least one entry in days 25–35 | Hypothesis |
| Parse Failure Resolution | Proportion of ambiguous inputs that are resolved via follow-up prompt rather than silently dropped | Greater than 80% of parse failures result in a clarification prompt and valid entry | Count of successful parse recoveries divided by total parse failures | Hypothesis |
| User Return Rate | Proportion of users who interact with the bot in week 2 after first use | Greater than 40% of users who logged at least one value in week 1 return in week 2 | Count of distinct users active in week 2 vs. week 1 | Hypothesis |
| Project Completion | A minimum viable version of the system is delivered and usable by the developer within the self-imposed milestone | Minimum viable scope delivered within 3 months of project start | Milestone checklist reviewed at the 3-month mark | Hypothesis |

---

## 6. Assumptions

1. **Telegram remains the appropriate delivery channel.**
   Why it exists: Telegram is the developer's and users' primary messaging platform today.
   If false: The delivery mechanism must be redesigned from the ground up, invalidating a core design decision.

2. **Free hosting tiers are sufficient for the target scale.**
   Why it exists: At approximately 100 users with low-frequency interactions, resource consumption is expected to be minimal.
   If false: Infrastructure costs become non-zero and the project requires a budget decision the developer has not planned for.

3. **Users are willing to interact with a bot using natural language commands without a graphical interface.**
   Why it exists: Telegram bots are text-based by default; no evidence of resistance has been observed in this group.
   If false: Logging adoption will be lower than expected and user return rate metrics will not be met.

4. **Natural-language parsing will succeed on the majority of inputs without requiring complex ML.**
   Why it exists: The target user group is small, known, and expected to follow patterns after initial onboarding.
   If false: Parse failure rate will exceed acceptable thresholds and the developer must invest additional effort in parsing logic or prompt design.

5. **Parse failures are acceptable if followed by a clarification prompt.**
   Why it exists: Confirmed by stakeholder decision. Perfect parsing is not required.
   If false: This assumption is confirmed as a design decision and is not subject to revision without explicit stakeholder input.

6. **A demo-first onboarding flow with fake historical data is sufficient to orient new users.**
   Why it exists: Users are non-technical friends who may not understand bot interactions without a concrete example.
   If false: Additional onboarding documentation or guided flows will be required, increasing scope.

7. **No alert or notification mechanism is needed.**
   Why it exists: Confirmed out of scope by stakeholder decision.
   If false: This is out of scope and would require a formal scope change.

8. **Static PNG charts sent in Telegram chat are sufficient for data visualisation needs.**
   Why it exists: Confirmed as the chart delivery mechanism by stakeholder decision. Image recognition is not in scope.
   If false: This is out of scope and would require a formal scope change.

9. **The developer can sustain 40–80 hours of effort to reach a minimum viable product.**
   Why it exists: The project has no external deadline or funding, making developer motivation and availability the primary completion risk.
   If false: The project may stall or remain incomplete, producing no portfolio artifact and no personal utility.

10. **The portfolio artifact will be relevant to the developer's intended audience at the time of completion.**
    Why it exists: Portfolio reception depends on the priorities of reviewers, which may shift between project start and project completion.
    If false: The portfolio value impact is reduced, though the personal utility and learning outcomes remain valid independently.

---

## 7. Risks

| Risk | Impact | Probability | Mitigation Strategy |
|---|---|---|---|
| Telegram platform suspension or API change | Bot becomes unavailable for all users with no fallback | Low | Monitor Telegram terms of service; avoid prohibited use patterns |
| Free hosting tier limits exceeded | Service degradation or unexpected cost | Low at target scale | Monitor resource usage; define a usage ceiling and enforce it |
| Parse failure rate higher than expected | Users frustrated; logging adoption drops | Medium | Implement clarification prompts as the default fallback; instrument failure rate from day one |
| Data loss due to infrastructure failure | User data permanently lost | Low-medium | Document the risk to users upfront; consider periodic exports as a mitigation option |
| Scope creep | Project grows beyond available time; minimum viable scope not delivered | Medium | Define minimum viable scope explicitly before build; treat all additions as explicit scope change decisions |
| Project incompletion | Developer time or motivation runs out before minimum viable scope is delivered | Medium | Define a minimum viable milestone; set a 3-month self-imposed deadline; scope down rather than abandon |
| Onboarding misalignment | Users fail to understand the bot's interaction model; low adoption after first session | Medium | Demo parameters with fake historical data before any real parameters are requested |
| Portfolio value not realised | Intended audience does not value the artifact at time of review | Low | Portfolio value is a secondary goal; personal utility and learning outcome are independent and remain valid |

---

## 8. Open Questions

1. What constitutes the minimum viable scope that would satisfy both the personal utility goal and produce a presentable portfolio artifact? This must be defined before development begins to enforce scope discipline.

2. What is the self-imposed milestone structure? A single 3-month deadline has been proposed as a metric target, but intermediate milestones (e.g., first working log command, first chart sent) have not been defined.

3. Should users be informed explicitly that data is stored and may not be permanent, given the free-tier infrastructure constraint? This is a trust and expectation-management question, not a technical one.

4. How will the developer measure and review the Portfolio Value success metric in practice — specifically, who are the intended reviewers and when will the project be shown to them?

---

## Version

v0.3

## Based on

v0.2

## Changes Introduced

- **Developer time** stated explicitly as 40–80 hours estimated effort; added as a Business Impact row and as Assumption 9.
- **Portfolio value** qualified — intended audience defined as potential employers or collaborators in software engineering roles; skills demonstrated listed explicitly.
- **Threshold alerts** confirmed out of scope. All alert references removed from all sections.
- **Charts** confirmed as static PNG images sent directly in Telegram chat. Documented as a Design Decision in Section 4 and as Assumption 8.
- **Project completion risk** added to the risk register with mitigation strategy of minimum viable scope definition and 3-month self-imposed milestone.
- **Project Completion** success metric added to Section 5 with a 3-month target and milestone checklist measurement method.
- **Telegram-only delivery** reclassified as a Design Decision with a note directing to the Decision Log, rather than a bare fact.
- Assumption count increased from 9 to 10.
- Open Questions updated: alerts and chart format questions removed (resolved). Four new questions added.

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-01 | Telegram is the exclusive delivery channel | Reduces scope; matches existing user behaviour; no alternative channel has been requested | v0.1 | Confirmed |
| D-02 | Identity model is Telegram ID only; no PII collected | Simplifies compliance; no authentication system required | v0.1 | Confirmed |
| D-03 | Parse failures are acceptable if followed by a clarification prompt | Perfect parsing is not required; a fallback prompt is sufficient | v0.2 | Confirmed |
| D-04 | Onboarding uses demo parameters with fake historical data | Reduces new-user confusion without requiring documentation | v0.2 | Confirmed |
| D-05 | Threshold alerts are out of scope | Confirmed by stakeholder decision in v0.3 revision cycle | v0.3 | Confirmed |
| D-06 | Charts are static PNG images sent in Telegram chat | Confirmed by stakeholder decision in v0.3 revision cycle; image recognition not in scope | v0.3 | Confirmed |

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| U-01 | Business | Portfolio value reception is unvalidated | Secondary goal at risk if audience priorities shift | Show project to intended reviewers at completion; assess response |
| U-02 | Business | Developer time estimate (40–80 hours) is informal | Project incompletion risk if effort is underestimated | Track actual hours from project start; review at first milestone |
| U-03 | Behavioral | User willingness to interact via natural language without a GUI is assumed | Adoption risk if users find text-command interaction unintuitive | Observe user behaviour in first two weeks post-launch |
| U-04 | System | Parse failure rate under real user inputs is unknown | Core usability metric at risk if failure rate is high | Instrument parse failures from day one; review within first 30 days |
| U-05 | Business | Minimum viable scope has not been formally defined | Scope creep and completion risk | Define minimum viable scope checklist before development begins |

## Traceability Updates

| Business Goal | Linked Metric | Risk |
|---|---|---|
| Personal utility — reduce logging friction | User Logging Consistency (3/week), User Return Rate (>40% week 2) | Parse failure rate; onboarding misalignment |
| Developer learning | Developer Learning Outcome (coherent presentation within 3 months) | Project incompletion; scope creep |
| Portfolio artifact | Portfolio Value (shown to intended audience at completion) | Relevance shift; project incompletion |
| System reliability | System Functionality (zero critical failures in 30 days) | Telegram suspension; hosting tier limits |
| Scope discipline | Project Completion (minimum viable scope within 3 months) | Scope creep; developer time availability |