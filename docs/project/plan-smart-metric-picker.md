---
doc: PLAN
feature: smart-metric-picker
project: checkpoint_recorder
version: 0.1
status: draft
owner: project-manager
reviewed_by: null
score: null
activities: [logging, management]
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: arch, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
  - {doc: uc-16, version: 0.1}
  - {doc: adr-013, version: 0.1}
updated: 2026-04-28
tags: [project-docs, plan, feature-addition]
---

# Feature Overview

The smart-metric-picker adds an inline keyboard metric selection flow to the checkpoint_recorder Telegram bot. When a user issues any metric-name-required command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`) with no argument, or with a fuzzy/misspelled argument, the bot presents their metric catalog as pressable inline buttons ordered by recency of last entry. The feature also introduces two new `ConversationState` nodes (`PendingMetricPicker`, `PendingPickerValue`), a Telegram `CallbackQuery` routing path through the Message Dispatcher, a recency-ordered metric catalog query in the Data Repository, and a "Create [typed_name]" button for zero-match logging flows — enabling users to navigate and create metrics without remembering exact names.

Sizing conventions used throughout:

- T-shirt: XS < 1 day · S 1–3 days · M 3–10 days · L 10–30 days · XL > 30 days
- Tokens: XS < 5k · S 5k–20k · M 20k–80k · L 80k–300k · XL > 300k

# Milestones

- **M1 Core FSM + DB** — tasks: T1, T2, T3. Database enum extended; new ConversationState nodes operational; /cancel handles new states; `FUZZY_MATCH_THRESHOLD` config var registered. No user-visible picker yet.
- **M2 Picker UX flows** — tasks: T4, T5, T6, T7. CallbackQuery routing live; inline keyboard assembled and dispatched; bare-command and fuzzy-name triggers functional; logging flow (PendingPickerValue → Entry) end-to-end.
- **M3 Management path + cancel** — tasks: T8, T9, T10, T11. All five management commands intercept at picker; zero-match, overflow (Show all fits), and scheduler timeout cleanup paths complete; BR13 replacement behavior confirmed.
- **M4 Observability** — tasks: T12. `picker_invocation_event` emitted; `picker_keyboard_latency_ms` SLO tracked. Feature complete.

# Work Breakdown Structure

## T1 Alembic migration — DM6 enum extension <- FR29, FR30, DM6
- size: S
- tokens: ~10k
- confidence: high
- owner: Developer
- depends_on: []
- milestone: M1
- done: New Alembic revision adds `PendingMetricPicker` and `PendingPickerValue` to the `conversation_state_enum` PostgreSQL enum; migration runs cleanly on a fresh DB and on a DB with existing rows; `ConversationStateEnum` in `models.py` extended with both values; rollback revision defined; no data loss on existing rows.

## T2 Config — fuzzy threshold <- FR23, SU-010
- size: XS
- tokens: ~2k
- confidence: high
- owner: Developer
- depends_on: [T1]
- milestone: M1
- notes: Picker timeout reuses existing `periodicity_prompt_expiry_hours` (24h default, SU-009) — no new setting needed (Q-PM-3 Option A). T10 reads `settings.periodicity_prompt_expiry_hours` directly.
- done: `fuzzy_match_threshold: int = 70` added to `Settings` in `config.py`; env var `FUZZY_MATCH_THRESHOLD` documented; default matches SU-010.

## T3 USG and /cancel — handle PendingMetricPicker and PendingPickerValue <- FR29, FR30, FR31, BR13
- size: S
- tokens: ~8k
- confidence: high
- owner: Developer
- depends_on: [T1]
- milestone: M1
- done: `ConversationStateEnum.PendingMetricPicker` and `PendingPickerValue` are imported everywhere `ConversationStateEnum` is referenced; `cmd_cancel` in `handlers/message.py` clears both new states to Idle correctly (existing code clears by `state != Idle` — no change needed, verified by test); `handle_text` in `handlers/message.py` has an explicit branch for `PendingMetricPicker` (sends reminder: "Please select a metric from the keyboard above, or use /cancel.") and `PendingPickerValue` (re-prompts for numeric value); existing `/cancel` integration test updated to cover both new states.

## T4 NLP Engine — fuzzy picker trigger <- FR23, SU-010
- size: S
- tokens: ~12k
- confidence: med
- owner: Developer
- depends_on: [T2, T3]
- milestone: M2
- notes: NLP Engine currently uses `token_sort_ratio` at 75 for same-metric match and 40 for ambiguity floor. The picker trigger uses `token_set_ratio` at threshold `settings.fuzzy_match_threshold` (default 70) against the metric name token extracted from the command argument — a different code path from the existing free-text parse. Risk of confusion with existing fuzz paths; isolated to a new function.
- done: New function `fuzzy_match_metrics(typed_name: str, known_metrics: list[str], threshold: int) -> list[str]` in `nlp_engine.py`; uses `token_set_ratio` case-insensitive; returns list of matching names sorted by score descending; returns empty list if zero matches; unit-tested with at least 5 cases (exact match, partial overlap, below threshold, empty catalog, Unicode name).

## T5 Data Repository — recency-ordered metric catalog query <- FR24
- size: S
- tokens: ~10k
- confidence: high
- owner: Developer
- depends_on: [T1]
- milestone: M2
- done: New async function `get_metrics_ordered_by_recency(session, user_id) -> list[Metric]` in `metric_manager.py`; SQL uses `LEFT JOIN entries GROUP BY metric.id ORDER BY MAX(entry_timestamp) DESC NULLS LAST, metric.name ASC`; scoped by `internal_user_id` (ADR-005); includes Active and Archived metrics (UC16 edge case: archived metrics remain in picker pool); unit-tested with three scenarios: all metrics have entries, some have no entries, all have no entries.

## T6 Inline keyboard builder <- FR22, FR24, FR25, FR27, FR28
- size: M
- tokens: ~25k
- confidence: med
- owner: Developer
- depends_on: [T4, T5]
- milestone: M2
- notes: `callback_data` encoding must fit within Telegram's 64-byte limit. `pick:<uuid>` = 41 bytes (safe). `create:<typed_name>` truncates `typed_name` at 57 chars (= 64 - len("create:") = 57). Full typed_name always available in `state_data`. FR25 overflow threshold is > 4 (not >= 4).
- done: New module `components/picker_keyboard.py` with three public functions: (1) `build_picker_keyboard(metrics: list[Metric], overflow_threshold=4) -> InlineKeyboardMarkup` — returns top-4 + "Show all fits" button if `len(metrics) > 4`, else all metrics; (2) `build_create_keyboard(typed_name: str) -> InlineKeyboardMarkup` — single "Create [typed_name]" button with `create:<truncated>` callback data; (3) `build_zero_match_message() -> str` — returns the management zero-match text string (FR28). Callback data format: `pick:<metric_id_uuid_str>` and `create:<typed_name>`. Unit tests: 3-metric list (no overflow), 5-metric list (overflow), truncation of long typed_name, empty metric list raises or returns empty gracefully.

## T7 Message Dispatcher — CallbackQuery handler and state gate <- FR29, ADR-013
- size: M
- tokens: ~25k
- confidence: med
- owner: Developer
- depends_on: [T6]
- milestone: M2
- notes: aiogram 3.x `@router.callback_query(...)` decorator registers handler. **No middleware changes required** — `UserSessionGuardMiddleware` already handles CallbackQuery events via `_extract_from_user` (confirmed in `user_guard.py` lines 41-42; registered as `dispatcher.update.outer_middleware`). State gate must reject callbacks when state != PendingMetricPicker and call `answer_callback_query` unconditionally (ADR-013 Decision step 5). Minor edge case: if a PendingDeletion user triggers a callback, the middleware injects data but does not dispatch the restoration prompt (message-only path in line 121 of user_guard.py); callback handler should check `user.account_status` and return gracefully. Ownership validation (metric_id belongs to requesting user) adds one DB read per callback (ADR-013 Consequence — acceptable within NFR18 budget).
- done: New `handlers/picker_callback.py` module; registers `CallbackQuery` handler on `Router`; handler: (1) calls `answer_callback_query` unconditionally at start; (2) checks ConversationState = PendingMetricPicker via USG — if not, replies "Session expired. Please re-issue the command." and returns (UC16 E3); (3) checks `user.account_status != Active` → answer and return; (4) parses `callback_data` prefix (`pick:` vs `create:`); (5) for `pick:`, validates metric UUID belongs to user (Data Repository read); (6) fetches last-3 entry values for selected metric and assembles selection confirmation + last-3-values context message (FR26) as single message; (7) dispatches state transition per `command_context` from `state_data` (logging → PendingPickerValue; management → Idle then delegate); router registered in `bot.py`.

## T8 Picker flow — logging path <- FR26, FR27, FR30
- size: M
- tokens: ~35k
- confidence: med
- owner: Developer
- depends_on: [T7]
- milestone: M2
- notes: This task closes the logging picker loop: bare command or fuzzy free-text → picker keyboard → metric selection → last-3-values shown → PendingPickerValue state → numeric value received → Entry created. Also handles the Create button zero-match path: Create button → PendingPeriodicity (reuses existing `handle_periodicity_response`; typed_name pre-filled). The bare free-text trigger requires the most careful integration: NLP Engine currently goes to PendingPeriodicity for unrecognized metric names; FR27 requires interception before that path when zero fuzzy matches exist. Existing `process_entry` must be modified.
- done: `process_entry` in `entry_processor.py` modified: after NLP `auto-parse` with unknown metric name, run `fuzzy_match_metrics`; if >= 1 match, dispatch picker keyboard (PendingMetricPicker with `command_context=logging`); if zero matches, dispatch Create button keyboard (PendingMetricPicker with `command_context=logging`, `typed_name=<extracted>`); PendingPeriodicity path now only reached from Create button callback (A2 in UC16); `handle_text` branch for `PendingPickerValue` receives numeric value → creates Entry atomically → clears state → dispatches confirmation; non-numeric value in PendingPickerValue returns re-prompt (UC16 E4); end-to-end test: free-text "wight 80" → picker shown → metric selected → "Enter value for weight:" → "80" → Entry confirmed.

## T9 Picker flow — management path <- FR22, FR28, FR29
- size: M
- tokens: ~30k
- confidence: med
- owner: Developer
- depends_on: [T7]
- milestone: M3
- notes: Five commands need updating: `/metric_archive`, `/metric_reactivate`, `/metric_delete`, `/alert_set`, `/chart`. Current handlers use `get_metric_by_name` for exact match and return error on no-match. They must now: (1) if no arg → dispatch picker (bare command, FR22); (2) if arg and exact match → proceed as before; (3) if arg and fuzzy match(es) → dispatch picker (FR23); (4) if arg and zero matches → dispatch zero-match message (FR28) and return. Post-selection, picker callback handler delegates back to each command's execution logic with the resolved metric_id. `command_context` stored in `state_data` determines which execution path runs after selection.
- done: All five command handlers updated; each follows the 4-branch pattern (no arg, exact match, fuzzy match, zero match); picker callback handler dispatches to management execution functions by `command_context`; `/chart` post-selection continues the existing `_deliver_chart` coroutine with resolved `metric_id`; `/alert_set` post-selection resumes alert configuration with resolved metric; `/metric_archive`, `/metric_reactivate` post-selection immediately execute and return to Idle; `/metric_delete` post-selection enters `PendingMetricDeletionConfirmation` with resolved metric_id; integration tests for each command's bare trigger.

## T10 Scheduled Process — picker state timeout cleanup <- FR29, FR30, SU-009
- size: S
- tokens: ~12k
- confidence: high
- owner: Developer
- depends_on: [T1, T8, T9]
- milestone: M3
- notes: Reuses `settings.periodicity_prompt_expiry_hours` (24h default) for picker timeout — no new config field (Q-PM-3 Option A). The Scheduled Process already has a `stale PendingPeriodicity cleanup` job; the same pattern applies to `PendingMetricPicker` and `PendingPickerValue`.
- done: Scheduled Process extended with cleanup for `PendingMetricPicker` and `PendingPickerValue` states older than `settings.periodicity_prompt_expiry_hours`; per-user Telegram notification dispatched ("Metric selection timed out. No action was taken." for PendingMetricPicker; "Value entry timed out. No entry was stored." for PendingPickerValue); ConversationState set to Idle; `conversation_state_event`(type=picker_timeout) emitted per cleared state; idempotent (zero stale rows case handled).

## T11 Show all fits — overflow expansion <- FR25
- size: S
- tokens: ~12k
- confidence: med
- owner: Developer
- depends_on: [T7]
- milestone: M3
- notes: "Show all fits" is a separate callback action type. Its `callback_data` must encode the action without a metric_id: proposed format `showfits` (8 bytes, well within 64-byte limit). The handler edits the current message (replaces inline keyboard) with the full list. If edit fails, original message remains visible and error is logged (UC16 E2). The full list is re-fetched and re-sorted (FR24) at press time to ensure freshness.
- done: `callback_data` format `showfits` registered in picker_keyboard.py and picker_callback.py; callback handler fetches full metric list (for bare command) or full fuzzy-match list (for typed-name context from `state_data`); edits the existing Telegram message with new `InlineKeyboardMarkup`; on Telegram edit failure: logs error, replies "Could not expand list. Please select from the visible options." (UC16 E2); state remains PendingMetricPicker throughout; unit test: 5-metric list → overflow button present; integration test: press overflow → all 5 metrics displayed.

## T12 Observability — picker events and SLO <- NFR9 analog, NFR18
- size: S
- tokens: ~10k
- confidence: high
- owner: Developer
- depends_on: [T7, T8, T9]
- milestone: M4
- done: `picker_invocation_event` emitted at each picker keyboard dispatch with fields `{user_id, command_context, trigger_type: "bare"|"fuzzy", matched_count, typed_name_present: bool}`; `picker_keyboard_latency_ms` recorded in event payload (timestamp delta from command receipt to keyboard send); `raw_input` / `typed_name` excluded from all event payloads per NFR8 — `typed_name_present` boolean used instead; `picker_selection_event` emitted on each metric selection with `{user_id, command_context, metric_id, has_entries: bool}`; schema validation at ObservabilityCollector boundary rejects events with `typed_name` field (same gate as `raw_input`).

# Critical Path

The critical path is sequential through the infrastructure and keyboard machinery before any user-facing flow is testable:

**T1 → T3 → T4 → T5 → T6 → T7 → T8**

Explanation:
- T1 (migration) must precede T3 (USG imports new enum values).
- T3 (USG + cancel) and T2 (config) are prerequisites for T4 (NLP fuzzy function) and T5 (recency query).
- T4 and T5 must both complete before T6 (keyboard builder) can be meaningfully tested.
- T6 must complete before T7 (CallbackQuery dispatcher) can dispatch to built keyboards.
- T7 must complete before T8 (logging flow) or T9 (management flow) can close the loop.
- T8 is on the critical path (not T9) because it is the more complex state transition.

Parallelizable work:
- T2 (config) runs in parallel with T1 after day 0.
- T5 (recency query) runs in parallel with T4 after T1 completes.
- T9 (management path) runs in parallel with T8 after T7 completes.
- T10 (scheduler cleanup) runs in parallel with T8/T9 after T1 completes.
- T11 (Show all fits) runs in parallel with T8/T9 after T7 completes.
- T12 (observability) runs in parallel with T9/T10/T11 after T7 completes.

Critical path token total: T1(10k) + T3(8k) + T4(12k) + T5(10k) + T6(25k) + T7(25k) + T8(35k) = **~125k tokens** (M–L range).

# RACI

Solo project — the Developer role is one person assisted by AI agents. The RACI reflects accountability ownership, not separate individuals.

| Deliverable | Developer | AI Agent |
|---|---|---|
| Alembic migration (T1) | A/R | C |
| Config additions (T2) | A/R | R (primary implementation) |
| USG + cancel updates (T3) | A/R | R (primary implementation) |
| NLP fuzzy function (T4) | A/R | R (primary implementation) |
| Recency query (T5) | A/R | R (primary implementation) |
| Keyboard builder module (T6) | A/R | R (primary implementation) |
| CallbackQuery handler (T7) | A/R | R (primary implementation) |
| Logging picker flow (T8) | A/R | R (primary implementation) |
| Management picker flow (T9) | A/R | R (primary implementation) |
| Scheduler picker cleanup (T10) | A/R | R (primary implementation) |
| Show all fits overflow (T11) | A/R | R (primary implementation) |
| Observability events (T12) | A/R | R (primary implementation) |
| Production deployment | A/R | C |

A = Accountable. R = Responsible. C = Consulted.

# Risk Register

## RISK-F1 Alembic enum extension on live PostgreSQL
- description: PostgreSQL `ALTER TYPE ... ADD VALUE` for an existing enum is non-transactional; if the migration script wraps the statement in a transaction block (Alembic default), it will fail on PostgreSQL < 12. On PostgreSQL >= 12 it is supported but must run outside of DDL transaction in certain configurations. Supabase runs PostgreSQL 15 but the migration generator pattern must be verified.
- probability: M
- impact: H
- owner: Developer
- mitigation: Use `op.execute("ALTER TYPE conversation_state_enum ADD VALUE IF NOT EXISTS 'PendingMetricPicker'")` inside `with op.get_context().autocommit_block():`; test migration on a clean Supabase branch before production deploy; include rollback test.
- trigger: Migration fails with "cannot ALTER TYPE ... inside a transaction block"

## RISK-F2 64-byte callback_data limit with UUID and typed_name
- description: `pick:<uuid>` = 41 bytes (safe). `create:<typed_name>` budget is 57 bytes for `typed_name`. Users whose metric names exceed 57 characters (allowed up to 100 chars by DM2) will have truncated `typed_name` in callback_data. ADR-013 acknowledges this; full name is in `state_data`. However, if `state_data` is stale or mismatched at press time (e.g., user presses old button), the system reconstructs the wrong name.
- probability: L
- impact: M
- owner: Developer
- mitigation: Always use `state_data.typed_name` as the authoritative source; callback_data `typed_name` is used only as a fallback if `state_data` is absent; add UC16 E3 state-gate check before any `create:` callback action; document 57-char truncation in picker_keyboard.py.
- trigger: User has metric name > 57 chars; presses Create button on stale session

## RISK-F3 process_entry modification breaks existing auto-create flow
- description: T8 requires modifying `process_entry` to intercept the unrecognized-name path and route to the picker instead of directly entering `PendingPeriodicity`. This is the highest-risk code change because it alters a core path tested in T3 of the original plan (auto-parsed entry, metric auto-creation). A regression here would silently break all new-metric creation from free-text entries.
- probability: M
- impact: H
- owner: Developer
- mitigation: Write regression tests for existing `process_entry` paths before modifying; make the new fuzzy-intercept branch conditional on `settings.fuzzy_match_threshold > 0` (feature flag); perform modification in a separate git commit from the keyboard builder so bisect is easy.
- trigger: `process_entry` tests fail after T8 implementation; or end-to-end test for "new metric via free text" stops working

## RISK-F4 CallbackQuery handler registration order in aiogram router
- description: aiogram 3.x resolves handlers in registration order. If the new `CallbackQuery` router is registered after the existing `Message` router in `bot.py`, there is no conflict. However if any existing handler uses a catch-all `F.data` filter on CallbackQuery (unlikely but possible), it would shadow the picker handler. USG middleware coverage confirmed: `_extract_from_user` in `user_guard.py` explicitly handles `event.callback_query`; both middlewares registered as `dispatcher.update.outer_middleware` which covers all update types (Q-PM-2 resolved).
- probability: L
- impact: M
- owner: Developer
- mitigation: Audit `bot.py` router registration order before T7 implementation to confirm no catch-all CallbackQuery filter exists; ensure `answer_callback_query` is called unconditionally (ADR-013 Decision step 5).
- trigger: Picker callback produces 60s "loading" spinner on Telegram client

## RISK-F5 Recency query performance with zero-entry metrics
- description: The recency-ordering SQL uses `LEFT JOIN` on entries + `MAX(entry_timestamp) NULLS LAST`. At ≤20 users × ≤20 metrics this is trivially fast. However if the query returns the full catalog every time a picker is displayed, and if the catalog grows (no hard cap in SRS), the query latency could approach the NFR18 5s budget in edge cases where many metrics have no entries (alphabetical sort of NULLS is done in Python, not DB).
- probability: L
- impact: M
- owner: Developer
- mitigation: Push the full sort (recency DESC NULLS LAST, name ASC for NULLS) into the SQL ORDER BY clause rather than Python-side; add `EXPLAIN ANALYZE` result note in query comment; stay within documented 20-user ceiling.
- trigger: picker_keyboard_latency_ms event shows p95 > 2s in production

## RISK-F6 Stale inline keyboard in Telegram chat history (BR13 replacement)
- description: When a user issues a new picker command while `PendingMetricPicker` is already active (BR13 — at most one picker per user), the old keyboard remains visible in the Telegram chat. Pressing a button on the old keyboard triggers UC16 E3 (state gate rejects it), but the user may be confused. Telegram does not provide a reliable API to retroactively disable or delete old inline keyboards.
- probability: M
- impact: L
- owner: Developer
- mitigation: When a new picker supersedes an old one (BR13 enforcement in the picker dispatch path), attempt to `edit_message_reply_markup(message_id, reply_markup=None)` to clear the old keyboard's buttons; catch and log on failure (edit may fail if message is too old); message E3 is explicit: "Session expired. Please re-issue the command."
- trigger: User has multiple stale picker keyboards in chat history; presses one and gets E3

## RISK-F7 NLP fuzzy trigger overlaps existing ambiguous-parse path
- description: The existing NLP Engine uses `token_sort_ratio` at threshold 40–75 for disambiguation (ParseAttempt flow). The new picker trigger uses `token_set_ratio` at threshold 70 (SU-010) for a different purpose. These are separate code paths (`parse` vs. `fuzzy_match_metrics`), but the scoring functions differ. If the NLP Engine is modified carelessly in T4, the existing disambiguation scores may change.
- probability: L
- impact: M
- owner: Developer
- mitigation: Implement `fuzzy_match_metrics` as a new standalone function that does NOT alter or reuse `_SAME_METRIC_SIMILARITY` or `_AMBIGUOUS_FLOOR` constants; add docstring explaining separation; unit-test both old and new fuzzy paths in the same test module.
- trigger: Disambiguation test cases (ParseAttempt) change scores after T4 implementation

## RISK-F8 PendingPickerValue timeout leaves user without notification
- description: `PendingPickerValue` timeout is handled by the Scheduled Process (T10), which runs at ≤12h cadence. If a user abandons a picker mid-flow and returns within 12h, they may find themselves still in `PendingPickerValue` state with no reminder. Any free-text message should show a re-prompt, but the Scheduled Process does not send the timeout notification until the next scheduler run.
- probability: M
- impact: L
- owner: Developer
- mitigation: The `PendingPickerValue` branch in `handle_text` (T3) already sends a re-prompt on any free-text message; this provides immediate feedback even before the scheduler runs; document the up-to-12h notification gap in the feature spec as a known behavior.
- trigger: User abandons PendingPickerValue state; returns within 12h; receives re-prompt from handle_text but no timeout notice until scheduler runs

# Total Token Budget

Actual figures are **output tokens only** (measured from the session transcript). The original estimates targeted total context-window consumption, which is typically 3–5× larger than output tokens alone — this explains the systematic overestimate.

| Stage | T-shirt | Estimated | Actual (output tokens) |
|---|---|---|---|
| **Documentation pipeline** | | | |
| BA stage (business analysis) | | — | 75,035 |
| SA stage (system analysis) | | — | 79,662 |
| Arch stage (architecture) | | — | 24,152 |
| PM stage (project plan + Q&A) | | — | 36,221 |
| *Docs subtotal* | | — | *215,070* |
| **Visual design** | | | |
| Picker UX mockup (HTML) | | — | 9,926 |
| **Implementation** | | | |
| Pre-implementation reading | | — | 6,419 |
| T1 Migration | S | ~10k | ~1,974 ¹ |
| T2 Config | XS | ~2k | ¹ included in T1 |
| T3 USG + cancel | S | ~8k | ~846 |
| T4 NLP fuzzy trigger | S | ~12k | ~584 |
| T5 Recency query | S | ~10k | ~1,669 |
| T6 Keyboard builder | M | ~25k | ~1,102 |
| T7 CallbackQuery handler | M | ~25k | ~22,304 ² |
| T8 Logging picker flow | M | ~35k | ² included in T7 |
| T9 Management picker flow | M | ~30k | ~16,030 |
| T10 Scheduler cleanup | S | ~12k | ~2,425 |
| T11 Show all fits | S | ~12k | ~1,039 |
| T12 Observability | S | ~10k | ~747 |
| *Implementation subtotal* | | *~191k* | *~54,139* |
| **Session overhead** | | | |
| Current session (Q&A, review) | | — | 12,565 |
| **Grand total** | | — | **~291,700** |

¹ T1 and T2 were implemented in the same parallel batch; output tokens are combined.  
² T7 and T8 were implemented in the same continuous pass; output tokens are combined.

**Original confidence band: ±25%** → range **143k – 239k tokens** (upper-M to lower-L range). This band applied to implementation only and was measuring context-window tokens, not output tokens.

Primary variance driver: T8 (process_entry surgery — highest regression risk, see RISK-F3). This held true in practice: T7+T8 together accounted for 41% of all implementation output tokens.

# Open Questions

Resolved:
- ~~Q-PM-1~~ T13 excluded from plan; tests handled in a separate activity.
- ~~Q-PM-2~~ USG middleware confirmed to cover CallbackQuery via `_extract_from_user` in `user_guard.py` — no middleware changes needed in T7.
- ~~Q-PM-3~~ Option A adopted: picker states reuse `settings.periodicity_prompt_expiry_hours` (24h). No new config field needed.
