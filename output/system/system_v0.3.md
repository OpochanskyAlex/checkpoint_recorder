# System Context Document

## Reviewed Business Version
v0.3

---

## 1. System Purpose

The system is a Telegram-based personal metric tracking bot serving a closed group of up to approximately 100 personally known users. Its responsibility is to accept free-text messages from users via Telegram, route those messages through a keyword-based dispatch model, parse log-intent messages to extract user-defined metric names and values, persist those records in isolated per-user embedded relational storage, and respond with structured confirmations, query results, or static chart images.

The system removes the friction of dedicated tracking apps by operating inside a communication channel the target users already use daily. The system has no monetization goal and exists to deliver personal utility and serve as a portfolio demonstration of stateful bot architecture.

**Scope note (Fact):** This document assumes full functional scope as described in Business v0.3. Business Open Question 1 — the formal definition of minimum viable scope — remains outstanding at the business layer. If the MVP scope is subsequently constrained, this system context document will require a targeted revision to reflect the reduced boundary. No system design work dependent on the full scope boundary should be treated as final until MVP scope is confirmed.

---

## 2. Actors

| Actor | Type (Internal/External) | Responsibility | Risk if Misaligned |
|---|---|---|---|
| Developer / Bot Owner | Internal | Builds, deploys, operates, and maintains the system; primary user; defines scope boundaries; holds the API token and hosting credentials | Single point of failure for all operations and decisions; scope creep risk; bus factor risk for operational continuity |
| Bot Operator / System Owner | Internal | Maintains system availability; monitors operational health; manages deployment and configuration; enforces data isolation | Single point of failure for all operational responsibilities (R-008). If unavailable, incidents are not resolved. |
| End User (Friend) | External | Sends free-text tracking messages; manages own parameters; queries history and charts; may request account deletion | Low logging consistency defeats success metrics; unexpected input patterns increase parse failure rate; ignored clarification prompts inflate unresolved parse failure count |
| Telegram Platform | External | Delivers messages between users and the bot; enforces delivery rate limits; renders static PNG images in chat; provides Telegram ID as the identity token | Platform policy changes, downtime, or rate-limit enforcement can make the system inaccessible to all actors |

---

## 3. System Boundaries

### Inside the System
- Receiving messages from users via Telegram
- Rejecting non-text Telegram inputs (voice notes, images, stickers, forwarded media) with an informative message; these message types are acknowledged but not processed by the parse engine
- Dispatching inbound text messages through the keyword-based command router
- Disambiguating keyword matches from log-intent messages according to the keyword collision rule (see Section 5)
- Parsing free-text log-intent input to extract parameter name and numeric value
- Generating a one-shot clarification prompt when parsing fails
- Creating a new parameter record automatically on first successful log use
- Persisting log entries per user, per parameter, with timestamp; using embedded relational storage co-located with the bot process
- Enforcing data isolation: all storage reads and writes are scoped by the Telegram ID received from the platform delivery layer; no cross-user query path exists
- Sanitizing all user-supplied input (parameter names, log values) before any storage operation; raw user input is never interpolated directly into storage queries
- Listing a user's own active parameters
- Returning the last N log entries for a parameter
- Generating a static PNG trend chart on demand and sending it in Telegram chat; charts are not persisted after delivery
- Executing period comparison (week / month) logic
- Deleting a parameter and its full history on user request
- Accepting account deletion requests; enforcing a 3-day restoration window before permanent data purge
- Executing a startup sweep on every bot process start to: (a) abandon all Open PendingClarification records, and (b) evaluate and execute pending account deletions whose 3-day window has expired
- Executing onboarding flow: presenting demo parameters with synthetic fake historical data clearly labeled as demo content to first-time users; demo data is tagged as synthetic and excluded from all analytics
- Guiding first-time users to add one real parameter; disclosing that the operator (developer) has unrestricted access to all stored data as part of the onboarding welcome message
- Recording every inbound message as a ParseAttempt for observability purposes
- Storing the Telegram Bot API token as an environment variable; the token must not appear in source code, version control, or log output
- Executing a periodic or scheduled data export of all stored data to a location outside the primary hosting environment; this is the sole mitigation for the 24-hour RPO

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
4. All persistent data (User, Parameter, LogEntry, PendingClarification, ParseAttempt, OnboardingSession) resides within the system boundary in embedded relational storage; no third-party data processors are in scope.
5. The onboarding flow is triggered automatically on the first message from an unrecognized Telegram ID.
6. The Telegram Bot API token is the sole secret the system holds; it is stored as an environment variable at the hosting layer and must never appear in log output.
7. The Telegram update delivery model (polling vs. webhook) is identified as a system-level decision affecting cold-start behavior and hosting requirements; it is logged as an open decision in the Decision Log (SD-10).
8. The data export is stored in a location external to and independent of the primary hosting environment (e.g., external file storage, email attachment, or developer-controlled storage); the exact destination is an operational procedure defined by the developer.

---

## 4. Core Entities

| Entity | Description | Key Attributes | Relationships |
|---|---|---|---|
| User | Represents a participant identified by Telegram ID | Telegram ID (primary identifier), onboarding status, first_seen_at timestamp, last_active_at timestamp, is_pending_deletion flag, deletion_requested_at timestamp | Owns zero or more Parameters; owns zero or more LogEntries; owns zero or more ParseAttempts |
| Parameter | A user-defined trackable metric | Parameter ID, name (user-defined string, bounded in length, sanitized), owning User ID, creation_at timestamp, last_entry_at timestamp, active/deleted status | Belongs to one User; has zero or more LogEntries |
| LogEntry | A single recorded measurement for a parameter | Entry ID, Parameter ID, User ID, raw input text, parsed value, unit (if present), entry_at timestamp | Belongs to one Parameter and one User |
| ParseAttempt | A record of every attempted parse of a user message; created for all inbound messages regardless of outcome | Attempt ID, User ID, raw input text, parse outcome (success / failure / clarification_needed), timestamp | Associated with one User; a successful ParseAttempt produces a LogEntry; a failed ParseAttempt may produce a PendingClarification |
| PendingClarification | A transient state representing an unanswered one-shot clarification prompt sent after a parse failure | Clarification ID, User ID, original raw input, clarification prompt text, sent_at timestamp, state (open / resolved / abandoned) | Belongs to one User; resolves to Resolved if the user's clarification response parses successfully, or to Abandoned otherwise |
| OnboardingSession | Tracks the onboarding state of a first-time user | Session ID, User ID, demo parameters shown flag, real parameter added flag, operator disclosure delivered flag, completion_at timestamp | Belongs to one User |

**Ownership notes:**
- All entities are owned by the User identified via Telegram ID.
- Demo parameters presented during onboarding are tagged as synthetic and are not stored as real Parameter records. They are excluded from all LogEntry counts, charts, and comparisons.
- Deleting a parameter purges all associated LogEntries immediately (hard-delete). This is a consequential, irreversible operation; a confirmation step is required before execution (see Flow 8). Note: parameter deletion (immediate hard-delete) and account deletion (3-day soft-delete window) use different semantics by design; see SD-02 and SD-03.
- When a User's account is in Pending Deletion state, no new log entries or commands are accepted except a restoration request. After the 3-day window, the User and all associated data are permanently purged by the enforcement mechanism (see Section 9.5).

**Lifecycle relevance:**
- A Parameter transitions through: Non-existent → Active → Deleted.
- A LogEntry is immutable once created; it is purged only when its parent Parameter is deleted.
- A PendingClarification is transient and one-shot: it exists between a parse failure and either the user's successful clarification response (Resolved) or the user sending any new message without a successful parse (Abandoned). The Resolved state is reachable when the user's clarification response itself parses successfully (see Section 5 and Flow 3).
- A User transitions through: New → Onboarding → Active → (optionally) Pending Deletion → Deleted.

**Entity removed from v0.1:**
- The Chart entity has been removed as a persistent construct. Charts are generated on demand at request time and delivered directly via Telegram. No Chart record is written to storage.

---

## 5. Command Dispatch Model

**Purpose:** This section describes how the system determines the intent of every inbound message before processing. This is the system's highest-complexity routing responsibility.

### Non-Text Input Rejection (Pre-Dispatch Gate)

Before any dispatch logic is applied, the system inspects the Telegram message type. If the message is not a text message (e.g., voice note, image, sticker, forwarded media, location, contact), the system returns an informative rejection message (e.g., "I can only process text messages. Please type your entry.") and halts processing. Non-text inputs do not enter the dispatch pipeline, do not create ParseAttempt records, and do not interact with PendingClarification state.

### Dispatch Priority Order

Every inbound **text** message from a user is evaluated in the following order:

1. **Pending Clarification Check (highest priority):** If the user has an open PendingClarification, the incoming message is routed to the clarification resolution handler. The system attempts to parse the new message as a valid parameter-value pair:
   - If parsing succeeds: the PendingClarification is marked **Resolved**; a LogEntry is created; a confirmation is sent to the user. *(The resolved state is reachable exactly here.)*
   - If parsing fails: the PendingClarification is marked **Abandoned**; the new message is then processed as a fresh input from step 2 below (which may produce a new PendingClarification).
   - *(Rationale: the one-shot model, per SD-003. A successful clarification response marks the record Resolved; a non-parseable response closes the record as Abandoned and the new message is processed normally.)*

2. **Account State Check:** If the user's account is in Pending Deletion state, all commands except an explicit restoration command are rejected with an informative message.

3. **Command Keyword Match:** The leading token(s) of the message are compared against the reserved command vocabulary using the **keyword collision disambiguation rule** defined below.

| Keyword(s) | Routed Flow |
|---|---|
| `list`, `show parameters` | Flow 7: Parameter List Query |
| `history [name]`, `log [name]`, `show [name]` | Flow 4: Parameter History Query |
| `chart [name]`, `graph [name]`, `plot [name]` | Flow 5: Trend Chart Generation |
| `compare [name]`, `vs [name]`, `versus [name]` | Flow 6: Period Comparison |
| `delete [name]` | Flow 8: Parameter Deletion |
| `delete account`, `remove account` | Flow 10: Account Deletion Request |
| `restore account` | Flow 11: Account Restoration |
| `help`, `start` | Flow 12: Help / Start (Active User variant) or Flow 9 (New User) |

4. **Log Intent (default):** If no keyword matches and no special state is active, the message is treated as a log command and passed to the parse engine (Flows 1–3).

### Keyword Collision Disambiguation Rule

A message is matched as a command keyword only when the reserved keyword appears as the **sole leading token** immediately followed by either a recognized parameter name token or end-of-message. A message is routed as a Log Intent (default) if any of the following conditions are met:

- The leading token matches a reserved keyword but is immediately followed by tokens that do not correspond to a recognized command structure (e.g., "history of my runs 5km" — the word "history" is followed by a preposition, not a parameter name directly, indicating log intent).
- The message contains a numeric token adjacent to the leading keyword token, suggesting a value being logged rather than a command.
- Ambiguity cannot be resolved → the system defaults to **Log Intent** (step 4) and invokes the parse engine, which handles the message as a potential log entry.

**Reserved keyword protection:** Reserved keywords (`list`, `history`, `log`, `show`, `chart`, `graph`, `plot`, `compare`, `vs`, `versus`, `delete`, `restore`, `help`, `start`) must not be used as standalone parameter names. If a user attempts to create a parameter whose name exactly matches a reserved keyword with no disambiguating context, the parse engine must flag this and prompt the user to use a more descriptive name. Multi-word names that begin with a reserved keyword (e.g., "history score") are permitted as parameter names and are disambiguated by context.

### Parameter Name Matching Strategy

The system applies a **case-insensitive exact match** as the primary matching rule for all flows that retrieve a parameter by name (Flows 4, 5, 6, 7, 8). The matching rules are:

1. **Case-insensitive exact match:** "Weight" matches "weight" and "WEIGHT". Whitespace is normalized (leading/trailing whitespace trimmed; multiple internal spaces collapsed to one).
2. **No prefix or fuzzy match by default:** "body" does not match "body weight". The user must provide the full parameter name.
3. **Ambiguity handling:** If two or more parameters belonging to the same user match the provided name under case-insensitive comparison (which should not occur under normal creation rules but may arise from historical data), the system surfaces the ambiguity to the user with a list of matching parameter names and requests clarification before proceeding.
4. **No-match handling:** If no parameter matches the provided name, the system returns an explicit informative message (e.g., "No parameter named '[name]' found. Use 'list' to see your parameters.").

### Parse Engine (Conceptual)

The parse engine attempts to extract a parameter name and a numeric value from the free-text message. The strategy is pattern-based: the engine scans the message for a recognizable numeric token (integer or decimal) and associates the remaining text as the parameter name. Unit tokens (e.g., "kg", "L", "km") adjacent to the numeric token are captured if present.

- A ParseAttempt record is created for every message reaching the parse engine, regardless of outcome.
- If extraction succeeds → Flow 1 (Successful Metric Logging).
- If extraction fails → Flow 2 (Parse Failure and Clarification).
- Per SD-007: a failed ParseAttempt is one-shot. The user may manually categorize the entry by re-sending a corrected message at any time; the system does not retry or reprocess the original failed input.

### Telegram Update Delivery Model

The mechanism by which the bot process receives updates from Telegram (long-polling vs. webhook) is a system-level decision with implications for hosting requirements and cold-start behavior. This is recorded as an open decision SD-10 in the Decision Log. Until resolved, the system design does not depend on either delivery mechanism; both are compatible with the described dispatch model.

---

## 6. Data and Interaction Flows

### Flow 1: Successful Metric Logging
- **Trigger:** User sends a message routed to the parse engine; parse engine successfully extracts a parameter name and numeric value
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** Parse engine extracts parameter name and value; all input is sanitized before any storage operation; a ParseAttempt record is created with outcome = success; the system checks whether the parameter already exists for this user (case-insensitive name match); if not, a new Parameter record is created; a new LogEntry is appended with the parsed value, unit (if present), and timestamp; Parameter.last_entry_at is updated; User.last_active_at is updated; a confirmation message is sent to the user
- **Output:** Confirmation message in Telegram chat; new LogEntry stored; ParseAttempt stored; optionally new Parameter created
- **Risk Points:** Parse logic may produce false positives (wrong parameter name or value inferred); auto-creation of parameters on every message may produce unwanted parameter proliferation; storage write failure must be handled explicitly (see Section 9.1); concurrent messages from the same user may race on parameter creation (see Section 9.6)

### Flow 2: Parse Failure and One-Shot Clarification
- **Trigger:** User sends a message routed to the parse engine; parse engine cannot extract a valid parameter-value pair
- **Actor:** End User
- **Input:** Raw free-text message from Telegram
- **System Processing:** Parse engine fails to extract a valid pair; a ParseAttempt record is created with outcome = failure; the system creates a PendingClarification record in Open state; the system sends a single clarification prompt to the user asking them to specify the parameter name and value explicitly; User.last_active_at is updated
- **Output:** One-shot clarification prompt sent to user in Telegram chat; PendingClarification record created in Open state; ParseAttempt stored
- **Risk Points:** The user may ignore the prompt; per SD-003, the system does not re-prompt — the record is abandoned if unaddressed; the user can re-send the original message at any time to trigger a new ParseAttempt; high parse failure rates reduce usability

### Flow 3: Clarification Resolution
- **Trigger:** User sends any message while a PendingClarification is in Open state
- **Actor:** End User
- **Input:** User's clarifying message in Telegram, while PendingClarification is Open
- **System Processing:** Per the Dispatch Model (Section 5, step 1), the Open PendingClarification intercepts the message first; the system attempts to parse the new message as a valid parameter-value pair:
  - **If parsing succeeds:** The PendingClarification is marked **Resolved**; a new ParseAttempt record is created with outcome = success; a new LogEntry is created; a confirmation message is sent to the user.
  - **If parsing fails:** The PendingClarification is marked **Abandoned**; the new message is then processed as fresh input through the dispatch model starting at step 2 (account state check), which may produce a new PendingClarification via Flow 2.
- **Output:**
  - On successful parse: Confirmation message sent; PendingClarification marked Resolved; new ParseAttempt and LogEntry created.
  - On failed parse: PendingClarification marked Abandoned; new ParseAttempt created; new PendingClarification may be created if the message again fails to parse.
- **Risk Points:** If parse consistently fails, users are caught in a repeated clarification cycle; the user must be clearly instructed to use explicit "parameter name: value" format in the clarification prompt

### Flow 4: Parameter History Query
- **Trigger:** User sends a message matched to the history/log/show keyword(s) followed by a parameter name
- **Actor:** End User
- **Input:** User request specifying a parameter name
- **System Processing:** User.last_active_at is updated; the system identifies the requesting user via Telegram ID; applies the parameter name matching strategy (Section 5) to locate the named parameter; if no match is found, returns an informative no-match message; if match found, retrieves the most recent N LogEntries for the named parameter belonging to that user; formats results as a readable list message; N is a fixed system default (to be configured by developer, see A-08); storage read failure is handled explicitly (see Section 9.7)
- **Output:** Formatted list of recent entries sent in Telegram chat, or a no-match message if the parameter does not exist
- **Risk Points:** If multiple parameters share a similar name, the system must surface ambiguity (handled by matching strategy in Section 5); N value must be defined before launch

### Flow 5: Trend Chart Generation
- **Trigger:** User sends a message matched to the chart/graph/plot keyword(s) followed by a parameter name
- **Actor:** End User
- **Input:** User request specifying a parameter name and optionally a time period
- **System Processing:** User.last_active_at is updated; the system applies the parameter name matching strategy to locate the named parameter; if no match, returns an informative no-match message; if fewer than 2 LogEntries exist for the parameter in the requested period, returns an informative message (Section 9.2); otherwise retrieves all relevant LogEntries; generates a static PNG chart image in memory with a timeout enforcement mechanism (if chart generation exceeds 15 seconds, the process is terminated and an error is returned — see Section 9.2); sends the image as a Telegram message; the chart is not stored after delivery
- **Output:** Static PNG chart image delivered in Telegram chat, or informative error message; no Chart entity is persisted
- **Risk Points:** Insufficient data points produce no chart; chart generation must complete within the latency target; timeout enforcement is required to prevent the bot process from blocking indefinitely

### Flow 6: Period Comparison
- **Trigger:** User sends a message matched to the compare/vs/versus keyword(s) followed by a parameter name
- **Actor:** End User
- **Input:** User request specifying parameter name and comparison period type (week or month)
- **System Processing:** User.last_active_at is updated; the system applies the parameter name matching strategy; retrieves LogEntries for the named parameter grouped by the two most recent comparable periods; computes summary statistics for each period; formats a comparison response; if either period contains fewer than 2 LogEntries, the system returns an explicit informative message rather than a potentially misleading comparison; storage read failure handled explicitly (see Section 9.7)
- **Output:** Comparison summary message sent in Telegram chat, or informative insufficient-data message
- **Risk Points:** Sparse data in one or both periods must be communicated explicitly; no silent or partial comparison output is acceptable

### Flow 7: Parameter List Query
- **Trigger:** User sends a message matched to the list/show parameters keyword(s)
- **Actor:** End User
- **Input:** User request
- **System Processing:** User.last_active_at is updated; the system retrieves all active Parameters belonging to the requesting user; formats them as a list; storage read failure handled explicitly (see Section 9.7)
- **Output:** List of active parameter names sent in Telegram chat
- **Risk Points:** If a user has many parameters, the response may be verbose; no pagination mechanism is defined at this scale

### Flow 8: Parameter Deletion
- **Trigger:** User sends a message matched to the delete [name] keyword pattern (where name is not "account")
- **Actor:** End User
- **Input:** User request specifying the parameter name to delete
- **System Processing:** User.last_active_at is updated; the system applies the parameter name matching strategy to identify the named parameter; if no match, returns an informative no-match message; sends a confirmation prompt to the user explicitly stating: (a) deletion is permanent, (b) all history will be removed, (c) this cannot be undone; if the user confirms, the Parameter is hard-deleted and all associated LogEntries are permanently purged; a deletion confirmation message is sent; if the user does not confirm or does not respond, no deletion occurs
- **Output:** Confirmation prompt sent; on user confirmation: Parameter and all LogEntries permanently deleted; deletion confirmation message sent; on no confirmation: no action taken
- **Risk Points:** Deletion is irreversible; a two-step confirmation is mandatory; accidental confirmation results in permanent data loss; note that parameter deletion (immediate, irreversible) differs by design from account deletion (3-day window)

### Flow 9: First-Time Onboarding
- **Trigger:** System receives first message from an unrecognized Telegram ID
- **Actor:** End User (new)
- **Input:** Any first message sent to the bot
- **System Processing:** The system detects that this Telegram ID has no existing User record; creates a new User record; creates an OnboardingSession; delivers a welcome message that **explicitly discloses** that the developer/operator has access to all stored data (operator disclosure, per Section 10.4); presents demo parameters with synthetic fake historical data clearly labeled as demo content; prompts the user to add one real parameter; sets the operator_disclosure_delivered flag on the OnboardingSession; if the user's first message is a valid log command (parseable), the system processes it as a log entry and marks onboarding as completed in parallel; demo data is tagged synthetic and excluded from all future analytics
- **Output:** Welcome message with operator disclosure delivered in Telegram chat; demo content presented; User record created; OnboardingSession created with operator_disclosure_delivered = true; onboarding completed or in-progress
- **Risk Points:** Demo data must be unambiguously labeled as synthetic; operator disclosure must be present in the onboarding welcome message and is non-optional; if the user's first message is a valid log command, processing it and completing onboarding concurrently prevents blocking

### Flow 10: Account Deletion Request
- **Trigger:** User sends a message matched to the delete account / remove account keyword pattern
- **Actor:** End User
- **Input:** User request to delete account
- **System Processing:** User.last_active_at is updated; the system sends a confirmation prompt explicitly stating: (a) all data (parameters, log entries, history) will be permanently deleted after 3 days, (b) the user may restore the account within 3 days by sending "restore account", (c) the exact expiry date and time; if confirmed, the User is placed in Pending Deletion state; deletion_requested_at is set; the system sends a confirmation message with the restoration deadline
- **Output:** Confirmation prompt sent; on user confirmation: User state set to Pending Deletion; deletion_requested_at set; confirmation message with 3-day restoration window sent
- **Risk Points:** User must understand the 3-day window is their only recovery path; the enforcement mechanism (Section 9.5) is responsible for executing the purge when the window expires

### Flow 11: Account Restoration
- **Trigger:** User sends a message matched to the restore account keyword pattern while in Pending Deletion state
- **Actor:** End User
- **Input:** Restoration request during the 3-day window
- **System Processing:** The system verifies that the account is in Pending Deletion state and that the 3-day window has not expired (deletion_requested_at + 3 days > current time); clears the is_pending_deletion flag and deletion_requested_at timestamp; restores the User to Active state; sends a restoration confirmation message
- **Output:** Account restored to Active state; all data remains intact; restoration confirmation message sent
- **Risk Points:** If the 3-day window has expired before the user sends this command, restoration is not possible; the system must return an explicit message indicating that data has been permanently purged; the startup sweep may have already executed the purge before this command is received

### Flow 12: Help / Start (Active User)
- **Trigger:** Active user (onboarding already complete) sends `help` or `start`
- **Actor:** End User (Active)
- **Input:** `help` or `start` message
- **System Processing:** User.last_active_at is updated; the system returns a command reference message listing all available commands and their usage format; no onboarding flow is re-triggered; no state changes occur
- **Output:** Command reference message sent to the user in Telegram chat, including: log format, history, chart, compare, list, delete, delete account, restore account, help
- **Risk Points:** The command reference must remain synchronized with the actual dispatch vocabulary; any changes to supported commands must be reflected here

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
| Open | Parse attempt fails; one clarification prompt sent to user | User sends any new message | Resolved (if the new message parses successfully via the clarification resolution handler) / Abandoned (if the new message also fails to parse, or is routed away from the parse engine) | One-shot model per SD-003; original unprocessed message is lost; user must re-send |
| Resolved | User's clarification response is successfully parsed by the clarification resolution handler in step 1 of the dispatch model; LogEntry created | (terminal) | None (terminal) | This state is reachable only via the successful-parse branch of step 1 in Section 5; the Section 11.1 observability formula depends on this state being correctly set |
| Abandoned | User's clarification response fails to parse (the failed-parse branch of step 1); or bot startup sweep marks all Open clarifications Abandoned; or the user's message bypasses parse (e.g., matches a command keyword after failing the parse branch) | (terminal) | None (terminal) | No re-prompt; no retry; the user must re-initiate if they wish to log the original data |

**Note on one-shot model (SD-003 and SD-007):** The system sends exactly one clarification prompt. The incoming response is first tested by the parse engine. A successful parse yields Resolved; a failed parse yields Abandoned. The user retains the ability to re-send the original message at any time, which triggers a fresh ParseAttempt through the standard dispatch.

### OnboardingSession States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| In Progress | First message received from an unrecognized Telegram ID | User adds a real parameter; or user's first message is a valid log command (auto-completes onboarding) | Completed | If the user never adds a real parameter, the OnboardingSession remains In Progress but does not block further interactions; operator disclosure is always delivered in the first message regardless |
| Completed | User has added at least one real parameter during onboarding, or first message was processed as a log command | (terminal) | None (terminal) | None identified |

### User States

| State | Entry Condition | Exit Trigger | Next Possible States | Risk |
|---|---|---|---|---|
| New | First message received from an unrecognized Telegram ID | Onboarding session is created | Onboarding | No pre-registration mechanism exists |
| Onboarding | Onboarding session created | Onboarding session reaches Completed state | Active | User can interact with the system during onboarding; commands are not blocked |
| Active | Onboarding complete; User is interacting with the system | User sends a confirmed account deletion request | Pending Deletion | No passive deactivation or expiry mechanism is defined |
| Pending Deletion | User has confirmed an account deletion request; 3-day restoration window is active | User sends a restoration command within 3 days (→ Active); or 3-day window expires and startup sweep or scheduled mechanism executes the purge (→ Deleted) | Active (if restored within window) / Deleted (if window expires and enforcement executes) | Only a restoration command can reverse this state; all other commands are rejected during this window; enforcement depends on the startup sweep or scheduled mechanism defined in Section 9.5 |
| Deleted | 3-day Pending Deletion window has expired and the enforcement mechanism has executed the permanent purge | (terminal — all data purged) | None (terminal) | Permanent; no recovery path; user must be informed of finality during the deletion flow; the Deleted state is set by the enforcement mechanism, not solely by time passage |

---

## 8. Non-Functional Requirements

### 8.1 Performance

| Target | Definition | Condition | Risk |
|---|---|---|---|
| Text response latency | The system must send an acknowledgement or response to a log, query, or command message within 3 seconds | Under normal load at max scale (≤ 100 active users) | Telegram cold start on free hosting tier may exceed this target; first-message latency after idle is not bounded by this target |
| Error response latency | Error messages (parse failures, storage failures, invalid commands) must be returned within the same 3-second target as successful text responses | Under normal load | Error delays longer than success responses increase user confusion |
| Chart generation latency | The system must deliver a chart image within 15 seconds of the request | Under normal load | If the 15-second bound is exceeded, the system must return an error message rather than silently fail; a timeout enforcement mechanism is required (see Section 9.2) |
| Cold-start latency | First-message cold-start latency is excluded from the 3-second target but must not exceed 60 seconds | After idle period on free-tier hosting | A response delay exceeding 60 seconds will cause users to assume the bot is non-functional; a keep-alive mechanism is recommended to reduce cold-start frequency |

### 8.2 Availability

- **Target:** Best-effort availability; no formal SLA. Targeted at >90% daily availability.
- **Rationale:** Free hosting tier provides no uptime guarantee. Downtime is acknowledged as acceptable for this personal-scale system.
- **Cold start behavior:** After an idle period, the first inbound message may trigger a process cold start. The response latency target does not apply to cold-start recovery. Users will experience a delay; no notification is sent.

### 8.3 Data Durability

- **Recovery Point Objective (RPO):** Maximum acceptable data loss window is 24 hours.
- **Export mechanism:** A scheduled or triggered export of all stored data must execute at a minimum daily frequency. The export must produce a portable format (such as a structured data dump or JSON export) that can be used to restore the system state independently of the hosting environment. The export must be stored in a location external to and independent of the primary hosting environment. The developer is responsible for configuring and verifying this export. The export mechanism is an operational component of the system, not a user-facing feature.
- **Recovery procedure:** The developer must define and document a restoration procedure that uses the export artifact to rebuild the storage from a known-good state. This procedure must be validated before launch.

### 8.4 Data Volume Estimate

At maximum scale: 100 users × 5 messages/day × 365 days = ~182,500 records/year across all entities. This is a trivially small data volume. The storage mechanism must support relational lookup (queries scoped by User ID) and sequential retrieval (sorted by timestamp) but does not require horizontal scaling, partitioning, or caching.

### 8.5 Message Volume and Rate Limits

- **Estimated peak:** 100 users × 5 messages/day = ~500 messages/day ≈ 0.006 messages/second average. Peak bursts may reach 5–10 messages/minute.
- **Telegram rate limits:** Telegram enforces approximately 30 outbound messages/second globally and 1 message/second per individual chat. At estimated peak load, the system operates well within these limits.
- **Rate limit failure behavior:** If a Telegram rate limit is exceeded, the outgoing message must be retried with a brief delay before surfacing an error; the message must not be silently dropped.

### 8.6 Error Communication

- **Requirement (Fact):** The system must return a human-readable error message for every failure path. No message may be silently dropped without a user-visible response.
- **Timing:** Error messages must be returned within the same 3-second latency target as successful text responses (see Section 8.1).
- **Scope:** This applies to: parse failures, storage read and write failures, chart generation failures, invalid commands, empty query results, deletion rejections, non-text input rejections, and Telegram rate limit retries that ultimately fail.

### 8.7 Input Constraints

- **Parameter name length:** Parameter names must be bounded in length. Names exceeding the bound are rejected with an informative message. The exact bound is to be defined by the developer; a recommended upper limit is 100 characters.
- **Character set:** Parameter names and values must be validated against a permitted character set. Characters outside the permitted set must be rejected with an informative message; they must not be silently truncated or stripped.
- **Input sanitization (mandatory):** All user-supplied input — including parameter names, log values, and any other free-text field stored in or queried against the storage layer — must be sanitized or parameterized before any storage operation. Raw user input must never be interpolated directly into storage queries. This requirement is technology-class agnostic and must be enforced regardless of the storage mechanism selected.

### 8.8 Concurrency

- **Posture:** The bot process handles one message at a time per user in a serialized manner. Concurrent messages from two different users are processed independently and do not share state. Concurrent messages from the same user (e.g., two messages sent within milliseconds) are processed sequentially; the second message is queued until the first is fully processed.
- **Rationale:** At the target scale (≤ 100 users, ≤ 10 messages/minute peak), strict per-user serialization is sufficient and avoids race conditions on PendingClarification state, Parameter creation, and User state.
- **Risk:** If the hosting environment delivers concurrent messages from the same user to two parallel execution contexts, race conditions on PendingClarification and Parameter creation are possible. This risk is noted in the risk register (see Section 14).

---

## 9. Failure Behavior Contract

This section defines the expected system behavior for failure scenarios. These are system-level decisions, not open questions.

### 9.1 Storage Write Failure (Flows 1, 8, 10, 11)
- **Scenario:** The system attempts to write a LogEntry, Parameter, or User state change and the storage operation fails.
- **Behavior:** The system returns an explicit error message to the user (e.g., "Your entry could not be saved. Please try again."). No confirmation message is sent. The entity is not partially written. The user is instructed to retry.
- **Rationale:** A false confirmation — confirming a save that did not occur — corrupts the user's trust and silently distorts success metrics.

### 9.2 Chart Generation Failure or Timeout (Flow 5)
- **Scenario:** The chart generation process fails (e.g., insufficient data points, internal error) or exceeds the 15-second latency target.
- **Timeout enforcement:** The chart generation process must be executed with a timeout enforcement mechanism. If the 15-second bound is reached, the chart generation process is actively terminated and an error message is returned to the user. The timeout mechanism must prevent the generation process from blocking the bot indefinitely.
- **Behavior on failure or timeout:** The system returns an explicit error message to the user (e.g., "Chart could not be generated. There may be insufficient data, or a temporary error occurred."). No image is sent. No partial or empty message is sent.
- **Minimum data point requirement:** If a parameter has fewer than 2 LogEntries in the requested period, the system returns an informative message (e.g., "Not enough data to generate a chart for this period.") rather than attempting chart generation.

### 9.3 Bot Startup with Open PendingClarifications
- **Scenario:** The bot process restarts (planned or after a crash) and finds PendingClarification records in the Open state in storage.
- **Behavior:** On startup, all PendingClarification records in Open state are marked Abandoned by the system. No notification is sent to affected users. Users whose clarification prompts are abandoned retain the ability to re-send their original message at any time, which triggers a fresh ParseAttempt through the standard dispatch.
- **Rationale:** Leaving Open PendingClarifications after a restart creates an ambiguous routing state for the first subsequent message from each affected user. Proactive abandonment on startup produces a clean, defined state.

### 9.4 Period Comparison with Sparse Data (Flow 6)
- **Scenario:** One or both periods in a comparison request contain fewer than 2 LogEntries.
- **Behavior:** The system returns an explicit informative message indicating which period lacks sufficient data. A partial or misleading comparison is never returned.

### 9.5 Account Deletion Enforcement Mechanism (3-Day Window)
- **Scenario:** A User record is in Pending Deletion state and the 3-day window defined by deletion_requested_at has expired.
- **Enforcement mechanism:** On every bot process startup, the system performs a sweep of all User records in Pending Deletion state. For each record where `deletion_requested_at + 3 days ≤ current_time`, the system executes permanent data purge: all LogEntries, Parameters, ParseAttempts, PendingClarifications, and OnboardingSession records belonging to that User are deleted; the User record is then deleted; the User state transitions to Deleted.
- **Offline window handling:** If the bot was offline when the 3-day window expired, the purge is executed on the next startup sweep. The expiry is based on the deletion_requested_at timestamp, not on a real-time clock event. A user whose 3-day window expired during a bot outage will have their data purged on the next bot startup, which may be slightly after the 3-day deadline. This is the accepted behavior under the free-tier operational model.
- **No notification on purge:** The system does not send a notification to the user when the purge executes. The user was informed of the deadline at the time of the deletion request (Flow 10).
- **Observability:** The startup sweep must log each purge event (User ID, purge_executed_at, deletion_requested_at) to the system log for developer audit purposes.

### 9.6 Concurrent Messages from the Same User
- **Scenario:** Two messages from the same user arrive in rapid succession before the first is fully processed.
- **Behavior:** Messages from the same user are processed sequentially. The second message is held in the delivery queue until the first message's processing is fully complete, including any storage writes. This prevents race conditions on PendingClarification state transitions, Parameter creation, and User state changes.
- **If the hosting environment does not support per-user serialization:** The developer must acknowledge this gap explicitly and accept the race condition risk. At the target scale (≤ 100 users, low message frequency), the probability of same-user concurrent messages is low but not zero.

### 9.7 Storage Read Failure (Flows 4, 5, 6, 7)
- **Scenario:** The system attempts to read LogEntries, Parameters, or User state for a query or chart request and the storage read operation fails.
- **Behavior:** The system returns an explicit error message to the user (e.g., "Could not retrieve your data. Please try again."). No partial results are returned. No empty chart or empty list is returned silently. The user is instructed to retry.
- **Rationale:** A storage read failure must be surfaced to the user. Returning an empty result set in response to a read failure would be indistinguishable from a genuinely empty parameter history, misleading the user.

---

## 10. Security and Data Controls

### 10.1 Data Isolation Enforcement
- **Control:** All storage queries must include the Telegram ID received from the platform delivery layer as a mandatory filter. No query path that could return data belonging to a different User ID is permitted.
- **Risk:** A routing or query logic defect that omits the User ID filter would expose one user's data to another. This is the highest-impact security failure mode for this system.

### 10.2 Secrets Handling
- **Control:** The Telegram Bot API token is the sole secret the system holds. It must be stored as an environment variable at the hosting layer. It must not appear in source code, configuration files committed to version control, or **any log output** (including error stack traces, debug dumps, or environment variable logging). Log output is treated as a potentially insecure surface and must explicitly exclude the token.
- **Assumption:** The hosting platform provides a mechanism for injecting environment variables into the bot process at runtime.

### 10.3 Demo Data Isolation
- **Control:** Demo parameters and their synthetic data created during onboarding are tagged with a `is_synthetic` flag. All analytics flows (chart generation, history queries, period comparison) must filter out entries with this flag. No synthetic data appears in any user-facing output outside of the explicit onboarding context.

### 10.4 Operator Data Access
- **Fact:** The developer, as the sole operator, has unrestricted access to all raw user data stored in the system. Users in this closed group are personally known to the developer. No technical access control separating the developer from user data is defined. This is acknowledged as a trust and expectation management concern.
- **Required disclosure:** Users must be informed of this condition as part of the onboarding welcome message (Flow 9). This disclosure is non-optional and is tracked by the `operator_disclosure_delivered` flag on the OnboardingSession entity. The onboarding flow must not be considered complete until this disclosure has been delivered.

### 10.5 Input Sanitization
- **Control:** All user-supplied input reaching any storage operation must be sanitized or parameterized. This includes parameter names, log values, and any free-text content stored or queried in the storage layer. Raw user input must never be interpolated directly into storage queries regardless of the storage technology class.

### 10.6 Non-Text Input Handling
- **Control:** Non-text Telegram messages (voice notes, images, stickers, forwarded media, locations, contacts) must be rejected at the pre-dispatch gate (Section 5) before reaching any processing logic. A rejection message must be returned. These inputs must not reach the parse engine, must not create ParseAttempt records, and must not interact with PendingClarification state.

---

## 11. Observability Model

### 11.1 Parse Failure Resolution Rate (Primary Success Metric)
- **Signal:** Every ParseAttempt record carries an outcome field (success / failure / clarification_needed). Every PendingClarification record carries a state field (open / resolved / abandoned).
- **Measurement:** The parse failure resolution rate is computed as:
  `(count of ParseAttempts with outcome = success) + (count of PendingClarifications with state = resolved)` divided by `(total ParseAttempts)` over a rolling 30-day window.
- **State consistency note:** The `Resolved` state on PendingClarification is set by the clarification resolution handler in step 1 of the dispatch model when the user's clarification response is successfully parsed. This state is now reachable by the described dispatch logic (Section 5, step 1, successful-parse branch). The formula is valid under this corrected model.
- **Target:** >80% resolution rate as defined in Business v0.3.
- **Access:** The developer queries the ParseAttempt and PendingClarification tables directly; no automated alerting is required at this scale.

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
- **Minimum check frequency:** The developer must interact with the bot at least once per day to detect extended outages. Given the >90% daily availability target (Section 8.2), an undetected multi-hour outage could exceed the acceptable downtime threshold for the day.

### 11.5 Storage Utilization
- **Signal:** The developer monitors storage consumption against the free-tier quota manually.
- **Threshold:** If storage approaches 80% of the free-tier limit, a data export and cleanup procedure should be initiated.

### 11.6 Error Rate by Flow
- **Signal:** ParseAttempt records cover parse-layer failures. Storage write and read failures, chart generation failures, and rejection events produce user-visible error messages; the developer can review error rates by inspecting system logs.
- **Minimum requirement:** The system must log every failure path with sufficient context (User ID, flow name, error type) to enable the developer to diagnose recurring issues.
- **System log durability:** The developer must be aware that free-tier hosting environments frequently do not persist logs across process restarts (log output may be written to stdout and discarded on restart). For retrospective error analysis, the developer should establish a log forwarding or export mechanism, or accept that pre-restart error history is ephemeral.

### 11.7 Account Deletion Purge Audit
- **Signal:** The startup sweep defined in Section 9.5 must write a log record for each purge event (User ID, purge_executed_at, deletion_requested_at).
- **Purpose:** Enables the developer to audit whether purge events executed correctly, to verify the 3-day window was honored, and to confirm no User records are stuck in Pending Deletion state indefinitely.

---

## 12. External Dependencies

| External System | Purpose | Dependency Type | Risk Level |
|---|---|---|---|
| Telegram Platform | Message delivery, user identity (Telegram ID), image display, chat interface, rate limit enforcement; update delivery via polling or webhook (see SD-10) | Hard dependency — system cannot function without it | High — any Telegram outage, API change, or policy change makes the system completely inaccessible |
| Free Hosting Infrastructure | Runtime environment for the bot process and embedded relational storage | Hard dependency — system cannot run without a host | Medium — free tier limits (memory, CPU, uptime, storage quotas) may cause degraded or interrupted service; data loss risk on tier eviction; daily backup is the primary mitigation |

No third-party integrations are proposed. Dependencies are stated as they exist in the approved business document.

---

## 13. Assumptions

1. **A-01: Telegram ID is stable and unique per user.**
   - Why it exists: The entire identity model relies on Telegram ID as the sole identifier with no PII fallback.
   - Risk if false: If a user loses access to their Telegram account, all their data becomes inaccessible or orphaned. If IDs are ever reassigned (highly unlikely), data isolation could be violated.
   - Validation idea: Review Telegram platform documentation to confirm ID permanence guarantees.

2. **A-02: Free-text messages are the only input modality used; all other Telegram message types are rejected at the pre-dispatch gate.**
   - Why it exists: Business document explicitly excludes voice input and image recognition; non-text input handling is now explicitly defined.
   - Risk if false: If users send voice notes or images expecting them to be processed, the rejection message must be clear and informative.
   - Validation idea: Test non-text input rejection in the first weeks post-launch; observe whether users attempt non-text input patterns.

3. **A-03: Demo parameters created during onboarding are synthetic and tagged; they are never co-mingled with real LogEntries.**
   - Why it exists: The business document states onboarding uses demo parameters with fake historical data; the system must prevent this data from contaminating real analytics.
   - Risk if false: Charts, comparisons, and history queries will include synthetic values, producing misleading output.
   - Validation idea: Confirm the `is_synthetic` tagging mechanism is applied at creation time and that all analytics flows enforce the filter.

4. **A-04: Deleting a parameter purges all associated LogEntries immediately (hard-delete).**
   - Why it exists: The business document states deletion removes a parameter "along with its history." A two-step confirmation step is added to mitigate accidental loss.
   - Risk if false: If soft-delete semantics were introduced without storage cleanup, storage would grow indefinitely.
   - Validation idea: Developer to confirm deletion semantics are hard-delete; verify the confirmation step is enforced in the deletion flow.

5. **A-05: The onboarding flow does not block valid log commands; if a user's first message is a parseable log command, the system processes it and marks onboarding as completed.**
   - Why it exists: Blocking users who know what they want to do from executing commands until onboarding is complete would create unnecessary friction.
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
   - Why it exists: The secrets handling control (Section 10.2) requires that the token not be stored in source code or logs.
   - Risk if false: If the hosting platform does not support environment variables, an alternative secrets storage mechanism must be defined before deployment.
   - Validation idea: Confirm environment variable support with the selected hosting provider before deployment.

10. **A-10: The embedded relational storage is co-located with the bot process on the hosting platform.**
    - Why it exists: The storage model decision (SD-08) specifies embedded relational storage to eliminate network dependency and reduce free-tier complexity.
    - Risk if false: If storage is external (separate service), network failures create an additional dependency layer and the failure behavior contract must be extended.
    - Validation idea: Confirm storage co-location with the hosting configuration before deployment.

11. **A-11: The Telegram update delivery mechanism (polling or webhook) is determined before deployment and its hosting implications are satisfied.**
    - Why it exists: SD-10 identifies this as an open decision. Webhook delivery requires a public HTTPS endpoint (not available on all free-tier platforms); polling does not.
    - Risk if false: If webhook is chosen but no public endpoint is available, the bot cannot receive updates. If polling is chosen but the platform does not allow persistent connections, the bot cannot maintain the polling loop.
    - Validation idea: Confirm hosting platform capability for the chosen delivery mechanism before deployment.

---

## 14. Risks

| Risk | Type | Impact | Probability | Mitigation Idea |
|---|---|---|---|---|
| High parse failure rate causes user abandonment | Behavioral | High — directly undermines core value proposition | Medium — free-text is inherently ambiguous | Invest in robust parse logic; define a clear message format guide for users; measure failure rate actively from day one |
| Free hosting tier eviction or resource exhaustion causes data loss | System | High — all user data could be lost permanently | Medium — free tiers have unpredictable longevity | Implement daily data export to external location; document recovery procedure; inform users of the data durability posture at onboarding |
| Telegram API changes or policy updates break the bot | System | High — entire delivery channel is external and uncontrolled | Low — Telegram Bot API is stable but not guaranteed | Monitor Telegram changelog; maintain awareness of terms of service compliance |
| Accidental parameter deletion with no undo mechanism | Behavioral | Medium — individual user permanently loses tracking history | Medium — deletion is a normal user action | Two-step confirmation prompt is mandatory before any deletion; clearly state irreversibility in the prompt |
| Scope creep beyond MVP boundary | Business | Medium — developer time and system complexity increase | High — single-developer projects with personal users are vulnerable to ad hoc feature requests | Enforce strict MVP boundary; maintain documented out-of-scope list; treat additions as explicit scope change decisions |
| Parameter name collision or ambiguity within a user's data | System | Medium — wrong data logged silently or query returns wrong parameter | Low-Medium — users naturally use varied naming | Case-insensitive exact-match rule defined; surface ambiguity to user when multiple matches are detected |
| One-shot clarification model leads to silently lost data | Behavioral | Medium — user believes data was logged but it was abandoned after an ignored clarification | Medium — users may not respond to the clarification prompt promptly | Clarification prompt must clearly state the one-shot nature and instruct the user to re-send their original message if they wish to retry |
| Bot cold start on free-tier hosting causes silent first-message failure | System | Medium — user sends a message and receives no response during cold start | High — free-tier services frequently suspend idle processes | Document cold-start behavior; consider a scheduled keep-alive mechanism; cold-start latency bounded at 60 seconds (Section 8.1) |
| Data isolation defect routes one user's data to another | System | High — privacy violation in a personal, trust-based system | Low — requires a specific query logic bug | Enforce mandatory User ID scoping on all queries; include data isolation in any testing checklist |
| Single developer as sole operator creates bus factor risk | Business | High — system has no operational continuity if developer is unavailable | Low (personal project scope) | Document operational procedures; maintain a basic runbook for restart and recovery |
| Insufficient data points for meaningful charts or comparisons | Behavioral | Low — user receives an uninformative response | High in early use (users have few log entries) | Minimum data point threshold enforced in Flows 5 and 6; return informative message if threshold not met |
| Account deletion 3-day window misunderstood by user | Behavioral | Medium — user expects immediate deletion and is confused by continued data presence, or expects longer window | Low | Deletion confirmation message must state the 3-day window explicitly and the exact expiry date/time |
| Concurrent messages from same user cause race conditions | System | Medium — duplicate LogEntries, duplicate Parameters, or inconsistent PendingClarification state | Low-Medium — depends on hosting environment's message delivery behavior | Per-user message serialization (Section 8.8); concurrency behavior contract defined in Section 9.6 |
| Chart generation blocks bot process indefinitely without timeout enforcement | System | High — all subsequent messages are blocked; bot becomes unresponsive | Low-Medium — chart generation on free-tier resources may be slow | Timeout enforcement mechanism required (Section 9.2); chart generation must be terminated after 15 seconds |
| System log ephemeral on free-tier hosting prevents retrospective error analysis | System | Medium — developer cannot diagnose errors that occurred before a process restart | High — stdout-based logging is commonly discarded on free-tier restarts | Establish log forwarding or export mechanism before launch; document that pre-restart error history is ephemeral (Section 11.6) |
| Keyword collision misroutes log-intent messages as commands | System | Medium — user's log entry is silently dropped or routed to wrong flow | Low-Medium — depends on user parameter naming habits | Keyword collision disambiguation rule defined in Section 5; log-intent is the default when ambiguous |

---

## 15. Logical Consistency Check

**Are there gaps in lifecycle?**
- The User entity has a defined exit path (Pending Deletion → Deleted via enforcement mechanism). No lifecycle gap exists.
- The Deleted state on User is now set by the enforcement mechanism (startup sweep), not solely by the passage of time. The mechanism is described in Section 9.5.
- The OnboardingSession has no explicit path out of In Progress if the user never adds a real parameter and never sends a valid log command. This is acceptable: the session remains In Progress but does not block system operation. It is explicitly noted as a non-blocking incomplete state.
- The operator disclosure is delivered in the first onboarding message regardless of whether the session reaches Completed state; the disclosure is not contingent on onboarding completion.

**Are any actors undefined?**
No. All three actors (Developer / Bot Owner, End User, Telegram Platform) are represented. No new actors have been introduced.

**Are there ambiguous states?**
- The PendingClarification state contradiction from v0.2 is resolved. The Resolved state is now reachable: it is set when the clarification resolution handler (dispatch step 1) successfully parses the user's response. The Abandoned state is set when parsing fails or when the startup sweep runs. The two states are mutually exclusive and cover all exit paths from Open.
- The onboarding interrupt behavior is resolved: valid log commands during onboarding are processed normally and complete onboarding concurrently.
- One residual ambiguity: the behavior when a user in Pending Deletion state sends a message other than a restoration command is defined (rejected with an informative message), but the exact rejection message vocabulary is not specified. This is a detailed design decision deferred to the developer.

**Are there circular flows?**
No circular flows are present. All flows have defined entry triggers and terminal output states. The clarification loop (Flow 2 → Flow 3) is a bounded one-shot retry that terminates in either a new ParseAttempt (Resolved or Abandoned). The account deletion/restoration cycle (Flow 10 → Flow 11) is a bounded reversible state change, not a circular dependency.

---

## Version
v0.3

## Based On
Business v0.3 | System v0.2 | System Review v0.2

## Changes Introduced

### Mandatory Revision Resolutions (from System Review v0.2):

1. **Resolved PendingClarification state contradiction (MR-1).** Section 5 dispatch model step 1 now splits on parse outcome: successful parse → Resolved; failed parse → Abandoned then fresh processing. Section 7 PendingClarification state model updated to reflect both exit paths as reachable. Section 6 Flow 3 updated to match. Section 11.1 observability formula preserved and noted as valid under the corrected model.

2. **Defined storage model (MR-2).** Section 3 (Boundaries) and Section 8.3 now specify embedded relational storage co-located with the bot process. Export mechanism requirements defined: portable format, external storage location, minimum daily frequency, recovery procedure requirement. Assumption A-10 added. Decision SD-08 added to Decision Log.

3. **Defined 3-day account deletion enforcement mechanism (MR-3).** Section 9.5 added: startup sweep checks all Pending Deletion records against current time, executes permanent purge for expired records, handles offline window by deferring to next startup, mandates audit log per purge event. Section 7 User state model updated: Deleted state is now set by the enforcement mechanism. Section 11.7 observability signal added for purge audit.

4. **Addressed keyword collision risk (MR-4).** Section 5 now includes a Keyword Collision Disambiguation Rule: keyword match requires the keyword as sole leading token in command structure context; numeric token adjacent to keyword indicates log intent; ambiguity defaults to Log Intent. Reserved keyword protection note added.

5. **Defined parameter name matching strategy (MR-5).** Section 5 now includes a named Parameter Name Matching Strategy: case-insensitive exact match, whitespace normalization, no fuzzy or prefix match, explicit ambiguity handling when multiple matches exist, explicit no-match message.

6. **Stated Telegram update delivery model (MR-6).** Section 5 includes a named subsection on the update delivery model. Decision SD-10 added to Decision Log as an open decision. Assumption A-11 added. Section 3 Boundary Assumption 7 added. Section 12 External Dependencies updated.

7. **Added input sanitization requirement (MR-7).** Section 8.7 now includes a mandatory input sanitization requirement: all user-supplied input must be sanitized or parameterized before storage operations; raw input must never be interpolated into queries; requirement is technology-class agnostic. Section 10.5 (Input Sanitization) added as a security control.

8. **Added non-text input rejection (MR-8).** Section 3 (Inside the System) now explicitly lists non-text input rejection. Section 5 includes a Non-Text Input Rejection pre-dispatch gate. Section 10.6 added as a security control. Assumption A-02 updated. Risk register updated.

9. **Integrated operator disclosure into Flow 9 (MR-9).** Flow 9 (First-Time Onboarding) now includes an explicit step mandating the delivery of the operator data access disclosure in the onboarding welcome message. OnboardingSession entity updated with `operator_disclosure_delivered` flag. Section 10.4 updated to reference Flow 9 enforcement.

10. **Added Help/Start flow for Active users (MR-10).** Flow 12 (Help / Start — Active User) added. Dispatch table in Section 5 updated to reference Flow 12 for Active users. New User `help`/`start` continues to invoke Flow 9.

### Additional Improvements (from NFR and reliability gaps in Review v0.2):

- **Section 8.1:** Error response latency target added (same 3-second target as success responses). Cold-start latency informally bounded at 60 seconds.
- **Section 8.5:** Telegram rate limit failure behavior added (retry before error; no silent drop).
- **Section 8.6:** Timing constraint added to error communication requirement.
- **Section 8.8:** Concurrency NFR section added with per-user serialization posture.
- **Section 9.6:** Concurrent message failure behavior contract added.
- **Section 9.7:** Storage read failure behavior contract added.
- **Section 11.4:** Minimum daily check frequency mandated for bot availability monitoring.
- **Section 11.6:** System log durability advisory added for free-tier hosting.
- **Section 11.7:** Account deletion purge audit observability signal added.
- **Section 14:** Four new risks added: concurrent message race conditions, chart timeout blocking, ephemeral system logs, keyword collision misrouting.
- **Traceability:** Parameter name matching strategy and non-text input rejection traced to business goals and entities.

---

## Decision Log Updates

| ID | Decision | Rationale | Version | Status |
|---|---|---|---|---|
| D-01 | Telegram is the exclusive delivery channel | Carried from Business v0.3 | v0.1 | Confirmed |
| D-02 | Identity model is Telegram ID only; no PII | Carried from Business v0.3 | v0.1 | Confirmed |
| D-03 | Parse failures acceptable — fallback to one-shot clarification prompt | Carried from Business v0.3; one-shot semantics added per SD-003 | v0.2 | Confirmed |
| D-04 | Onboarding uses demo parameters with fake historical data tagged as synthetic | Carried from Business v0.3; synthetic tagging formalized in v0.2 | v0.2 | Confirmed |
| D-05 | Threshold alerts out of scope | Carried from Business v0.3 | v0.1 | Confirmed |
| D-06 | Charts are static PNG images generated on demand; not persisted | Carried from Business v0.3; persistence decision resolved in v0.2 as on-demand | v0.2 | Confirmed |
| SD-01 | PendingClarification entity models the one-shot clarification state | One-shot semantics per SD-003; Resolved state is now reachable via successful-parse branch of dispatch step 1; Abandoned state set on failed-parse or startup sweep | v0.3 | Updated — state contradiction resolved |
| SD-02 | Parameter deletion is hard-delete with mandatory two-step confirmation | Hard-delete semantics confirmed; parameter deletion (immediate) and account deletion (3-day window) intentionally use different semantics | v0.2 | Confirmed |
| SD-03 | Account deletion includes a 3-day restoration window | User account deletion uses soft-delete with 3-day window; enforcement mechanism is startup sweep defined in Section 9.5 | v0.3 | Updated — enforcement mechanism defined |
| SD-04 | Command dispatch uses keyword-first routing with log intent as default | Resolves the command routing gap from v0.1; keyword collision disambiguation rule added in v0.3 | v0.3 | Updated — disambiguation rule added |
| SD-05 | Charts are generated on demand and not persisted after delivery | Reduces storage complexity; chart data is always derivable from LogEntries; trade-off acknowledged: large LogEntry sets require full retrieval on every chart request, which is acceptable at target scale | v0.2 | Confirmed |
| SD-06 | Parameter name matching is case-insensitive exact match; no fuzzy or prefix matching | Deterministic behavior; prevents silent mismatches; users are directed to use the exact parameter name; ambiguity is surfaced explicitly | v0.3 | New |
| SD-07 | Failed ParseAttempts are one-shot; no automatic retry or reprocessing | Reduces state complexity; user may re-send at any time | v0.2 | Confirmed |
| SD-08 | Storage uses embedded relational storage co-located with the bot process | Eliminates network dependency; reduces free-tier complexity; compatible with the data volume requirements at target scale; trade-off: storage is not independently scalable and is tied to the hosting process lifecycle | v0.3 | New |
| SD-09 | Non-text Telegram inputs are rejected at the pre-dispatch gate with an informative message | Prevents undefined behavior in the parse engine; sets clear user expectations; consistent with the text-only input model | v0.3 | New |
| SD-10 | Telegram update delivery model (polling vs. webhook) | Open decision — implications: webhook requires a public HTTPS endpoint; polling survives cold-start more gracefully; choice affects cold-start behavior and hosting requirements. Must be resolved before deployment. | v0.3 | Open — must be resolved before deployment |

---

## Uncertainty Updates

| ID | Type | Description | Impact | Validation Plan |
|---|---|---|---|---|
| U-01 | Behavioral | Onboarding interrupt behavior | **Resolved in v0.2:** valid log commands during onboarding are processed normally and complete onboarding concurrently | Closed |
| U-02 | Behavioral | PendingClarification one-shot model | **Resolved in v0.2 / corrected in v0.3:** one-shot prompt; Resolved state is now reachable via successful-parse branch; Abandoned set on failed-parse or startup sweep | Closed |
| U-03 | Data | Demo onboarding parameter persistence | **Resolved in v0.2:** demo parameters are synthetic-tagged and excluded from all analytics | Closed |
| U-04 | Data | Default value of N in "last N entries" history query | Still open — developer to define and document default N | Define N before launch; document as system configuration constant |
| U-05 | Behavioral | Race condition: new message while PendingClarification is Open | **Resolved in v0.2:** new message triggers the clarification resolution handler; outcome determines Resolved or Abandoned state | Closed |
| U-06 | Operational | Minimum data point threshold for chart generation | **Partially resolved in v0.2:** minimum of 2 LogEntries required; exact threshold for a "meaningful" chart (beyond 2) left to developer | Define threshold before chart flow is implemented; document in system configuration |
| U-07 | System | Telegram update delivery model (polling vs. webhook) | **Open decision (SD-10):** hosting implications differ significantly; must be resolved before deployment | Developer to confirm hosting platform capability and select delivery model before deployment |
| U-08 | Operational | System log durability on free-tier hosting | Open — stdout logs may be ephemeral; pre-restart error history may be lost | Developer to evaluate log forwarding options before launch; accept ephemeral logs as known risk if no forwarding is configured |

---

## Traceability Updates

| Business Goal | Entity / Flow / State | Risk |
|---|---|---|
| Unified tracking inside Telegram | Flow 1 (Successful Metric Logging), Flow 2 (Parse Failure), Flow 12 (Help for Active Users), User entity, Parameter entity | High parse failure rate reduces unification value; keyword collision disambiguation mitigates misrouting |
| User-defined parameters, no predefined categories | Parameter entity (auto-created on first use), Flow 1, SD-06 (case-insensitive name matching) | Parameter proliferation from auto-creation; name ambiguity handled by matching strategy |
| Data isolated per Telegram ID | User entity (Telegram ID as sole key), all entities scoped by User ID, Section 10.1 isolation control, Section 10.5 input sanitization | Telegram ID stability (A-01); isolation defect risk; injection risk mitigated by input sanitization |
| Log of last N entries | Flow 4 (Parameter History Query), LogEntry entity, parameter name matching strategy | Undefined N value (U-04); no-match message defined |
| Trend chart as static PNG in Telegram | Flow 5 (Trend Chart Generation), on-demand generation model, timeout enforcement (Section 9.2) | Insufficient data points; timeout blocking risk mitigated by enforcement mechanism |
| Period comparison (week / month) | Flow 6 (Period Comparison) | Sparse data producing misleading comparisons; mitigated by explicit informative message |
| Parse failure fallback to clarification | Flow 2, Flow 3 (corrected Resolved/Abandoned semantics), PendingClarification state model | One-shot model may result in lost entries if user ignores prompt; Resolved state correctly tracked for observability |
| Onboarding with demo data | Flow 9 (First-Time Onboarding including operator disclosure), OnboardingSession entity (operator_disclosure_delivered flag), synthetic tagging | Demo data contamination mitigated by is_synthetic flag; disclosure delivery enforced in flow |
| Parse failure resolution rate >80% | ParseAttempt entity, PendingClarification Resolved state, Section 11.1 observability (corrected formula) | Resolved state now correctly reachable; formula is valid |
| User Return Rate >40% at week 2 | User.last_active_at, Section 11.2 observability | No automated reporting; manual measurement by developer |
| Parameter Retention Rate >50% at day 30 | Parameter.last_entry_at, Section 11.3 observability | Derivable from LogEntry timestamps; no automated reporting |
| Developer learning and portfolio value | All flows demonstrate stateful architecture, multi-user isolation, NLP parsing, chart delivery, account lifecycle management | Scope creep risk |
| MVP delivered within 3 months on near-zero budget | External dependency on free hosting infrastructure; embedded storage model (SD-08); daily export as RPO mitigation | Free tier instability and data loss risk; export mechanism defined with external storage requirement |
| Account deletion with user data rights | Flow 10, Flow 11, User Pending Deletion / Deleted states, 3-day restoration window, startup sweep enforcement (Section 9.5), purge audit (Section 11.7) | User misunderstanding mitigated by explicit confirmation; enforcement gap closed by startup sweep |
| Non-text input handling | Section 3 boundary, Section 5 pre-dispatch gate, Section 10.6, SD-09 | Non-text inputs could cause undefined behavior if not rejected; mitigated by pre-dispatch gate |
| Input injection protection | Section 8.7 sanitization requirement, Section 10.5 control | Storage corruption or injection if raw input reaches storage queries; mitigated by mandatory sanitization |
