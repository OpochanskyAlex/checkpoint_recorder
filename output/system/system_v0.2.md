# System Context Document

## Reviewed Business Version
v0.3

---

## 1. System Purpose

The system is a Telegram-based personal metric tracking bot serving a closed group of up to approximately 100 personally known users. Its responsibility is to accept free-text messages from users via Telegram, route those messages through a keyword-based dispatch model, parse log-intent messages to extract user-defined metric names and values, persist those records in isolated per-user storage, and respond with structured confirmations, query results, or static chart images.

The system removes the friction of dedicated tracking apps by operating inside a communication channel the target users already use daily. The system has no monetization goal and exists to deliver personal utility and serve as a portfolio demonstration of stateful bot architecture.

**Scope note (Fact):** This document assumes full functional scope as described in Business v0.3. Business Open Question 1 — the formal definition of minimum viable scope — remains outstanding at the business layer. If the MVP scope is subsequently constrained, this system context document will require a targeted revision to reflect the reduced boundary. No system design work dependent on the full scope boundary should be treated as final until MVP scope is confirmed.

---

## 2. Actors

| Actor | Type (Internal/External) | Responsibility | Risk if Misaligned |
|---|---|---|---|
| Developer / Bot Owner | Internal | Builds, deploys, operates, and maintains the system; primary user; defines scope boundaries; holds the API token and hosting credentials | Single point of failure for all operations and decisions; scope creep risk; bus factor risk for operational continuity |
| End User (Friend) | External | Sends free-text tracking messages; manages own parameters; queries history and charts; may request account deletion | Low logging consistency defeats success metrics; unexpected input patterns increase parse failure rate; ignored clarification prompts inflate unresolved parse failure count |
| Telegram Platform | External | Delivers messages between users and the bot; enforces delivery rate limits; renders static PNG images in chat; provides Telegram ID as the identity token | Platform policy changes, downtime, or rate-limit enforcement can make the system inaccessible to all actors |

---

## 3. System Boundaries

### Inside the System
- Receiving messages from users via Telegram
- Dispatching inbound messages through the keyword-based command router
- Parsing free-text log-intent input to extract parameter name and numeric value
- Generating a one-shot clarification prompt when parsing fails
- Creating a new parameter record automatically on first successful log use
- Persisting log entries per user, per parameter, with timestamp
- Enforcing data isolation: all storage reads and writes are scoped by the Telegram ID received from the platform delivery layer; no cross-user query path exists
- Listing a user's own active parameters
- Returning the last N log entries for a parameter
- Generating a static PNG trend chart on demand and sending it in Telegram chat; charts are not persisted after delivery
- Executing period comparison (week / month) logic
- Deleting a parameter and its full history on user request
- Accepting account deletion requests; enforcing a 3-day restoration window before permanent data purge
- Executing onboarding flow: presenting demo parameters with fake historical data to first-time users; demo data is tagged as synthetic and excluded from all analytics
- Guiding first-time users to add one real parameter
- Recording every inbound message as a ParseAttempt for observability purposes
- Storing the Telegram Bot API token as an environment variable; the token must not appear in source code or version control

### Outside the System
- Telegram client rendering (controlled by Telegram)
- User identity verification beyond Telegram ID (no PII collected or verified)
- Threshold alert and push notification mechanisms (confirmed out of scope, D-05)
- External API integrations
- Voice input processing
- Multi-language support
- Machine learning predictions
- Image recognition
- Monetization logic
- Chart storage after delivery (charts are generated on demand and discarded after sending)

### Boundary Assumptions
1. Telegram acts as the sole delivery and identity layer; no alternative input channel exists or is planned.
2. The system identifies users exclusively by their Telegram ID; no mapping to real-world identity is performed.
3. Static PNG charts are generated internally on demand and delivered as Telegram messages; no external charting service is used; charts are not stored after delivery.
4. All persistent data (User, Parameter, LogEntry, PendingClarification, ParseAttempt, OnboardingSession) resides within the system boundary; no third-party data processors are in scope.
5. The onboarding flow is triggered automatically on the first message from an unrecognized Telegram ID.
6. The Telegram Bot API token is the sole secret the system holds; it is stored as an environment variable at the hosting layer.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships |
|---|---|---|---|
| User | Represents a participant identified by Telegram ID | Telegram ID (primary identifier), onboarding status, first_seen_at timestamp, last_active_at timestamp, is_pending_deletion flag, deletion_requested_at timestamp | Owns zero or more Parameters; owns zero or more LogEntries; owns zero or more ParseAttempts |
| Parameter | A user-defined trackable metric | Parameter ID, name (user-defined string), owning User ID, creation_at timestamp, last_entry_at timestamp, active/deleted status | Belongs to one User; has zero or more LogEntries |
| LogEntry | A single recorded measurement for a parameter | Entry ID, Parameter ID, User ID, raw input text, parsed value, unit (if present), entry_at timestamp | Belongs to one Parameter and one User |
| ParseAttempt | A record of every attempted parse of a user message; created for all inbound messages regardless of outcome | Attempt ID, User ID, raw input text, parse outcome (success / failure / clarification_needed), timestamp | Associated with one User; a successful ParseAttempt produces a LogEntry; a failed ParseAttempt may produce a PendingClarification |
| PendingClarification | A transient state representing an unanswered one-shot clarification prompt sent after a parse failure | Clarification ID, User ID, original raw input, clarification prompt text, sent_at timestamp, state (open / resolved / abandoned) | Belongs to one User; resolves into either a LogEntry (Resolved) or is abandoned if the user ignores the prompt or sends a new message |
| OnboardingSession | Tracks the onboarding state of a first-time user | Session ID, User ID, demo parameters shown flag, real parameter added flag, completion_at timestamp | Belongs to one User |

**Ownership notes:**
- All entities are owned by the User identified via Telegram ID.
- Demo parameters presented during onboarding are tagged as synthetic and are not stored as real Parameter records. They are excluded from all LogEntry counts, charts, and comparisons.
- Deleting a parameter purges all associated LogEntries immediately (hard-delete). This is a consequential, irreversible operation; a confirmation step is required before execution (see Flow 8).
- When a User's account is in Pending Deletion state, no new log entries or commands are accepted except a restoration request. After the 3-day window, the User and all associated data are permanently purged.

**Lifecycle relevance:**
- A Parameter transitions through: Non-existent → Active → Deleted.
- A LogEntry is immutable once created; it is purged only when its parent Parameter is deleted.
- A PendingClarification is transient and one-shot: it exists between a parse failure and either the user's response or the user sending a new message. It does not persist beyond its resolution or abandonment.
- A User transitions through: New → Onboarding → Active → (optionally) Pending Deletion → Deleted.

**Entity removed from v0.1:**
- The Chart entity has been removed as a persistent construct. Charts are generated on demand at request time and delivered directly via Telegram. No Chart record is written to storage. The generation timestamp and chart parameters do not need to be persisted.

---

## 5. Command Dispatch Model

**Purpose:** This section describes how the system determines the intent of every inbound message before processing. This is the system's highest-complexity routing responsibility.

### Dispatch Priority Order

Every inbound message from a user is evaluated in the following order:

1. **Pending Clarification Check (highest priority):** If the user has an open PendingClarification, the incoming message is routed to the clarification resolution handler. The open PendingClarification is marked Abandoned. The new message is then processed as a fresh input from step 2 below. *(Rationale: the one-shot model, per SD-003. The user's new message takes precedence; the original unresolved input is discarded.)*

2. **Account State Check:** If the user's account is in Pending Deletion state, all commands except an explicit restoration command are rejected with an informative message.

3. **Command Keyword Match:** The leading token(s) of the message are compared against the reserved command vocabulary:

| Keyword(s) | Routed Flow |
|---|---|
| `list`, `show parameters` | Flow 7: Parameter List Query |
| `history`, `log`, `show [name]` | Flow 4: Parameter History Query |
| `chart`, `graph`, `plot` | Flow 5: Trend Chart Generation |
| `compare`, `vs`, `versus` | Flow 6: Period Comparison |
| `delete [name]` | Flow 8: Parameter Deletion |
| `delete account`, `remove account` | Flow 10: Account Deletion Request |
| `restore account` | Flow 11: Account Restoration |
| `help`, `start` | Onboarding or help text |

4. **Log Intent (default):** If no keyword matches and no special state is active, the message is treated as a log command and passed to the parse engine (Flows 1–3).

### Parse Engine (Conceptual)

The parse engine attempts to extract a parameter name and a numeric value from the free-text message. The strategy is pattern-based: the engine scans the message for a recognizable numeric token (integer or decimal) and associates the remaining text as the parameter name. Unit tokens (e.g., "kg", "L", "km") adjacent to the numeric token are captured if present.

- A ParseAttempt record is created for every message reaching the parse engine, regardless of outcome.
- If extraction succeeds → Flow 1 (Successful Metric Logging).
- If extraction fails → Flow 2 (Parse Failure and Clarification).
- Per SD-007: a failed ParseAttempt is one-shot. The user may manually categorize the entry by re-sending a corrected message at any time; the system does not retry or reprocess the original failed input.

---

## 6. Data and Interaction Flows

### Flow 1: Successful Metric Logging
- **Trigger:** User sends a message routed to the parse engine; parse engine successfully extracts a parameter name and numeric value
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** Parse engine extracts parameter name and value; a ParseAttempt record is created with outcome = success; the system checks whether the parameter already exists for this user; if not, a new Parameter record is created; a new LogEntry is appended with the parsed value, unit (if present), and timestamp; Parameter.last_entry_at is updated; User.last_active_at is updated; a confirmation message is sent to the user
- **Output:** Confirmation message in Telegram chat; new LogEntry stored; ParseAttempt stored; optionally new Parameter created
- **Risk Points:** Parse logic may produce false positives (wrong parameter name or value inferred); auto-creation of parameters on every message may produce unwanted parameter proliferation; storage write failure must be handled explicitly (see Section 9)

### Flow 2: Parse Failure and One-Shot Clarification
- **Trigger:** User sends a message routed to the parse engine; parse engine cannot extract a valid parameter-value pair
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** Parse engine fails to extract a valid pair; a ParseAttempt record is created with outcome = failure; the system creates a PendingClarification record in Open state; the system sends a single clarification prompt to the user asking them to specify the parameter name and value explicitly; User.last_active_at is updated
- **Output:** One-shot clarification prompt sent to user in Telegram chat; PendingClarification record created in Open state; ParseAttempt stored
- **Risk Points:** The user may ignore the prompt; per SD-003, the system does not re-prompt — the record is abandoned if unaddressed; the user can re-send the original message at any time to trigger a new ParseAttempt; high parse failure rates reduce usability

### Flow 3: Clarification Resolution
- **Trigger:** User responds to the clarification prompt with a corrected or structured entry
- **Actor:** End User
- **Input:** User's clarifying message in Telegram, while PendingClarification is Open
- **System Processing:** Per the Dispatch Model (Section 5), the Open PendingClarification intercepts the message first; the incoming message is sent to the clarification resolution handler; the PendingClarification is marked Abandoned; the new message is then processed as a fresh input through the dispatch model (steps 2–4); if the new message parses successfully, a LogEntry is created; confirmation is sent
- **Output:** Confirmation message if new message parses successfully; PendingClarification marked Abandoned; new ParseAttempt and optionally new LogEntry created
- **Risk Points:** The clarification response may itself fail to parse, producing a new PendingClarification; this is handled by repeating Flow 2

### Flow 4: Parameter History Query
- **Trigger:** User sends a message matched to the history/log keyword(s)
- **Actor:** End User
- **Input:** User request specifying a parameter name
- **System Processing:** User.last_active_at is updated; the system identifies the requesting user via Telegram ID; retrieves the most recent N LogEntries for the named parameter belonging to that user; formats results as a readable list message; N is a fixed system default (to be configured by developer, see A-08)
- **Output:** Formatted list of recent entries sent in Telegram chat
- **Risk Points:** Parameter name must match exactly or approximately to what the user typed; if multiple similarly named parameters exist, the system must surface ambiguity to the user rather than silently selecting one

### Flow 5: Trend Chart Generation
- **Trigger:** User sends a message matched to the chart/graph/plot keyword(s)
- **Actor:** End User
- **Input:** User request specifying a parameter name and optionally a time period
- **System Processing:** User.last_active_at is updated; the system retrieves all relevant LogEntries for the named parameter within the requested or default period; generates a static PNG chart image in memory; sends the image as a Telegram message; the chart is not stored after delivery; if chart generation fails or exceeds the latency threshold, an error message is returned (see Section 9)
- **Output:** Static PNG chart image delivered in Telegram chat; no Chart entity is persisted
- **Risk Points:** If there are too few data points, the chart may be uninformative; a minimum data point threshold must be defined and enforced; chart generation must complete within the latency target (see Section 8)

### Flow 6: Period Comparison
- **Trigger:** User sends a message matched to the compare/vs/versus keyword(s)
- **Actor:** End User
- **Input:** User request specifying parameter name and comparison period type (week or month)
- **System Processing:** User.last_active_at is updated; the system retrieves LogEntries for the named parameter grouped by the two most recent comparable periods; computes summary statistics for each period; formats a comparison response; if either period contains insufficient data, the system returns an explicit informative message rather than a potentially misleading comparison
- **Output:** Comparison summary message sent in Telegram chat
- **Risk Points:** Sparse data in one or both periods must be communicated explicitly; no silent or partial comparison output is acceptable

### Flow 7: Parameter List Query
- **Trigger:** User sends a message matched to the list/show parameters keyword(s)
- **Actor:** End User
- **Input:** User request
- **System Processing:** User.last_active_at is updated; the system retrieves all active Parameters belonging to the requesting user; formats them as a list
- **Output:** List of active parameter names sent in Telegram chat
- **Risk Points:** If a user has many parameters, the response may be verbose; no pagination mechanism is defined at this scale

### Flow 8: Parameter Deletion
- **Trigger:** User sends a message matched to the delete [name] keyword pattern
- **Actor:** End User
- **Input:** User request specifying the parameter name to delete
- **System Processing:** User.last_active_at is updated; the system identifies the named parameter for the requesting user; sends a confirmation prompt to the user explicitly stating that deletion is permanent and all history will be removed; if the user confirms, the Parameter is hard-deleted and all associated LogEntries are permanently purged; a deletion confirmation message is sent; if the user does not confirm, no deletion occurs
- **Output:** Confirmation prompt sent; on user confirmation: Parameter and all LogEntries permanently deleted; deletion confirmation message sent
- **Risk Points:** Deletion is irreversible; a two-step confirmation is mandatory; accidental confirmation results in permanent data loss

### Flow 9: First-Time Onboarding
- **Trigger:** System receives first message from an unrecognized Telegram ID
- **Actor:** End User (new)
- **Input:** Any first message sent to the bot
- **System Processing:** The system detects that this Telegram ID has no existing User record; creates a new User record; creates an OnboardingSession; presents demo parameters with synthetic fake historical data clearly labeled as demo content; prompts the user to add one real parameter; if the user's first message is a valid log command (parseable), the system processes it as a log entry and marks onboarding as completed in parallel; demo data is tagged synthetic and excluded from all future analytics
- **Output:** Welcome and demo content delivered in Telegram chat; User record created; OnboardingSession created and completed or in-progress
- **Risk Points:** Demo data must be unambiguously labeled as synthetic to prevent confusion with real data; if the user's first message is a valid log command, processing it and completing onboarding concurrently prevents blocking

### Flow 10: Account Deletion Request
- **Trigger:** User sends a message matched to the delete account / remove account keyword pattern
- **Actor:** End User
- **Input:** User request to delete account
- **System Processing:** User.last_active_at is updated; the system sends a confirmation prompt explicitly stating: all data (parameters, log entries, history) will be permanently deleted after 3 days; the user may restore the account within 3 days; if confirmed, the User is placed in Pending Deletion state; deletion_requested_at is set; the system sends a confirmation message with the restoration deadline
- **Output:** Confirmation prompt sent; on user confirmation: User state set to Pending Deletion; confirmation message with 3-day restoration window sent
- **Risk Points:** User must understand the 3-day window is their only recovery path; the system must enforce the state change and block new commands during Pending Deletion

### Flow 11: Account Restoration
- **Trigger:** User sends a message matched to the restore account keyword pattern while in Pending Deletion state
- **Actor:** End User
- **Input:** Restoration request during the 3-day window
- **System Processing:** The system verifies that the account is in Pending Deletion state and that the 3-day window has not expired; clears the is_pending_deletion flag and deletion_requested_at timestamp; restores the User to Active state; sends a restoration confirmation message
- **Output:** Account restored to Active state; all data remains intact; restoration confirmation message sent
- **Risk Points:** If the 3-day window has expired before the user sends this command, restoration is not possible; the system must return an explicit message indicating that data has been permanently purged

---

## 7. State Model

### Parameter States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Non-existent | System start, or no message ever sent for this parameter name | User sends a parseable log message with a new parameter name | Active | Auto-creation may generate unwanted parameters from mistyped or incidental messages |
| Active | Parameter record created via successful log entry | User sends a confirmed delete request for this parameter | Deleted | Accidental deletion has no undo mechanism; two-step confirmation is required |
| Deleted | User deletion confirmed and parameter hard-deleted | (terminal — no recovery path) | None (terminal) | All associated LogEntries are permanently purged on deletion |

### LogEntry States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Recorded | Successful parse and storage of a metric value | Parent Parameter deletion (cascades) | Purged | Immutability means errors cannot be corrected by the user; the user must re-enter with a new log command |
| Purged | Parent Parameter is hard-deleted | (terminal) | None (terminal) | Permanent; no recovery |

### ParseAttempt States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Recorded | Every inbound message reaching the parse engine | (terminal — immutable audit record) | None (terminal) | Audit record is append-only; it is purged only on User account deletion |

### PendingClarification States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| Open | Parse attempt fails; one clarification prompt sent to user | User sends any new message (see note); or user explicitly responds to the prompt | Abandoned (new message received) / Resolved (clarification response parses successfully) / Abandoned (clarification response also fails to parse) | One-shot model per SD-003; original unprocessed message is lost; user must re-send |
| Resolved | User's clarification response is successfully processed as a new ParseAttempt and LogEntry | (terminal) | None (terminal) | Correct dispatch of the clarification response through the standard flow is required |
| Abandoned | User sends any new message while clarification is Open (the new message triggers a dispatch and the Open clarification is closed first); or the user's clarification response itself fails to parse | (terminal) | None (terminal) | No re-prompt; no retry; the user must re-initiate if they wish to log the original data |

**Note on one-shot model (SD-003 and SD-007):** The system sends exactly one clarification prompt. If the user ignores it or sends an unrelated message, the PendingClarification is marked Abandoned. The user retains the ability to re-send the original message at any time, which triggers a fresh ParseAttempt through the standard dispatch.

### OnboardingSession States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| In Progress | First message received from an unrecognized Telegram ID | User adds a real parameter; or user's first message is a valid log command (auto-completes onboarding) | Completed | If the user never adds a real parameter, the OnboardingSession remains In Progress but does not block further interactions |
| Completed | User has added at least one real parameter during onboarding, or first message was processed as a log command | (terminal) | None (terminal) | None identified |

### User States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| New | First message received from an unrecognized Telegram ID | Onboarding session is created | Onboarding | No pre-registration mechanism exists |
| Onboarding | Onboarding session created | Onboarding session reaches Completed state | Active | User can interact with the system during onboarding; commands are not blocked |
| Active | Onboarding complete; User is interacting with the system | User sends a confirmed account deletion request | Pending Deletion | No passive deactivation or expiry mechanism is defined |
| Pending Deletion | User has confirmed an account deletion request; 3-day restoration window is active | User sends a restoration command within 3 days; or 3-day window expires | Active (if restored within window) / Deleted (if window expires) | Only a restoration command can reverse this state; all other commands are rejected during this window |
| Deleted | 3-day Pending Deletion window has expired without a restoration request | (terminal — all data purged) | None (terminal) | Permanent; no recovery path; user must be informed of finality during the deletion flow |

---

## 8. Non-Functional Requirements

### 8.1 Performance

| Target | Definition | Condition | Risk |
|---|---|---|---|
| Text response latency | The system must send an acknowledgement or response to a log, query, or command message within 3 seconds | Under normal load at max scale (≤ 100 active users) | Telegram cold start on free hosting tier may exceed this target; first-message latency after idle is not bounded by this target |
| Chart generation latency | The system must deliver a chart image within 15 seconds of the request | Under normal load | If the 15-second bound is exceeded, the system must return an error message rather than silently fail or timeout within Telegram's window |

### 8.2 Availability

- **Target:** Best-effort availability; no formal SLA. Targeted at >90% daily availability.
- **Rationale:** Free hosting tier provides no uptime guarantee. Downtime is acknowledged as acceptable for this personal-scale system.
- **Cold start behavior:** After an idle period, the first inbound message may trigger a process cold start. The response latency target does not apply to cold-start recovery. Users will experience a delay; no notification is sent.

### 8.3 Data Durability

- **Recovery Point Objective (RPO):** Maximum acceptable data loss window is 24 hours.
- **Mechanism:** A periodic export or backup of all stored data must be available. The developer is responsible for executing or automating this at a minimum daily frequency. The export is the primary mitigation against free-tier storage eviction or data loss.
- **Scope note:** The export mechanism is an operational procedure, not a user-facing feature.

### 8.4 Data Volume Estimate

At maximum scale: 100 users × 5 messages/day × 365 days = ~182,500 records/year across all entities. This is a trivially small data volume. The storage mechanism must support relational lookup (queries scoped by User ID) and sequential retrieval (sorted by timestamp) but does not require horizontal scaling, partitioning, or caching.

### 8.5 Message Volume and Rate Limits

- **Estimated peak:** 100 users × 5 messages/day = ~500 messages/day ≈ 0.006 messages/second average. Peak bursts may reach 5–10 messages/minute.
- **Telegram rate limits:** Telegram enforces approximately 30 outbound messages/second globally and 1 message/second per individual chat. At estimated peak load, the system operates well within these limits.

### 8.6 Error Communication

- **Requirement (Fact):** The system must return a human-readable error message for every failure path. No message may be silently dropped without a user-visible response.
- **Scope:** This applies to: parse failures, storage failures, chart generation failures, invalid commands, empty query results, and deletion rejections.

### 8.7 Input Constraints

- **Parameter name length:** Parameter names must be bounded in length. Names exceeding the bound are rejected with an informative message. The exact bound is to be defined by the developer; a recommended upper limit is 100 characters.
- **Character set:** Parameter names and values containing characters that cause storage or display anomalies must be sanitized or rejected with an informative message.

---

## 9. Failure Behavior Contract

This section defines the expected system behavior for the three highest-risk failure scenarios. These are system-level decisions, not open questions.

### 9.1 Storage Write Failure (Flows 1, 8, 10, 11)
- **Scenario:** The system attempts to write a LogEntry, Parameter, or User state change and the storage operation fails.
- **Behavior:** The system returns an explicit error message to the user (e.g., "Your entry could not be saved. Please try again."). No confirmation message is sent. The entity is not partially written. The user is instructed to retry.
- **Rationale:** A false confirmation — confirming a save that did not occur — corrupts the user's trust and silently distorts success metrics.

### 9.2 Chart Generation Failure (Flow 5)
- **Scenario:** The chart generation process fails (e.g., insufficient data points, internal error) or exceeds the 15-second latency target.
- **Behavior:** The system returns an explicit error message to the user (e.g., "Chart could not be generated. There may be insufficient data, or a temporary error occurred."). No image is sent. No partial or empty message is sent.
- **Minimum data point requirement:** If a parameter has fewer than 2 LogEntries in the requested period, the system returns an informative message (e.g., "Not enough data to generate a chart for this period.") rather than attempting chart generation.

### 9.3 Bot Startup with Open PendingClarifications
- **Scenario:** The bot process restarts (planned or after a crash) and finds PendingClarification records in the Open state in storage.
- **Behavior:** On startup, all PendingClarification records in Open state are marked Abandoned by the system. No notification is sent to affected users. Users whose clarification prompts are abandoned retain the ability to re-send their original message at any time, which triggers a fresh ParseAttempt through the standard dispatch.
- **Rationale:** Leaving Open PendingClarifications after a restart creates an ambiguous routing state for the first subsequent message from each affected user. Proactive abandonment on startup produces a clean, defined state.

### 9.4 Period Comparison with Sparse Data (Flow 6)
- **Scenario:** One or both periods in a comparison request contain fewer than 2 LogEntries.
- **Behavior:** The system returns an explicit informative message indicating which period lacks sufficient data. A partial or misleading comparison is never returned.

---

## 10. Security and Data Controls

### 10.1 Data Isolation Enforcement
- **Control:** All storage queries must include the Telegram ID received from the platform delivery layer as a mandatory filter. No query path that could return data belonging to a different User ID is permitted.
- **Risk:** A routing or query logic defect that omits the User ID filter would expose one user's data to another. This is the highest-impact security failure mode for this system.

### 10.2 Secrets Handling
- **Control:** The Telegram Bot API token is the sole secret the system holds. It must be stored as an environment variable at the hosting layer. It must not appear in source code, configuration files committed to version control, or any log output.
- **Assumption:** The hosting platform provides a mechanism for injecting environment variables into the bot process at runtime.

### 10.3 Demo Data Isolation
- **Control:** Demo parameters and their synthetic data created during onboarding are tagged with a `is_synthetic` flag. All analytics flows (chart generation, history queries, period comparison) must filter out entries with this flag. No synthetic data appears in any user-facing output outside of the explicit onboarding context.

### 10.4 Operator Data Access
- **Fact:** The developer, as the sole operator, has unrestricted access to all raw user data stored in the system. Users in this closed group are personally known to the developer. No technical access control separating the developer from user data is defined. This is acknowledged as a trust and expectation management concern. Users should be informed of this condition at onboarding time.

---

## 11. Observability Model

### 11.1 Parse Failure Rate (Primary Success Metric)
- **Signal:** Every ParseAttempt record carries an outcome field (success / failure / clarification_needed).
- **Measurement:** The parse failure resolution rate is computed as: (count of ParseAttempts with outcome = success OR PendingClarification.state = resolved) / (total ParseAttempts) over a rolling 30-day window.
- **Target:** >80% resolution rate as defined in Business v0.3.
- **Access:** The developer queries the ParseAttempt table directly; no automated alerting is required at this scale.

### 11.2 User Return Rate (Primary Success Metric)
- **Signal:** User.last_active_at is updated on every inbound message processed.
- **Measurement:** The User Return Rate is computed as: (count of Users with at least one interaction in week 2 after first_seen_at) / (count of Users with at least one interaction in week 1) over a rolling cohort window.
- **Target:** >40% as defined in Business v0.3.

### 11.3 Parameter Retention Rate (Primary Success Metric)
- **Signal:** Parameter.last_entry_at is updated on every successful LogEntry creation.
- **Measurement:** Parameters active at day 30 are those with at least one LogEntry in the days 25–35 window. Retention rate = (count of such parameters) / (count of Parameters created before day 5).
- **Target:** >50% at day 30 as defined in Business v0.3.

### 11.4 Bot Availability
- **Signal:** No automated health check mechanism is defined for this personal-scale system. Bot availability is monitored manually by the developer through periodic direct interaction.
- **Operational note:** A process crash results in silent unavailability; the developer should establish a minimum check frequency (e.g., once per day) to detect extended outages.

### 11.5 Storage Utilization
- **Signal:** The developer monitors storage consumption against the free-tier quota manually.
- **Threshold:** If storage approaches 80% of the free-tier limit, a data export and cleanup procedure should be initiated.

### 11.6 Error Rate by Flow
- **Signal:** ParseAttempt records cover parse-layer failures. Storage write failures and chart generation failures produce user-visible error messages; the developer can review error rates by inspecting system logs.
- **Minimum requirement:** The system must log every failure path with sufficient context (User ID, flow name, error type) to enable the developer to diagnose recurring issues.

---

## 12. External Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Platform | Message delivery, user identity (Telegram ID), image display, chat interface, rate limit enforcement | Hard dependency — system cannot function without it | High — any Telegram outage, API change, or policy change makes the system completely inaccessible |
| Free Hosting Infrastructure | Runtime environment for the bot process and persistent data storage | Hard dependency — system cannot run without a host | Medium — free tier limits (memory, CPU, uptime, storage quotas) may cause degraded or interrupted service; data loss risk on tier eviction; daily backup is the primary mitigation |

No third-party integrations are proposed. Dependencies are stated as they exist in the approved business document.

---

## 13. Assumptions

1. **A-01: Telegram ID is stable and unique per user.**
   - Why it exists: The entire identity model relies on Telegram ID as the sole identifier with no PII fallback.
   - Risk if false: If a user loses access to their Telegram account, all their data becomes inaccessible or orphaned. If IDs are ever reassigned (highly unlikely), data isolation could be violated.
   - Validation idea: Review Telegram platform documentation to confirm ID permanence guarantees.

2. **A-02: Free-text messages are the only input modality used.**
   - Why it exists: Business document explicitly excludes voice input and image recognition.
   - Risk if false: If users send voice notes or images to log data, the system will either ignore them or generate parse failures, causing user frustration.
   - Validation idea: Define explicit rejection messages for non-text inputs; observe actual user behavior in the first weeks post-launch.

3. **A-03: Demo parameters created during onboarding are synthetic and tagged; they are never co-mingled with real LogEntries.**
   - Why it exists: The business document states onboarding uses demo parameters with fake historical data; the system must prevent this data from contaminating real analytics.
   - Risk if false: Charts, comparisons, and history queries will include synthetic values, producing misleading output.
   - Validation idea: Confirm the `is_synthetic` tagging mechanism is applied at creation time and that all analytics flows enforce the filter.

4. **A-04: Deleting a parameter purges all associated LogEntries immediately (hard-delete).**
   - Why it exists: The business document states deletion removes a parameter "along with its history." A two-step confirmation step is added to mitigate accidental loss.
   - Risk if false: If soft-delete semantics were introduced without storage cleanup, storage would grow indefinitely.
   - Validation idea: Developer to confirm deletion semantics are hard-delete; verify the confirmation step is enforced in the deletion flow.

5. **A-05: The onboarding flow does not block valid log commands; if a user's first message is a parseable log command, the system processes it and marks onboarding as completed.**
   - Why it exists: Blocking users who know what they want to do from executing commands until onboarding is complete would create unnecessary friction for returning or experienced users.
   - Risk if false: If onboarding is mandatory and blocking, any user who bypasses the tutorial steps will be unable to use the system.
   - Validation idea: Developer to implement onboarding as a non-blocking parallel flow; test with a valid log command as the first message.

6. **A-06: The system can serve up to approximately 100 concurrent users within free hosting tier resource limits.**
   - Why it exists: The business document states the target scale is max ~100 users on free hosting tiers.
   - Risk if false: If actual concurrent usage spikes beyond what free tier resources support, the system may become unresponsive.
   - Validation idea: Estimate expected message volume against free tier resource limits; confirm before launch.

7. **A-07: Parse failure is defined as any message from which the parse engine cannot extract a valid parameter name and numeric value pair.**
   - Why it exists: The boundary between parseable and unparseable is not defined in the business document.
   - Risk if false: If the parse failure definition is too strict, valid inputs will generate unnecessary clarification prompts. If too loose, incorrect data will be logged silently.
   - Validation idea: Developer to document parse failure criteria; measure parse failure rate in first 30 days against the >80% resolution target.

8. **A-08: The "last N entries" for history queries uses a fixed system-default value of N, not user-configurable at query time.**
   - Why it exists: The business document specifies "last N entries" without defining N or whether it is configurable.
   - Risk if false: A fixed N that is too small renders history queries uninformative; a fixed N that is too large produces overly long Telegram messages.
   - Validation idea: Developer to define and document the default N value; consider allowing the user to specify N inline in their query message as a later enhancement.

9. **A-09: The hosting platform supports environment variable injection for the Telegram Bot API token.**
   - Why it exists: The secrets handling control (Section 10.2) requires that the token not be stored in source code.
   - Risk if false: If the hosting platform does not support environment variables, an alternative secrets storage mechanism must be defined before deployment.
   - Validation idea: Confirm environment variable support with the selected hosting provider before deployment.

---

## 14. Risks

| Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|
| High parse failure rate causes user abandonment | Behavioral | High — directly undermines core value proposition | Medium — free-text is inherently ambiguous | Invest in robust parse logic; define a clear message format guide for users; measure failure rate actively from day one |
| Free hosting tier eviction or resource exhaustion causes data loss | System | High — all user data could be lost permanently | Medium — free tiers have unpredictable longevity | Implement daily data export; document recovery procedure; inform users of the data durability posture at onboarding |
| Telegram API changes or policy updates break the bot | System | High — entire delivery channel is external and uncontrolled | Low — Telegram Bot API is stable but not guaranteed | Monitor Telegram changelog; maintain awareness of terms of service compliance |
| Accidental parameter deletion with no undo mechanism | Behavioral | Medium — individual user permanently loses tracking history | Medium — deletion is a normal user action | Two-step confirmation prompt is mandatory before any deletion; clearly state irreversibility in the prompt |
| Scope creep beyond MVP boundary | Business | Medium — developer time and system complexity increase | High — single-developer projects with personal users are vulnerable to ad hoc feature requests | Enforce strict MVP boundary; maintain documented out-of-scope list; treat additions as explicit scope change decisions |
| Parameter name collision or ambiguity within a user's data | System | Medium — wrong data logged silently or query returns wrong parameter | Low-Medium — users naturally use varied naming | Define a case-insensitive exact-match or prefix-match rule; surface ambiguity to user when detected |
| One-shot clarification model leads to silently lost data | Behavioral | Medium — user believes data was logged but it was abandoned after an ignored clarification | Medium — users may not respond to the clarification prompt promptly | Clarification prompt must clearly state the one-shot nature and instruct the user to re-send their original message if they wish to retry |
| Bot cold start on free-tier hosting causes silent first-message failure | System | Medium — user sends a message and receives no response during cold start | High — free-tier services frequently suspend idle processes | Document cold-start behavior; consider a scheduled keep-alive mechanism to reduce idle suspension frequency |
| Data isolation defect routes one user's data to another | System | High — privacy violation in a personal, trust-based system | Low — requires a specific query logic bug | Enforce mandatory User ID scoping on all queries; include data isolation in any testing checklist |
| Single developer as sole operator creates bus factor risk | Business | High — system has no operational continuity if developer is unavailable | Low (personal project scope) | Document operational procedures; maintain a basic runbook for restart and recovery |
| Insufficient data points for meaningful charts or comparisons | Behavioral | Low — user receives an uninformative response | High in early use (users have few log entries) | Minimum data point threshold enforced in Flows 5 and 6; return informative message if threshold not met |
| Account deletion 3-day window misunderstood by user | Behavioral | Medium — user expects immediate deletion and is confused by continued data presence, or expects longer window | Low | Deletion confirmation message must state the 3-day window explicitly and the exact expiry date/time |

---

## 15. Logical Consistency Check

**Are there gaps in lifecycle?**
One residual gap is identified:
- The User entity now has a defined exit path (Pending Deletion → Deleted) closing the gap from v0.1. No further lifecycle gap exists for User.
- The OnboardingSession has no explicit path out of In Progress if the user never adds a real parameter and never sends a valid log command. This is acceptable: the session remains In Progress but does not block system operation. It is explicitly noted as a non-blocking incomplete state.

**Are any actors undefined?**
No. All three actors (Developer / Bot Owner, End User, Telegram Platform) are represented. No new actors have been introduced.

**Are there ambiguous states?**
Two ambiguities from v0.1 are resolved:
- The PendingClarification race condition is resolved: the one-shot model means any new message from the user cancels an Open PendingClarification, which is marked Abandoned, and the new message is processed normally.
- The onboarding interrupt behavior is resolved: valid log commands during onboarding are processed normally and complete onboarding concurrently.

One residual ambiguity exists:
- The behavior when a user in Pending Deletion state sends a message other than a restoration command is defined (rejected with an informative message), but the exact message vocabulary for rejection is not specified. This is a detailed design decision deferred to the developer.

**Are there circular flows?**
No circular flows are present. All flows have defined entry triggers and terminal output states. The clarification loop (Flow 2 → Flow 3) is a bounded one-shot retry that terminates in either a new ParseAttempt (Resolved or Abandoned). The account deletion/restoration cycle (Flow 10 → Flow 11) is a bounded reversible state change, not a circular dependency.

---

## Version
v0.2

## Based On
Business v0.3

## Changes Introduced
- Added explicit MVP scope acknowledgement in Section 1 (addresses Mandatory Revision 10)
- Added Section 5: Command Dispatch Model covering keyword routing, parse engine conceptual description, and dispatch priority order (addresses Mandatory Revision 1)
- Added Section 8: Non-Functional Requirements covering latency, availability, RPO, data volume, message rate, error communication, and input constraints (addresses Mandatory Revision 3)
- Added Section 9: Failure Behavior Contract covering storage write failure, chart generation failure, bot startup with Open PendingClarifications, and sparse data comparison (addresses Mandatory Revision 4)
- Added Section 10: Security and Data Controls covering isolation enforcement, secrets handling, demo data isolation, and operator access (addresses Mandatory Revision 8 and security gaps from the review)
- Added Section 11: Observability Model covering parse failure rate, user return rate, parameter retention rate, bot availability, storage utilization, and error rate (addresses observability gaps from the review)
- Removed persistent Chart entity; charts are now on-demand generated and not stored; Flow 5 updated accordingly (addresses Mandatory Revision 7)
- ParseAttempt creation added explicitly to Flows 1 and 2; ParseAttempt state model added (addresses Mandatory Revision 6)
- PendingClarification one-shot model formalized per stakeholder responses SD-003 and SD-007; race condition resolved as an architectural decision (addresses Mandatory Revision 5 and U-05)
- User entity updated: added last_active_at, is_pending_deletion, deletion_requested_at attributes (addresses Mandatory Revision 9)
- Parameter entity updated: added last_entry_at attribute for Parameter Retention Rate observability
- User state model extended: added Pending Deletion and Deleted states per stakeholder response SD-004 (3-day restoration window)
- Flow 8 (Parameter Deletion) updated: two-step confirmation now mandatory
- Flow 10 (Account Deletion Request) and Flow 11 (Account Restoration) added per SD-004
- Onboarding interrupt behavior resolved in Flow 9 and OnboardingSession state model
- Assumption A-05 updated to reflect onboarding non-blocking resolution
- Assumption A-09 added for hosting environment variable support
- Risks updated: added cold-start risk, data isolation defect risk, one-shot clarification data loss risk, account deletion misunderstanding risk; removed PendingClarification race condition risk (resolved)
- Logical consistency check updated to reflect resolved ambiguities and residual items

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-01 | Telegram is the exclusive delivery channel | Carried from Business v0.3 | v0.1 | Confirmed |
| D-02 | Identity model is Telegram ID only; no PII | Carried from Business v0.3 | v0.1 | Confirmed |
| D-03 | Parse failures acceptable — fallback to one-shot clarification prompt | Carried from Business v0.3; one-shot semantics added per SD-003 | v0.2 | Updated |
| D-04 | Onboarding uses demo parameters with fake historical data tagged as synthetic | Carried from Business v0.3; synthetic tagging formalized in v0.2 | v0.2 | Updated |
| D-05 | Threshold alerts out of scope | Carried from Business v0.3 | v0.1 | Confirmed |
| D-06 | Charts are static PNG images generated on demand; not persisted | Carried from Business v0.3; persistence decision resolved in v0.2 as on-demand | v0.2 | Updated |
| SD-01 | PendingClarification entity models the one-shot clarification state | Formalized in v0.2; one-shot semantics per SD-003; race condition resolved | v0.2 | Confirmed |
| SD-02 | Parameter deletion is hard-delete with mandatory two-step confirmation | Hard-delete semantics confirmed; confirmation step added to prevent accidental loss | v0.2 | Confirmed |
| SD-03 | Account deletion includes a 3-day restoration window per SD-004 | User account deletion uses soft-delete with 3-day window before permanent purge | v0.2 | New — confirmed per stakeholder response |
| SD-04 | Command dispatch uses keyword-first routing with log intent as default | Resolves the command routing gap from v0.1; enables unambiguous intent identification | v0.2 | New |
| SD-05 | Charts are generated on demand and not persisted after delivery | Reduces storage complexity; chart data is always derivable from LogEntries | v0.2 | New |

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| U-01 | Behavioral | Onboarding interrupt behavior | **Resolved in v0.2:** valid log commands during onboarding are processed normally and complete onboarding concurrently | Closed |
| U-02 | Behavioral | PendingClarification one-shot model | **Resolved in v0.2:** per SD-003, one-shot prompt; new message abandons open clarification; user may re-send original at any time | Closed |
| U-03 | Data | Demo onboarding parameter persistence | **Resolved in v0.2:** demo parameters are synthetic-tagged and excluded from all analytics; never persisted as real Parameter records | Closed |
| U-04 | Data | Default value of N in "last N entries" history query | Still open — developer to define and document default N | Define N before launch; document as system configuration constant |
| U-05 | Behavioral | Race condition: new message while PendingClarification is Open | **Resolved in v0.2:** new message triggers abandonment of open clarification and is processed as fresh input | Closed |
| U-06 | Operational | Minimum data point threshold for chart generation | Open — developer to define the minimum number of LogEntries required to generate a meaningful chart | Define threshold before chart flow is implemented |

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Unified tracking inside Telegram | Flow 1 (Successful Metric Logging), Flow 2 (Parse Failure), User entity, Parameter entity | High parse failure rate reduces unification value |
| User-defined parameters, no predefined categories | Parameter entity (auto-created on first use), Flow 1 | Parameter proliferation from auto-creation; mitigated by two-step deletion |
| Data isolated per Telegram ID | User entity (Telegram ID as sole key), all entities scoped by User ID, Section 10.1 isolation control | Telegram ID stability (A-01); isolation defect risk |
| Log of last N entries | Flow 4 (Parameter History Query), LogEntry entity | Undefined N value (U-04) |
| Trend chart as static PNG in Telegram | Flow 5 (Trend Chart Generation), on-demand generation model | Insufficient data points for chart; mitigated by minimum threshold |
| Period comparison (week / month) | Flow 6 (Period Comparison) | Sparse data producing misleading comparisons; mitigated by explicit informative message |
| Parse failure fallback to clarification | Flow 2, Flow 3, PendingClarification one-shot model | One-shot model may result in lost entries if user ignores prompt |
| Onboarding with demo data | Flow 9 (First-Time Onboarding), OnboardingSession entity, synthetic tagging | Demo data contamination mitigated by is_synthetic flag |
| Parse failure resolution rate >80% | ParseAttempt entity and state, Section 11.1 observability | No automated alerting; manual measurement by developer |
| User Return Rate >40% at week 2 | User.last_active_at, Section 11.2 observability | No automated reporting; manual measurement by developer |
| Parameter Retention Rate >50% at day 30 | Parameter.last_entry_at, Section 11.3 observability | Derivable from LogEntry timestamps; no automated reporting |
| Developer learning and portfolio value | All flows demonstrate stateful architecture, multi-user isolation, NLP parsing, chart delivery | Scope creep risk |
| MVP delivered within 3 months on near-zero budget | External dependency on free hosting infrastructure; daily export as RPO mitigation | Free tier instability and data loss risk |
| Account deletion with user data rights | Flow 10, Flow 11, User Pending Deletion / Deleted states, 3-day restoration window | User misunderstanding of the 3-day window; mitigated by explicit confirmation message |
