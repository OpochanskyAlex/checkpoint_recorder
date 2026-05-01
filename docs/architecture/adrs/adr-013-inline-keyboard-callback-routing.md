---
doc: ADR
id: ADR-013
title: Inline keyboard CallbackQuery routing
project: checkpoint_recorder
version: 0.1
status: accepted
owner: architect
reviewed_by: null
score: null
activities: [logging, management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
related: [ADR-001, ADR-002]
updated: 2026-05-01
tags: [project-docs, adr]
---

# ADR-013: Inline keyboard CallbackQuery routing

# Context

Prior to the smart-metric-picker feature, the bot handled only text Message events from the Telegram Bot API. All routing in Message Dispatcher was keyed on the text content and the per-user ConversationState.

The smart-metric-picker feature introduces inline keyboard buttons (FR22–FR30). When a user presses an inline keyboard button, Telegram sends a `CallbackQuery` event — a distinct event type from a text Message. This requires a structurally new routing path in Message Dispatcher. Key considerations:

1. CallbackQuery events arrive independently of any subsequent text message; they carry an opaque `callback_data` string defined at keyboard construction time and a `message_id` that identifies the message to edit/answer.
2. The picker presents three callback action types: (a) metric selection (user picks a metric by pressing its button), (b) "Create [typed_name]" (zero-match logging flow only), and (c) Cancel (present on every picker keyboard display; produces the same outcome as the `/cancel` command). These must be distinguishable at the routing layer without requiring a DB read before dispatch.
3. ConversationState remains the primary routing guard: a CallbackQuery received when the user is not in `PendingMetricPicker` state must be rejected gracefully (UC16 E3 — stale callback).
4. Future inline keyboard interactions (e.g., confirmation dialogs, pagination if ever added) will reuse the same pattern.
5. The `callback_data` field has a Telegram limit of 64 bytes.

This ADR formalizes the routing pattern for CallbackQuery events so that future inline keyboard features have a stable precedent.

# Decision

**Route CallbackQuery events through Message Dispatcher alongside text Message events, using a structured `callback_data` encoding to carry action type and metric_id.**

Specifically:

1. **Message Dispatcher registers a CallbackQuery handler** in addition to the existing Message handler. aiogram 3.x supports this natively with `@router.callback_query(...)` decorators. No separate dispatcher or process is introduced (consistent with [[adr-001-monolith|ADR-001]]).

2. **callback_data encoding:** A compact colon-delimited string encodes the action type and the relevant identifier. Three action types for the picker:
   - `pick:<metric_id>` — user selected a metric; `metric_id` is the UUID of the selected metric (36-char UUID fits within the 64-byte limit alongside the prefix).
   - `create:<typed_name>` — user pressed the "Create [typed_name]" button; `typed_name` is the user's typed string, truncated to fit within the 64-byte total limit.
   - `cancel` — user pressed the Cancel button; 6 bytes; no payload. Routed to the FR31/FR32 Idle-transition path from ANY non-Idle ConversationState (not only PendingMetricPicker); the state gate in Decision step 3 does NOT reject this action type even when state ≠ PendingMetricPicker.

3. **State gate:** The CallbackQuery handler checks the user's ConversationState via USG before dispatching. If state ≠ `PendingMetricPicker` AND `callback_data ≠ "cancel"`, the callback is rejected: Telegram's `answer_callback_query` is called (required to clear the "loading" spinner), and the user receives "Session expired. Please re-issue the command." (UC16 E3). No state change occurs. Exception: `callback_data = "cancel"` bypasses the state gate and always routes to the FR31/FR32 outcome (ConversationState → Idle from any non-Idle state).

4. **Ownership-validation before use:** For `pick:<metric_id>`, the Data Repository confirms the metric belongs to `internal_user_id` before any downstream action. This prevents a crafted or replayed callback from acting on another user's metric.

5. **Telegram `answer_callback_query` always called:** The handler always answers the callback (even on error) to remove the loading indicator from the client. Failure to answer within 60 seconds results in a "loading" state on the Telegram client.

# Alternatives Considered

## A1 Separate callback handler per callback type (no shared routing through Dispatcher)

- Pros: simpler per-feature handler; no need to parse callback_data at a central point
- Cons: duplicates the ConversationState gate and ownership-validation logic in each handler; no single place to enforce the "always answer_callback_query" rule; as inline keyboard features multiply, the pattern diverges; harder to add cross-cutting concerns (observability, error handling) later
- Why not: the ConversationState gate and answer_callback_query obligation are cross-cutting; centralizing in Dispatcher enforces them uniformly. The cost of parsing a compact callback_data string is negligible.

## A2 State-only routing — no callback_data encoding; derive action from ConversationState alone

- Pros: zero bytes used in callback_data; simplest keyboard construction
- Cons: when ConversationState = PendingMetricPicker, Dispatcher cannot distinguish "metric selected" from "Create button pressed" without reading state_data from DB and comparing; adds a mandatory DB read before routing; for the "Show all fits" expansion (FR25), the current message_id is also needed to edit the message — this cannot be derived from state alone; future keyboards with more action types break this approach immediately
- Why not: routing should not require a DB read before the action is determined. callback_data encoding is cheap, fits within the 64-byte limit, and is the standard Telegram Bot API pattern.

## A3 Encode full command context in callback_data instead of relying on ConversationState state_data

- Pros: each callback is self-contained; no state_data lookup needed
- Cons: 64-byte limit becomes tight when encoding command_context + metric_id + typed_name together; ConversationState is already the authoritative source of command_context (FR29, DM6); duplicating it in callback_data creates a consistency risk if state and callback diverge (e.g., new picker replaces old one per BR13 but old button still in Telegram chat history)
- Why not: ConversationState is the source of truth per the existing design. callback_data encodes only the opaque identifier needed for routing dispatch; command_context is read from state_data after the state gate passes.

# Consequences

## Positive
- Single routing point for all callback events; ConversationState gate and answer_callback_query obligation enforced once
- Compact callback_data (≤64 bytes) fits Telegram's limit with both action types
- Ownership validation at the routing layer prevents stale/replayed callbacks from acting on wrong user data
- Future inline keyboard features follow the same pattern: register callback handler in Dispatcher, define callback_data action type, add state gate

## Negative
- Message Dispatcher now handles two distinct aiogram event types (Message and CallbackQuery); test coverage must include both paths
- The 64-byte callback_data limit constrains `typed_name` in the `create:<typed_name>` action; typed names longer than ~57 bytes must be truncated. This is acceptable: the full typed_name is preserved in DM6 ConversationState state_data and is not reconstructed from callback_data.
- Stale inline keyboards in Telegram chat history (from a previous picker session) remain visible to the user after the session expires. Pressing a non-cancel button on a stale keyboard triggers UC16 E3 gracefully. Pressing the Cancel button on a stale keyboard always works (it routes to FR31/FR32 from any non-Idle state), providing a reliable escape path even from stale UIs.
- The ownership-validation DB read (Decision step 4) adds a mandatory DB round-trip on every CallbackQuery event; within the NFR18 budget at stated scale (≤20 users × ≤20 metrics); re-evaluate at the 20-user ceiling.

## Follow-ups
- Define the exact callback_data separator and encoding rules (colon-delimited vs. JSON prefix) in the implementation spec; colon-delimited is preferred for byte efficiency.
- Integration tests must cover: (a) valid callback in correct state; (b) valid callback in wrong state (E3); (c) callback with metric_id belonging to different user (rejected); (d) stale callback after picker session replaced by new one (BR13).
- ~~Add `picker_invocation_event` to the Observability event registry~~ — confirmed: `picker_invocation_event` already registered in overview.md Observability section.

# NFRs affected

- NFR18 (picker keyboard ≤5s p95): routing CallbackQuery through Dispatcher adds negligible overhead; dominant cost is DB metric catalog query and Telegram outbound API call — both within the same budget as NFR1/NFR2
- NFR6 (per-user isolation): ownership-validation at routing layer adds an explicit enforcement point beyond the repository-layer guard (ADR-005)
- NFR4 (uptime): answer_callback_query obligation prevents Telegram from showing indefinite "loading" on client, reducing user-visible degradation during partial failures
