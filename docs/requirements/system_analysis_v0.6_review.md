# Architecture Review Report — System Context Document

> **Review Date:** 2026-03-17
> **Reviewer Role:** Senior Architecture Review Board (Architecture Critic + Devil's Advocate)

---

## Reviewed Versions

- **System Context Document:** v0.6
- **Business Analysis:** v0.5
- **Review Based On:** system_analysis_v0.6.md, business_analysis_v0.5.md

---

## 1. Executive Assessment

System Context Document v0.6 represents a materially improved iteration over v0.5, closing the most critical lifecycle gaps (ParseAttempt states, Metric Abandoned state, Entry cascade deletion, InternalUser quantitative boundary). The entity model is coherent, the 10 flows are individually well-structured, and business goal traceability is explicit and meaningful. However, the document carries five structural weaknesses that require resolution before it can safely anchor architecture design: (1) NFRs are almost entirely absent — no performance, availability, or security targets are stated; (2) the logging and observability dependency required to measure every declared success metric is not modeled as a system component; (3) the `raw_input` field on the Entry entity creates an undeclared personal-data footprint that directly contradicts the privacy-by-design premise; (4) multiple open decisions (SD-003, SD-004, SD-007) and uncertainty items (SU-001 through SU-007) remain unresolved and will create ambiguous handoff conditions for the architect; (5) individual metric deletion is referenced in the state model but has no interaction flow. At current completeness, this document provides a useful but incomplete baseline — it cannot be handed to an architect without targeted fixes.

---

## 2. Strengths

- **Entity model is well-formed:** All six entities have clear attributes, relationships, and lifecycle descriptions. The inferred entities (ParseAttempt, MetricActivityStatus) are properly qualified as inferred and their scope is bounded.
- **State models are comprehensive:** Four complete state machines covering all major lifecycle objects. Transitions, entry conditions, exit triggers, and risk annotations are present for every state.
- **10 interaction flows cover the core scope:** Each flow has trigger, actor, processing steps, output, and per-step risk points. This is unusually thorough for a context document.
- **Traceability section is genuinely useful:** Every business goal is traced to specific entities, flows, and states. Measurement mechanisms are named for most success metrics.
- **Uncertainty Register and Decision Log are explicit:** SU-001–007 and SD-001–007 correctly surface what remains open. The document does not pretend to have resolved things it hasn't.
- **Risk inheritance is clean:** Business risks R-001 to R-008 are carried forward with accurate re-framing; system-level risks R-009 to R-016 are additions, not duplications.
- **Boundary assumptions are precise:** The identity mapping vs. identity authentication distinction (Assumption 4, §3) is a high-quality clarification that will prevent architecture misunderstandings.
- **Assumption management includes validation ideas:** Each assumption includes a falsification scenario and a proposed validation path — above-average practice at this stage.

---

## 3. Critical Weaknesses

- **No NFRs are defined.** The document contains no performance targets (response latency, chart generation time), no availability/uptime target, no throughput ceiling, and no graceful degradation policy. Architecture design cannot proceed without a minimum NFR baseline, even for a 10-user portfolio project.
- **Observability is not modeled as a system component.** The traceability section repeatedly states "system must log X" (alert evaluation events, entry resolution outcomes, chart invocations) to measure all five success metrics, yet no logging or observability component is declared in §7 Required System Component Dependencies. This creates a hidden mandatory dependency.
- **`raw_input` on Entry entity is a de-facto personal data store.** The system stores the original free-text of every user message as `raw_input`. Users are likely to include personally identifying or sensitive content in metric messages (e.g., `mood 3, anxiety worsening`, `weight 82.5 after hospitalization`, `expenses 200 for therapy`). This directly contradicts the "no personal data stored" privacy-by-design claim (D-007, Business §4). The privacy analysis in the business document addresses identity data (name, phone, email) but does not address the content of user messages.
- **Individual metric deletion has no interaction flow.** The Metric "Deleted" state (§6) and §3 (Inside the System) both reference individual metric deletion, but no dedicated flow exists. Flow 8 (Metric Listing & Management) explicitly states deletion is not included. This is flagged as SU-006 but left unresolved. An architect will make inconsistent assumptions without this flow.
- **Three open system decisions remain unconfirmed by the stakeholder.** SD-003 (alert one-shot vs. persistent repeating), SD-004 (confirmation step for account and alert deletion), and SD-007 (behavior when second ambiguous message arrives during active ParseAttempt) all require stakeholder sign-off before architecture design can finalise state models and flow branches.
- **Compound flow atomicity is unresolved.** Flow 1 risk points identify a three-way compound flow (Onboarding + Data Entry + Metric Creation) and state "failure modes for partial success across any of these legs are undefined." This is the most likely real-world first-contact scenario and its failure behavior is deferred with no resolution path.
- **Bot access control is entirely absent.** The document does not address whether the bot is accessible to any Telegram user or restricted to a known cohort. Any Telegram user can send a message to the bot and trigger registration (Flow 1). There is no mention of an allowlist, invitation mechanism, or any form of bot-level access gating. For a system claiming ~10 users by design, uncontrolled public access is an unacknowledged risk.
- **Periodicity is accepted as a free-form user string with no validation.** Flow 7 Risk Points explicitly state "No periodicity validation beyond user-provided string — the system accepts the user's input as authoritative." Yet MetricActivityStatus computation requires interpreting this string to determine "last 5 periods." An arbitrary string like `"every other Tuesday"`, `"fortnightly"`, or `"whenever I feel like it"` cannot be interpreted. The valid set of periodicities must be defined.

---

## 4. NFR Coverage Gaps

| NFR Category | Missing / Weak Area | Why It Matters | Required Fix |
|---|---|---|---|
| **Performance** | No response latency target stated for any flow. No chart generation time budget defined. | Architect cannot make technology choices without knowing whether 2-second chart generation is acceptable or 10 seconds is a failure. Even at 10 users, unresponsive bots create abandonment — directly threatening the >40% retention target. | State minimum acceptable response times per interaction type (e.g., entry acknowledgment ≤2s, chart delivery ≤10s). |
| **Availability** | No uptime or availability target declared. | The Data Persistence Layer is declared Critical (R-013) but no availability obligation is attached. If the system is down 10% of the time, the retention target is unreachable. | Define a minimum availability expectation (e.g., 95% uptime acceptable for portfolio; 99% for meaningful retention). |
| **Reliability — Transactional** | No atomicity guarantee for any multi-step flow. Flow 2 stores an Entry (step 3), evaluates alerts (step 4), and sends a confirmation (step 5). No behavior is defined if step 3 succeeds but step 4 or 5 fails. | Silent partial completion is a data integrity risk. | Declare transactional expectations: which steps must be atomic, and what constitutes a rollback condition. |
| **Security — Bot Access** | No access control policy on bot registration or usage. The bot is implicitly open to any Telegram user. | An unanticipated user cohort inflates the user base beyond the ~10 target, potentially surfacing latent defects in user isolation (R-005). | Define whether the bot is public or restricted, and if restricted, describe the gating mechanism. |
| **Security — Bot Token** | No mention of how the Telegram Bot API token is secured. | Token compromise = full impersonation of the bot, access to all user interactions. | Acknowledge secrets management (even at portfolio scale: env variable, secret manager). |
| **Scalability** | Document states "10 users is sufficient for single-instance deployment." No ceiling or degradation point is acknowledged. | If a stakeholder shares the bot publicly or adds users beyond the design scope, the system may degrade without warning. | State the designed ceiling explicitly (e.g., "system is designed for ≤20 users; beyond this, architecture review required"). |
| **Observability** | No logging or tracing component declared. Success metrics require event logs but no component is modeled to capture them. | Without a logging component, the >85% parse success rate and >95% alert accuracy cannot be measured — making all success metrics unverifiable. | Declare a Logging / Observability Component in §7 as a required system component dependency. |

---

## 5. Trade-off & ADR Issues

- **SD-003 (alert lifecycle) is open but treated as tentatively resolved.** The document models alerts as persistent-repeating, documents an assumption (Assumption 5), and states "Confirm with stakeholder." However, if the stakeholder decides one-shot behavior is correct, the Alert state model changes materially (Triggered becomes a terminal state, not a transition back to Monitoring). This cannot remain open at context sign-off.

- **SD-004 (confirmation step for destructive operations) has no alternative considered.** The decision mandates a confirmation prompt for account deletion and alert deletion but provides no rationale for why the confirmation is a prompt rather than, e.g., a timed undo window, a keyword confirmation (`DELETE MY DATA`), or a two-step cooldown. For a Telegram-native system, the UX of these confirmation mechanisms varies significantly.

- **No trade-off discussion for free-text vs. structured input.** The business document accepts free-text as the core value proposition. The system context document should at minimum record that structured input (e.g., Telegram bot command syntax `/log weight 82.5`) was considered and rejected in favor of pure free-text — and document the consequence: higher NLP complexity and parse failure surface area.

- **ParseAttempt expiry timeout (SU-001) has no candidate range discussed.** A 30-second timeout is qualitatively different from a 24-hour timeout. The uncertainty is recorded but no bounding analysis is provided. This will produce architecture questions with no grounding.

- **MetricActivityStatus computation trigger strategy (SU-005) is deferred without a candidate approach.** Options include event-driven (trigger on every Entry), scheduled (cron on periodicity boundary), or lazy (compute on read). Each has materially different implications for system design. The document leaves this entirely open.

---

## 6. Reliability & Failure Scenario Issues

| Scenario | What is Missing | Risk | Priority |
|---|---|---|---|
| Data Persistence Layer failure mid-transaction (e.g., entry parsed, not stored) | No rollback or compensating behavior defined. User may receive a confirmation message for an entry that was never persisted. | Data integrity failure; user believes data is stored when it is not. Silent data loss. | **Critical** |
| Telegram dispatch failure during alert notification (R-011) | "System design should define retry or dead-letter behaviour" — but no retry policy, no queue, no dead-letter destination is described. | Alert accuracy target (>95%) cannot be met without a retry mechanism. Dispatch failure is silent to the user. | **High** |
| Chart Rendering Component failure during Flow 4 (R-016) | "Failure modes (rendering timeout, format incompatibility) must be defined" — deferred to architecture. No fallback (e.g., text summary instead of image) is considered. | User experiences a silent failure or unhandled error. Chart adoption metric (>25%) is unmeasurable if failures are not counted. | **Medium** |
| Compound flow partial failure: Onboarding + Entry + Metric Creation (Flow 1 risk point) | Explicitly flagged as "undefined." No resolution path proposed. | First-contact experience may leave the user in an indeterminate state (registered but without their first entry stored). | **High** |
| User sends new message during active ParseAttempt (R-010, SU-007) | Behavior is deferred to system design. Two options (treat as selection, treat as new input) have opposite consequences and neither is designated. | Common real-world scenario. Silent mis-routing of user intent. | **High** |
| Telegram account loss before bot account deletion | User's bot data persists under the 1-year retention guarantee but is unreachable. No orphan cleanup policy exists beyond the 1-year window. | Orphaned data for users who lost Telegram access. Data retention obligation duration is met but data serves no recoverable purpose. | **Low** (accepted risk, but should be stated explicitly as an orphan data policy) |
| Alert notification fires into an active ParseAttempt disambiguation session | Not modeled. The bot sends an alert notification while the user is responding to a selection prompt. Telegram delivers both messages sequentially. The user may confuse the alert notification for the selection prompt options. | Conversation state corruption; user may respond to alert text as though it were a metric selection. | **Medium** |

---

## 7. Security & Compliance Issues

| Area | Gap | Risk | Priority |
|---|---|---|---|
| **`raw_input` as personal data** | Entry entity stores the original free-text message as `raw_input`. Users routinely include personal context in tracking messages. This field is not excluded from the privacy-by-design analysis. | System stores personal/sensitive data while claiming it stores none. GDPR Art. 4(1) definition of personal data may be satisfied by content even without an identifier — particularly for health-adjacent data. | **High** |
| **Bot access control** | No mechanism prevents arbitrary Telegram users from registering and using the bot. | Uncontrolled user registration beyond the ~10 user design scope. Potential exposure of system-level defects in user isolation. | **Medium** |
| **Bot API token security** | The Telegram Bot Token is a privileged secret enabling full bot impersonation. Its storage, rotation, and protection are not mentioned. | Token leakage → full read/write access to all bot interactions; ability to impersonate the bot to all users. | **High** |
| **Onboarding consent without acknowledgment** | Flow 1 dispatches an onboarding message describing the retention and no-export policy. There is no confirmation that the user has read or acknowledged it. | Trust and transparency risk (linked to R-006). Users may claim they were not informed of the no-export limitation. | **Low** (portfolio context; noted for completeness) |
| **No rate limiting or abuse prevention** | Any Telegram user can flood the bot with messages. No mention of rate limiting on message processing or registration. | Bot may be abused to exhaust resources or generate excessive ParseAttempts, degrading service for legitimate users. | **Low** (10-user scope, but should be acknowledged) |

---

## 8. Observability Issues

| Signal | Missing Detail | Operational Risk | Priority |
|---|---|---|---|
| **Parse resolution outcome logging** | Traceability section states "system must log each inbound message attributed as a data entry attempt and its resolution outcome." No logging component is declared in §7. No log schema is described. | >85% data input success rate cannot be computed. | **Critical** |
| **Alert evaluation event logging** | Traceability section states "system must log each alert evaluation event (entry evaluated, condition result, dispatch outcome)." No logging component or log schema exists. | >95% alert accuracy cannot be measured. | **Critical** |
| **Chart invocation logging** | Chart adoption metric (>25%) requires chart command invocations / active users. No logging mechanism. | Chart adoption success metric is unmeasurable. | **High** |
| **MetricActivityStatus computation audit** | SU-005 flags stale status as a risk. Without a computation audit trail, stale active/inactive status cannot be detected or corrected. | Retention tracking metric may silently report incorrect values. | **Medium** |
| **Operational health signals** | No system health metrics are described (e.g., message queue depth, response latency, storage utilization). Single operator relies on these for incident detection. | Incidents are not detected until users report failures. Single operator has no proactive visibility. | **Medium** |

---

## 9. Broken or Incomplete Traceability

| Item | Missing Link | Why Problematic | Fix |
|---|---|---|---|
| **Individual Metric Deletion** | State "Deleted" exists for Metric; §3 lists it as in-scope; no interaction flow covers it | An architect designing the metric management component has no defined user-facing behavior for this operation. Will make assumptions inconsistent with business intent. | Add Flow 11 (Individual Metric Deletion) or explicitly state it is deferred with a stakeholder decision. |
| **Periodicity Validation Rules** | No defined set of valid periodicities. MetricActivityStatus computation depends on interpreting periodicity strings. | "Last 5 periods" is uncomputable for arbitrary strings. The active-user success metric breaks for non-standard periodicity inputs. | Define the valid periodicity vocabulary (e.g., `daily`, `weekly`) as a constraint. |
| **Logging / Observability Component** | Measurement of all 5 success metrics requires event logging, but no logging component appears in §7. | Every success metric is unverifiable without this component. Business goal traceability collapses at measurement time. | Add Logging / Observability Component to §7 Required System Component Dependencies. |
| **Data Retention Enforcement Mechanism** | D-013 requires 1-year retention. §3 Inside the System lists "Data retention enforcement." No flow or component models how this is enforced. | A scheduled job or retention check must exist. Without it, the retention obligation is stated but unimplemented. | At minimum, declare an intent to model this as a scheduled process or storage-layer policy and flag it for architecture design. |
| **`raw_input` Privacy Classification** | Entry entity stores raw_input. Privacy analysis (D-007, R-007) covers identity data but not message content. | Privacy-by-design claim is incomplete. Business risk register underestimates actual data sensitivity. | Add a privacy assessment of `raw_input` to the entity description and risk register. Either justify retention of raw_input or propose a scrubbing/anonymization policy. |
| **Multi-value Entry Dimension Naming** | Alert entity has `target_value_dimension` for multi-value entries. Flow 9 references it. But nowhere is it defined how dimensions are named at entry time. | When a user stores `80kg 5reps`, are dimensions named by the parser? By the user at metric creation? By position? Alert configuration and chart rendering both depend on consistent dimension naming. | Define the dimension naming convention for multi-value entries. |

---

## 10. Devil's Advocate Challenges

The following challenges are structural and strategic stress-tests, not minor corrections.

### 10.1 The `raw_input` Privacy Contradiction May Invalidate the Entire Privacy Premise

The system's core regulatory defense is "we store no personal data, only opaque IDs." The `raw_input` field stores exactly what users type. Users tracking health metrics will type things like *"weight 82, feeling sick again"* or *"mood 2, therapist appointment today."* These are special-category personal data under GDPR Article 9 (health data). The system does not know or filter what users include. The privacy analysis must be extended to cover message content, not just identity fields — otherwise the design choice documented in D-007 is based on an incomplete threat model.

### 10.2 The >85% Parse Success Target Has No Baseline

The system targets >85% successful automatic parse. But what is the baseline parse accuracy of a free-text NLP approach against ~10 user-defined, arbitrary metric names? If the baseline is 60%, reaching 85% requires significant NLP investment. If the baseline is 95%, the target is conservative. No NLP approach or technology is even hinted at. The target is stated but the mechanism to achieve it is entirely undefined. An architect receiving this document has no foundation for technology selection.

### 10.3 Periodicity Is a Hidden Complexity Bomb

Users define periodicity at metric creation as a free-form string. MetricActivityStatus requires computing "last 5 periods" from this string. The business document gives examples of "daily" and "weekly." But what is a "period" boundary for a weekly metric? Is Monday the start of a week? Does a "period" mean 7 calendar days from the last entry? A calendar week (Mon–Sun)? The active-user definition (≥4/5 periods) will produce different results under different interpretations. The success metric *"tracking retention >40%"* changes meaning depending on which interpretation is implemented. This must be resolved before the architect designs the activity computation engine.

### 10.4 One-ParseAttempt-Per-User Is Fragile in Real Telegram Usage

Assumption 7 limits the system to one active ParseAttempt per user. In real Telegram usage, users frequently send messages in rapid succession: *"weight 82"* immediately followed by *"sorry, 82.5"*. If the first message creates an active ParseAttempt, the second message arrives while the first is unresolved. SU-007 defers the behavior. But this is not an edge case — it is the modal behavior of messaging-app users. Assumption 7 is a simplification that may produce frequent user-facing failures in the most common interaction pattern.

### 10.5 Alert Notifications Can Corrupt ParseAttempt Conversation State

The system uses a single Telegram channel for both data entry and alert notifications (Boundary Assumption 5). Consider: a user submits an ambiguous entry → a ParseAttempt is created → an unrelated alert fires on a different metric → the bot sends an alert notification message → the user reads both messages and responds to what they think is the selection prompt but is actually responding to the alert notification. The system receives a response and may route it as a metric selection. This is a concrete, plausible failure path that is not addressed anywhere in the document.

### 10.6 Entry Immutability Creates Cumulative Data Pollution

The business goal is "enable self-insight through history." Entry immutability means confident-but-wrong auto-parses permanently pollute a metric's time series. With the NLP approach targeting 85% accuracy (not 100%), 15% of entries may be silently incorrect. Over 100 entries, 15 incorrect data points distort the chart and may trigger false alerts. The "self-insight" goal is compromised by design. The document acknowledges this in Flow 2 risk points but treats it as acceptable. The cumulative long-term impact on chart quality and alert accuracy should be explicitly assessed.

---

## 11. Scoring

| Dimension | Raw Score (0–5) | Weight | Weighted Score | Comment |
|---|---|---|---|---|
| Alignment to Business Goals | 4 | ×2 | 8 | Traceability is genuinely good; `raw_input` gap and logging gap threaten measurement of all metrics |
| Boundary & Context Consistency | 4 | ×1 | 4 | Boundaries are precise and well-articulated; minor typographic error (double dash in §3) |
| Component Model Quality | 3 | ×2 | 6 | Entity model is solid; logging component, retention mechanism, and periodicity vocabulary missing |
| Interaction Model Clarity | 3 | ×2 | 6 | 10 flows are individually clear; individual metric deletion missing; compound flow failure modes undefined |
| NFR Coverage & Tactics | 1 | ×2 | 2 | No latency, no availability, no throughput targets stated at all; effectively absent |
| Trade-off Justification | 3 | ×2 | 6 | Decision log is present and structured; SD-003, SD-004, SD-007 unresolved; no free-text vs. structured input trade-off recorded |
| Reliability & Failure Handling | 2 | ×2 | 4 | Risk register is good; transactional failure, mid-flow failures, and retry policies all deferred without candidate approach |
| Security & Compliance Baseline | 2 | ×1 | 2 | Privacy-by-design acknowledged but `raw_input` gap is significant; no access control, no token security |
| Observability Readiness | 1 | ×1 | 1 | Measurement intent is expressed repeatedly but no observability component, no log schema, no SLO candidates |
| Risk Identification & Mitigation | 3 | ×1 | 3 | Risk register is comprehensive; several mitigations are "defer to system design" without candidate resolution |

**Total Score: 42 / 70**

> **Threshold:** 42–55 = Significant refinement required

---

## 12. Mandatory Revisions

1. **Extend the privacy analysis to cover `raw_input` content.** Either (a) justify that free-text content does not constitute personal data in this system's context with explicit reasoning, or (b) define a scrubbing or anonymization policy for `raw_input` storage. Update D-007 and R-007 accordingly. This is a pre-architecture blocker.

2. **Define a minimum NFR set.** At minimum: (a) acceptable response latency for entry acknowledgment and chart delivery, (b) system availability target, (c) transactional atomicity expectations for multi-step flows. These do not need to be enterprise-grade — they need to exist at all to make architecture design tractable.

3. **Declare a Logging / Observability Component in §7.** Without it, all five success metrics are unverifiable by design. Describe its purpose, what events it captures, and the failure risk if absent. At minimum, it is a Medium-risk dependency on par with the Chart Rendering Component.

4. **Define the valid periodicity vocabulary.** Replace "user-provided string" with an explicit closed list (e.g., `daily`, `weekly`) and define how a "period boundary" is computed for each value. This is required for MetricActivityStatus computation and the active-user success metric.

5. **Resolve SD-003, SD-004, and SD-007 with stakeholder.** These three open decisions directly affect the Alert state model, the account deletion flow, and the ParseAttempt conflict behavior respectively. The architecture document cannot finalize these models with open stakeholder questions.

6. **Add Flow 11: Individual Metric Deletion.** The state model and §3 both reference this capability. An architect must have a defined flow covering: trigger, confirmation step, cascade behavior, user notification, and what happens to active alerts on the deleted metric.

7. **Address the bot access control gap.** Define whether the bot is public (any Telegram user can register) or restricted (allowlist/invitation-only). If restricted, describe the access control mechanism. If intentionally public, acknowledge the risk explicitly in the risk register.

8. **Model the compound flow failure behavior.** For the three-way compound case (Onboarding + Data Entry + Metric Creation on first contact), define the transactional semantics: which steps are atomic, what the rollback policy is if any step fails, and what state the user is left in on partial success.

9. **Define naming convention for multi-value entry dimensions.** Specify how dimensions are named when a user submits a compound entry (`80kg 5reps`). This is required for Alert `target_value_dimension` to be operable and for chart rendering of multi-value metrics.

10. **Add an operational alert for the alert-into-ParseAttempt conversation state collision.** Either define how the system distinguishes an alert notification from a selection prompt response, or declare that alert notifications are suppressed while a ParseAttempt is active for that user.

---

## 13. Iteration Recommendation

**Iterate — Targeted Fixes Required**

The document scores 42/70, at the boundary of "Significant refinement required." The entity model, flow structure, and traceability are of high quality and should not be reworked. The mandatory revisions are targeted and do not require architectural redesign — they require completing the NFR baseline, resolving stakeholder-dependent open questions, and addressing the `raw_input` privacy gap. The document should not proceed to architecture design until items 1, 2, 3, 4, 5, and 6 in the Mandatory Revisions list are resolved. Items 7–10 are important but can be resolved in parallel with early architecture design if explicitly documented as pre-design constraints.

---

*Review completed: 2026-03-17*
*Review role: Architecture Review Board (Critic + Devil's Advocate)*
*Document reviewed: system_analysis_v0.6.md*
*Business reference: business_analysis_v0.5.md*
