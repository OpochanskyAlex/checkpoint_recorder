---
doc: UC
id: UC1
project: checkpoint_recorder
version: 0.1
status: draft
owner: system-analyst
reviewed_by: null
score: null
activities: [account]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
updated: 2026-04-26
tags: [project-docs, use-case]
---

# UC1: Onboard new user

Traces to [[srs#FR1|FR1 Idempotent user registration]], [[srs#FR2|FR2 Account status gate]], [[srs#FR3|FR3 Conversation state routing]]. User story: [[us-6-manage-account|US6 Manage account]].

Activity tags: `@account`

## Actors

- **Primary:** End User
- **Secondary:** Telegram Platform (message delivery), Observability Collector

## Preconditions

- No InternalUser record exists for this Telegram user ID.
- Telegram Gateway has successfully received the inbound message.

## Postconditions

### On success
- Exactly one InternalUser record exists with `account_status = Active` and no personal data fields.
- Onboarding message delivered covering: data retention policy, no-export limitation, verbatim `raw_input` storage, one-shot alert behavior.
- `registration_event` emitted to Observability Collector.
- ConversationState record created with `state = Idle`.

### On failure
- No InternalUser record created.
- No entry processed.
- User receives an error message.

## Main flow (happy path)

1. End User sends any first message to the bot.
2. Message Dispatcher receives message; User Session Guard finds no InternalUser for this Telegram ID — first-contact path.
3. Account Manager performs atomic check-and-create of InternalUser (upsert on `telegram_user_id`; DB unique constraint prevents duplicates).
4. Account Manager dispatches onboarding message (FR1 content: retention policy, no export, raw_input storage, one-shot alerts).
5. Account Manager emits `registration_event` (fire-and-forget).
6. ConversationState record initialized to `Idle`.

## Alternative flows

### A1 First message is also a parseable data entry (compound first-contact)
Branches from step 4.
1. After onboarding message dispatched, Account Manager signals Entry Processor to process the original message as a data entry.
2. Entry Processor proceeds as UC2 from step 2 onward, using the newly created InternalUser context.
3. If entry processing requires a new metric → periodicity prompt dispatched (UC2 / A1). ConversationState → PendingPeriodicity.
4. If entry processing yields ambiguous NLP result → UC3 initiated. ConversationState → PendingDisambiguation.

### A2 First message is ambiguous (NLP cannot auto-parse)
Branches from A1 step 2.
1. Entry Processor routes to ParseAttempt Manager.
2. UC3 initiated immediately after onboarding.

## Error paths

### E1 InternalUser creation fails (DB write error)
- Detected at: step 3.
- System response: Account Manager returns error to user; no InternalUser created.
- Final state: user unregistered; no entry or ParseAttempt created. User retries by sending a new message.

### E2 Onboarding message dispatch fails
- Detected at: step 4.
- System response: `registration_event` still emitted if InternalUser was created. User does not receive onboarding message (known limitation — Telegram delivery unconfirmed at application layer).
- Final state: user registered but unaware of data policy. Operator-detectable via missing Telegram delivery receipt.

### E3 Entry processing fails after successful registration (compound flow)
- Detected at: A1 step 2.
- System response: Account Manager sends explicit error to user: "Your account was created. Your entry could not be processed — please send it again." `registration_event` emitted regardless of entry outcome.
- Final state: user registered; entry not stored; user informed to re-submit.

## Edge cases

- **Concurrent first messages from same user** → DB unique constraint on `telegram_user_id` ensures exactly one InternalUser created. Second write returns constraint violation; treated as upsert (use existing record). BR7 equivalent for users.
- **Deleted user sends a new message** → Account Manager treats this as first-contact; new InternalUser with new `internal_user_id` created. Old Deleted record remains terminal.

## Non-functional considerations

- NFR6: InternalUser creation query must be atomic (check-and-create, not check-then-create).
- NFR5, BR5: No personal data fields (name, username, phone) written to DM1 at any point.
- BR12: Onboarding is the primary atomic step; entry processing is secondary and its failure must not roll back registration.
