# System Context Document

## Reviewed Business Version
v0.3

---

## 1. System Purpose

The system is a Telegram-based personal metric tracking bot serving a closed group of up to approximately 100 personally known users. Its responsibility is to accept free-text messages from users via Telegram, parse those messages to extract user-defined metric names and values, persist those records in isolated per-user storage, and respond with structured confirmations, logs, or static chart images. The system removes the friction of dedicated tracking apps by operating inside a communication channel the target users already use daily. The system has no monetization goal and exists to deliver personal utility and serve as a portfolio demonstration of stateful bot architecture.

---

## 2. Actors

| Actor | Type (Internal/External) | Responsibility | Risk if Misaligned |
|---|---|---|---|
| Developer / Bot Owner | Internal | Builds, deploys, operates, and maintains the system; primary user; defines scope boundaries | Single point of failure for all operations and decisions; scope creep risk |
| End User (Friend) | External | Sends free-text tracking messages; manages own parameters; queries history and charts | Low logging consistency defeats success metrics; unexpected input patterns increase parse failure rate |
| Telegram Platform | External | Delivers messages between users and the bot; renders static PNG images in chat | Platform policy changes, downtime, or rate limits can make the system inaccessible to all actors |

---

## 3. System Boundaries

### Inside the System
- Receiving messages from users via Telegram
- Parsing free-text input to extract parameter name and numeric value
- Generating a clarification prompt when parsing fails
- Creating a new parameter record automatically on first use
- Persisting log entries per user, per parameter, with timestamp
- Enforcing data isolation per Telegram user ID
- Listing a user's own parameters
- Returning the last N log entries for a parameter
- Generating a static PNG trend chart and sending it in Telegram chat
- Executing period comparison (week / month) logic
- Deleting a parameter and its full history on user request
- Executing onboarding flow: presenting demo parameters with fake historical data to first-time users
- Guiding first-time users to add one real parameter

### Outside the System
- Telegram client rendering (controlled by Telegram)
- User identity verification beyond Telegram ID (no PII collected or verified)
- Threshold alerts and push notifications
- External API integrations
- Voice input processing
- Multi-language support
- Machine learning predictions
- Image recognition
- Monetization logic
- User account management outside Telegram identity

### Boundary Assumptions
1. Telegram acts as the sole delivery and identity layer; no alternative input channel exists or is planned.
2. The system identifies users exclusively by their Telegram ID; no mapping to real-world identity is performed.
3. Static PNG charts are generated internally and delivered as Telegram messages; no external charting service is used.
4. All data storage and processing occur within the system boundary; no third-party data processors are in scope.
5. The onboarding flow is triggered automatically on the first message from an unrecognized Telegram ID.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships |
|---|---|---|---|
| User | Represents a participant identified by Telegram ID | Telegram ID (primary identifier), onboarding status, first-seen timestamp | Owns zero or more Parameters; owns zero or more LogEntries |
| Parameter | A user-defined trackable metric | Parameter ID, name (user-defined string), owning User ID, creation timestamp, active/deleted status | Belongs to one User; has zero or more LogEntries |
| LogEntry | A single recorded measurement for a parameter | Entry ID, Parameter ID, User ID, raw input text, parsed value, unit (if present), entry timestamp | Belongs to one Parameter and one User |
| ParseAttempt | A record of an attempted parse of a user message | Attempt ID, User ID, raw input text, parse outcome (success / failure), timestamp | Associated with one User; may or may not produce a LogEntry |
| PendingClarification | A pending state when parse has failed and the bot awaits user clarification | Clarification ID, User ID, original raw input, clarification prompt sent, awaiting-response flag | Belongs to one User; resolves into either a LogEntry or dismissal |
| Chart | A generated static PNG trend image for a parameter | Chart ID, Parameter ID, User ID, period covered, generation timestamp | Derived from LogEntries of one Parameter; delivered as a Telegram message |
| OnboardingSession | Tracks the onboarding state of a first-time user | Session ID, User ID, demo parameters shown, real parameter added flag, completion timestamp | Belongs to one User |

**Ownership notes:**
- All entities are owned by the User identified via Telegram ID.
- Demo parameters created during onboarding are synthetic and are not persisted as real Parameter records unless the user explicitly continues using them (assumption — see Section 8, A-03).
- Deleted Parameters retain their LogEntries until explicitly purged, or are purged immediately on deletion (this is unresolved — see Section 8, A-04).

**Lifecycle relevance:**
- A Parameter transitions through: Created -> Active -> Deleted.
- A LogEntry is immutable once created.
- A PendingClarification is transient: it exists only between a parse failure and user response or timeout.

---

## 5. Data and Interaction Flows

### Flow 1: Successful Metric Logging
- **Trigger:** User sends a free-text message to the bot (e.g., "fuel 40L", "mood 7")
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** The system receives the message; attempts to parse it into a parameter name and value; if parsing succeeds, it checks whether the parameter already exists for this user; if the parameter does not exist, it creates a new Parameter record; it appends a new LogEntry with the parsed value and timestamp; it sends a confirmation message to the user
- **Output:** Confirmation message in Telegram chat; new LogEntry stored; optionally new Parameter created
- **Risk Points:** Parse logic may produce false positives (wrong parameter name or value inferred); auto-creation of parameters on every message may produce unwanted parameter proliferation

### Flow 2: Parse Failure and Clarification
- **Trigger:** User sends a free-text message that the system cannot parse into a valid parameter-value pair
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** The system receives the message; parse attempt fails; the system creates a PendingClarification record; the system sends a clarification prompt to the user asking them to specify the parameter name and value explicitly
- **Output:** Clarification prompt message sent to user in Telegram chat; PendingClarification record created
- **Risk Points:** If the user ignores the clarification prompt, the system must handle the open PendingClarification gracefully; a high rate of parse failures reduces usability and may cause abandonment

### Flow 3: Clarification Resolution
- **Trigger:** User responds to a clarification prompt with a corrected or structured entry
- **Actor:** End User
- **Input:** User's clarifying message in Telegram
- **System Processing:** The system matches the incoming message to the open PendingClarification for this user; attempts to parse the clarification response; if successful, creates a LogEntry; closes the PendingClarification; sends confirmation
- **Output:** Confirmation message; LogEntry created; PendingClarification resolved
- **Risk Points:** The system must correctly associate the clarification response with the correct open PendingClarification; if the user sends a new unrelated message while a clarification is pending, behavior must be defined (currently unresolved)

### Flow 4: Parameter History Query
- **Trigger:** User requests the last N log entries for a parameter (e.g., "show mood history")
- **Actor:** End User
- **Input:** User request specifying a parameter name
- **System Processing:** The system identifies the requesting user via Telegram ID; retrieves the most recent N LogEntries for the named parameter belonging to that user; formats results as a readable message
- **Output:** Formatted list of recent entries sent in Telegram chat
- **Risk Points:** Parameter name must match exactly or approximately to what the user typed; name disambiguation may be needed if multiple similarly named parameters exist

### Flow 5: Trend Chart Generation
- **Trigger:** User requests a trend chart for a parameter
- **Actor:** End User
- **Input:** User request specifying a parameter name and optionally a time period
- **System Processing:** The system retrieves all relevant LogEntries for the named parameter within the requested or default period; generates a static PNG chart image; sends the image as a Telegram message
- **Output:** Static PNG chart image delivered in Telegram chat
- **Risk Points:** If there are too few data points, the chart may be uninformative; chart generation must complete within Telegram's response timeout window

### Flow 6: Period Comparison
- **Trigger:** User requests a comparison between two periods (week or month)
- **Actor:** End User
- **Input:** User request specifying parameter name and comparison period type
- **System Processing:** The system retrieves LogEntries for the named parameter grouped by the two most recent comparable periods; computes summary statistics for each period; formats a comparison response
- **Output:** Comparison summary message sent in Telegram chat
- **Risk Points:** Insufficient data in one or both periods may produce misleading comparisons; the system must handle and communicate sparse data gracefully

### Flow 7: Parameter List Query
- **Trigger:** User requests to see their tracked parameters
- **Actor:** End User
- **Input:** User request (e.g., "list parameters", "what am I tracking")
- **System Processing:** The system retrieves all active Parameters belonging to the requesting user; formats them as a list
- **Output:** List of active parameter names sent in Telegram chat
- **Risk Points:** If a user has many parameters, the response may be verbose; no pagination mechanism is defined

### Flow 8: Parameter Deletion
- **Trigger:** User requests deletion of a parameter
- **Actor:** End User
- **Input:** User request specifying the parameter name to delete
- **System Processing:** The system identifies the named parameter for the requesting user; marks it as deleted (or permanently removes it — see A-04); removes or archives associated LogEntries
- **Output:** Deletion confirmation message sent in Telegram chat
- **Risk Points:** Accidental deletion is irreversible if entries are purged; no confirmation step is currently defined in the business document

### Flow 9: First-Time Onboarding
- **Trigger:** System receives first message from an unrecognized Telegram ID
- **Actor:** End User (new)
- **Input:** Any first message sent to the bot
- **System Processing:** The system detects that this Telegram ID has no existing User record; creates a new User record; presents demo parameters with synthetic fake historical data; prompts the user to add one real parameter
- **Output:** Welcome and demo content delivered in Telegram chat; User record created; OnboardingSession created
- **Risk Points:** Demo data must be clearly labeled as fake to avoid confusion; if the user's first message is a valid tracking command, the system must decide whether to process it as a log entry or force onboarding first (currently unresolved — see A-05)

---

## 6. State Model

### Parameter States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Non-existent | System start, or no message ever sent for this parameter name | User sends a parseable message with a new parameter name | Created | Auto-creation may generate unwanted parameters |
| Active | Parameter record created (auto or explicit) | User sends a delete request for this parameter | Deleted | No intermediate archival state defined |
| Deleted | User deletion request processed | (terminal — no recovery path defined) | None (terminal) | Accidental deletion has no undo mechanism |

### LogEntry States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Recorded | Successful parse and storage of a metric value | Parameter deletion (may cascade) | Purged (on parameter deletion) | Immutability means errors cannot be corrected by the user |
| Purged | Associated Parameter is deleted and entries are removed | (terminal) | None (terminal) | Data loss is permanent |

### PendingClarification States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Open | Parse attempt fails; clarification prompt sent to user | User responds with a clarification message; or user sends a new unrelated message; or a timeout occurs | Resolved / Abandoned | Behavior on competing messages while clarification is open is undefined |
| Resolved | User's clarification response successfully parsed into a LogEntry | (terminal) | None (terminal) | Correct association of response to open clarification required |
| Abandoned | User does not respond, or response cannot be parsed, or a timeout is reached | (terminal) | None (terminal) | No retry mechanism is defined; the original message is lost |

### OnboardingSession States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| In Progress | First message from an unrecognized Telegram ID received | User adds a real parameter; or user explicitly skips onboarding | Completed / Skipped | Undefined behavior if user sends a log command before completing onboarding |
| Completed | User has added at least one real parameter during onboarding | (terminal) | None (terminal) | None identified |
| Skipped | User explicitly bypasses the onboarding flow (if such a mechanism exists) | (terminal) | None (terminal) | Assumption — skip mechanism existence is unconfirmed (A-05) |

### User States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| New | First message received from an unrecognized Telegram ID | Onboarding flow begins | Onboarding | No pre-registration mechanism exists |
| Onboarding | Onboarding session created | Onboarding session reaches Completed or Skipped state | Active | Undefined behavior if user sends commands mid-onboarding |
| Active | Onboarding complete; user is interacting with the system | No defined exit trigger currently | Active (persistent) | No account deactivation or removal mechanism is defined |

---

## 7. External Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Platform | Message delivery, user identity (Telegram ID), image display, chat interface | Hard dependency — system cannot function without it | High — any Telegram outage, API change, or policy change makes the system completely inaccessible |
| Free Hosting Infrastructure | Runtime environment for the bot process and data storage | Hard dependency — system cannot run without a host | Medium — free tier limits (memory, CPU, uptime, storage quotas) may cause degraded or interrupted service; data loss risk on tier eviction |

No third-party integrations are proposed. Dependencies are stated as they exist in the approved business document.

---

## 8. Assumptions

1. **A-01: Telegram ID is stable and unique per user.**
   - Why it exists: The entire identity model relies on Telegram ID as the sole identifier with no PII fallback.
   - Risk if false: If a user loses access to their Telegram account, all their data becomes inaccessible or orphaned. If IDs are ever reassigned (highly unlikely but not documented as impossible), data isolation could be violated.
   - Validation idea: Review Telegram platform documentation to confirm ID permanence guarantees.

2. **A-02: Free-text messages are the only input modality used.**
   - Why it exists: Business document explicitly excludes voice input and image recognition.
   - Risk if false: If users attempt to send voice notes or images to log data, the system will either ignore them or generate parse failures, causing user frustration.
   - Validation idea: Observe actual user behavior in the first weeks post-launch; define explicit rejection messages for non-text inputs.

3. **A-03: Demo parameters created during onboarding are synthetic and not persisted as real user data.**
   - Why it exists: The business document states onboarding uses demo parameters with fake historical data, but does not specify whether the user can continue tracking with those demo parameters.
   - Risk if false: If demo data is co-mingled with real data, analytics and charts will be distorted.
   - Validation idea: Confirm with developer whether demo parameters are ephemeral display-only or persistent seeded records.

4. **A-04: Deleting a parameter purges all associated LogEntries immediately.**
   - Why it exists: The business document states deletion removes a parameter "along with its history," implying immediate purge, but does not specify soft-delete vs. hard-delete.
   - Risk if false: If soft-delete is used, storage grows indefinitely. If hard-delete is used with no confirmation, accidental data loss is permanent.
   - Validation idea: Developer to confirm deletion semantics; consider whether a confirmation step is needed.

5. **A-05: The onboarding flow can be bypassed or auto-completes if the user sends a valid log command as their first message.**
   - Why it exists: The business document does not define what happens if a returning user's first message to the bot is a tracking command rather than an interactive onboarding response.
   - Risk if false: If onboarding is mandatory and blocks all other commands, users who know what they want to do cannot proceed without completing onboarding steps.
   - Validation idea: Developer to define onboarding interrupt behavior; specify whether a valid log command during onboarding should be processed or deferred.

6. **A-06: The system can handle at most approximately 100 concurrent users without performance degradation.**
   - Why it exists: The business document states the target scale is max ~100 users on free hosting tiers.
   - Risk if false: If actual concurrent usage spikes beyond what free tier resources support, the system may become unresponsive.
   - Validation idea: Profile expected message volume; verify free tier resource limits against estimated load.

7. **A-07: Parse failure is defined as any message the system cannot extract a valid parameter-value pair from.**
   - Why it exists: The business document references parse failures and clarification prompts but does not define the exact boundary between a parseable and unparseable message.
   - Risk if false: If the parse failure definition is too strict, many valid inputs will trigger unnecessary clarification prompts. If too loose, incorrect data will be logged silently.
   - Validation idea: Developer to define and document parse failure criteria; measure parse failure rate in first 30 days against the >80% resolution metric.

8. **A-08: The "last N entries" for history queries uses a fixed or user-configurable N.**
   - Why it exists: The business document specifies "last N entries" without defining what N is or whether it is configurable.
   - Risk if false: A fixed N that is too small renders history queries uninformative; a fixed N that is too large produces overly long Telegram messages.
   - Validation idea: Developer to define default N; consider whether the user can specify N inline in their query.

---

## 9. Risks

| Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|
| High parse failure rate causes user abandonment | Behavioral | High — directly undermines core value proposition | Medium — free-text is inherently ambiguous | Invest in robust parse logic; define a clear message format guide for users; measure failure rate actively |
| Free hosting tier eviction or resource exhaustion causes data loss | System | High — all user data could be lost permanently | Medium — free tiers have unpredictable longevity | Implement periodic data export capability (noted in business doc as a consideration); document recovery procedure |
| Telegram API changes or policy updates break the bot | System | High — entire delivery channel is external and uncontrolled | Low — Telegram Bot API is stable but not guaranteed | Monitor Telegram changelog; design message handling to be loosely coupled to API specifics |
| Accidental parameter deletion with no undo mechanism | Behavioral | Medium — individual user loses tracking history | Medium — deletion is a normal user action without a confirmation step | Add a confirmation prompt before deletion; consider a short-window soft-delete with undo |
| Scope creep beyond MVP boundary | Business | Medium — developer time and system complexity increase | High — single-developer projects with personal users are vulnerable to ad hoc feature requests | Enforce strict MVP boundary; maintain a documented out-of-scope list; version gate new features |
| Parameter name collision or ambiguity within a user's data | System | Medium — wrong data logged silently or query returns wrong parameter | Low-Medium — users naturally use varied naming | Define a case-insensitive exact-match or prefix-match rule; surface ambiguity to user when detected |
| Onboarding demo data contaminating real user analytics | System | Low-Medium — charts and comparisons would show misleading data | Low if assumption A-03 is validated | Confirm demo data isolation; tag synthetic entries distinctly |
| PendingClarification race condition when user sends new message while clarification is open | System | Medium — incorrect data logged or message lost | Medium — users frequently send follow-up messages before a bot responds | Define explicit priority rule: new message cancels open clarification, or open clarification blocks new commands |
| Single developer as sole operator creates bus factor risk | Business | High — system has no operational continuity if developer is unavailable | Low (personal project scope) | Document operational procedures; consider basic runbook for restart/recovery |
| Insufficient data points for meaningful charts or comparisons | Behavioral | Low — user receives an uninformative response | High in early use (users have few log entries) | Define minimum data point threshold; return informative message if chart cannot be meaningfully generated |

---

## 10. Logical Consistency Check

**Are there gaps in lifecycle?**
Yes — two gaps are identified:
- The User entity has no defined exit from the Active state. No deactivation, removal, or data expiry mechanism is defined. This is acceptable for a closed personal-scale system but should be explicitly acknowledged.
- The PendingClarification Abandoned state has no defined trigger for timeout. If no timeout is defined, a PendingClarification could remain Open indefinitely, blocking or confusing future interactions.

**Are any actors undefined?**
No. All three actors identified in the business document (Developer / Bot Owner, End User, Telegram Platform) are represented. No new actors have been introduced.

**Are there ambiguous states?**
Yes — two ambiguities are identified:
- The behavior of the system when a user sends a new message while a PendingClarification is Open is undefined. This creates an ambiguous state transition.
- The OnboardingSession Skipped state is assumed but not confirmed in the business document. If no skip mechanism exists, this state should be removed.

**Are there circular flows?**
No circular flows are present. All flows have defined entry triggers and terminal output states. The clarification loop (Flow 2 -> Flow 3) is a bounded retry, not a circular dependency, because it terminates in either Resolved or Abandoned.

---

## Version
v0.1

## Based On
Business v0.3

## Changes Introduced
- Initial system context document produced from approved business analysis v0.3
- System boundary defined explicitly, separating Telegram platform responsibilities from system responsibilities
- Seven core entities identified and described with ownership and lifecycle notes
- Nine interaction flows modeled from functional requirements
- Full state model constructed covering Parameter, LogEntry, PendingClarification, OnboardingSession, and User lifecycles
- Two external dependencies identified and characterized
- Eight assumptions surfaced and documented with risk and validation plans
- Ten risks identified and classified
- Logical consistency check performed; two lifecycle gaps and two state ambiguities flagged

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-01 | Telegram is the exclusive delivery channel | Carried from Business v0.3 | v0.1 | Confirmed |
| D-02 | Identity model is Telegram ID only; no PII | Carried from Business v0.3 | v0.1 | Confirmed |
| D-03 | Parse failures acceptable — fallback to manual clarification prompt | Carried from Business v0.3 | v0.1 | Confirmed |
| D-04 | Onboarding uses demo parameters with fake historical data | Carried from Business v0.3 | v0.1 | Confirmed |
| D-05 | Threshold alerts out of scope | Carried from Business v0.3 | v0.1 | Confirmed |
| D-06 | Charts are static PNG images in Telegram chat; image recognition not in scope | Carried from Business v0.3 | v0.1 | Confirmed |
| SD-01 | PendingClarification entity introduced to model parse failure state | Required to represent the bounded wait state between parse failure and user response | v0.1 | New — requires developer confirmation |
| SD-02 | Parameter deletion behavior (hard-delete vs. soft-delete) is unresolved | Business document states history is deleted with the parameter but does not specify implementation semantics | v0.1 | Open |

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| U-01 | Behavioral | Onboarding interrupt behavior is undefined — what happens if first message is a valid log command | Medium — may block or confuse first-time users | Developer to specify; update onboarding flow definition |
| U-02 | Behavioral | PendingClarification timeout duration is not defined | Medium — open clarifications may persist indefinitely | Developer to define timeout rule and abandoned state trigger |
| U-03 | Data | Whether demo onboarding parameters are ephemeral or persistent is not specified | Medium — analytics accuracy depends on this | Developer to confirm; update entity model accordingly |
| U-04 | Data | Default or configurable value of N in "last N entries" history query is unspecified | Low-Medium — affects usability of history responses | Developer to define N; document as system configuration |
| U-05 | Behavioral | Behavior when a new user message arrives while a PendingClarification is Open is undefined | Medium — risk of incorrect data logging or lost messages | Developer to define priority rule for competing message states |

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Unified tracking inside Telegram | Flow 1 (Successful Metric Logging), Flow 2 (Parse Failure), User entity, Parameter entity | High parse failure rate reduces unification value |
| User-defined parameters, no predefined categories | Parameter entity (auto-created on first use), Flow 1 | Parameter proliferation from auto-creation |
| Data isolated per Telegram ID | User entity (Telegram ID as sole key), all entities scoped by User ID | Telegram ID stability (A-01) |
| Log of last N entries | Flow 4 (Parameter History Query), LogEntry entity | Undefined N value (U-04) |
| Trend chart as static PNG in Telegram | Flow 5 (Trend Chart Generation), Chart entity | Insufficient data points for meaningful chart |
| Period comparison (week / month) | Flow 6 (Period Comparison) | Sparse data producing misleading comparisons |
| Parse failure fallback to clarification | Flow 2, Flow 3, PendingClarification entity and states | Race condition on competing messages (U-05) |
| Onboarding with demo data | Flow 9 (First-Time Onboarding), OnboardingSession entity | Demo data contamination (A-03, U-03) |
| Developer learning and portfolio value | All flows demonstrate stateful architecture, multi-user isolation, NLP parsing, chart delivery | Scope creep risk |
| MVP delivered within 3 months on near-zero budget | External dependency on free hosting infrastructure | Free tier instability and data loss risk |