"""
Inline keyboard CallbackQuery handler for the smart-metric-picker (ADR-013).

Routing rules:
  1. answer_callback_query() called unconditionally (ADR-013 Decision step 5).
  2. cancel bypass: callback_data="cancel" routes to Idle from any non-Idle state
     WITHOUT going through the state gate (FR32, ADR-013 Decision step 3).
  3. ConversationState gate: must be PendingMetricPicker, else E3 (session expired).
  4. Account status check: PendingDeletion/Deleted → silent dismiss.
  5. callback_data dispatch: pick:<uuid> | create:<name> | showfits
  6. Ownership validation before any metric action (ADR-013 Decision step 4).
"""
import uuid

import structlog
from aiogram import Router
from aiogram.types import CallbackQuery
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.components.metric_manager import (
    get_last_entries,
    get_metrics_ordered_by_recency,
)
from checkpoint_recorder.components.picker_flow import format_last_values
from checkpoint_recorder.components.picker_keyboard import (
    build_all_fits_keyboard,
    build_picker_keyboard,
)
from checkpoint_recorder.db.models import (
    AccountStatus,
    ConversationState,
    ConversationStateEnum,
    InternalUser,
    Metric,
    MetricStatus,
)

log = structlog.get_logger()
router = Router(name="picker_callback")


@router.callback_query()
async def handle_picker_callback(
    callback: CallbackQuery,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    # Step 1: always answer to clear Telegram's loading spinner (ADR-013)
    await callback.answer()

    data: str = callback.data or ""
    # Step 2: cancel bypasses the state gate — routes to Idle from any non-Idle state (FR32)
    if data == "cancel":
        await _handle_cancel(callback, conv_state, session)
        return

    # Step 3: state gate — reject stale/unexpected callbacks (UC16 E3)
    if conv_state.state != ConversationStateEnum.PendingMetricPicker:
        await callback.message.answer(
            "Session expired. Please re-issue the command."
        )
        return

    # Step 4: account status gate (edge case: PendingDeletion user pressed old button)
    if user.account_status != AccountStatus.Active:
        return

    # Step 5: route by callback_data prefix
    if data == "showfits":
        await _handle_show_fits(callback, conv_state, session, user)
    elif data.startswith("create:"):
        await _handle_create(callback, conv_state, session)
    elif data.startswith("pick:"):
        await _handle_pick(callback, conv_state, session, user)
    else:
        log.warning("picker_unknown_callback", data=data, user_id=str(user.id))
        await callback.message.answer("Unknown action. Please try again.")


async def _handle_cancel(
    callback: CallbackQuery,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Cancel button pressed — dismiss picker keyboard, return to Idle (FR32, UC16 A6)."""
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        log.warning("picker_cancel_edit_failed", message_id=callback.message.message_id)

    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()
    await callback.message.answer("Cancelled. You're back to the main menu.")


async def _handle_show_fits(
    callback: CallbackQuery,
    conv_state: ConversationState,
    session: AsyncSession,
    user: InternalUser,
) -> None:
    """Expand overflow: edit the keyboard to show all matching metrics (FR25)."""
    state_data: dict = conv_state.state_data or {}
    typed_name: str = state_data.get("typed_name", "")

    all_metrics = await get_metrics_ordered_by_recency(session, user.id)

    if typed_name:
        from checkpoint_recorder.components.nlp_engine import fuzzy_match_metrics
        from checkpoint_recorder.config import settings
        match_names = set(
            fuzzy_match_metrics(typed_name, [m.name for m in all_metrics], settings.fuzzy_match_threshold)
        )
        display_metrics = [m for m in all_metrics if m.name in match_names]
    else:
        display_metrics = all_metrics

    keyboard = build_all_fits_keyboard(display_metrics)
    try:
        await callback.message.edit_reply_markup(reply_markup=keyboard)
    except Exception:
        log.warning("picker_edit_keyboard_failed", user_id=str(user.id))
        await callback.message.answer(
            "Could not expand list. Please select from the visible options."
        )


async def _handle_create(
    callback: CallbackQuery,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Create button pressed — transition to PendingPeriodicity (FR27)."""
    state_data: dict = conv_state.state_data or {}
    typed_name: str = state_data.get("typed_name", "")
    pending_value = state_data.get("pending_value")
    original_timestamp = state_data.get("original_timestamp")
    raw_input = state_data.get("raw_input", "")

    if not typed_name or pending_value is None:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        await callback.message.answer("Something went wrong. Please try again.")
        return

    conv_state.state = ConversationStateEnum.PendingPeriodicity
    conv_state.state_data = {
        "pending_metric_name": typed_name,
        "pending_value": pending_value,
        "original_timestamp": original_timestamp,
        "raw_input": raw_input,
    }
    await session.commit()

    await callback.message.answer(
        f"New metric: <b>{typed_name}</b>\n\n"
        "How often do you track this?\n"
        "Reply with <b>daily</b> or <b>weekly</b>"
    )


async def _handle_pick(
    callback: CallbackQuery,
    conv_state: ConversationState,
    session: AsyncSession,
    user: InternalUser,
) -> None:
    """Metric selected — validate ownership, show last-3-values, dispatch next step (FR26)."""
    data: str = callback.data or ""
    metric_id_str = data[len("pick:"):]

    # Parse and validate UUID
    try:
        metric_id = uuid.UUID(metric_id_str)
    except ValueError:
        await callback.message.answer("Invalid selection. Please try again.")
        return

    # Ownership validation (ADR-013 Decision step 4)
    metric_row = await session.execute(
        select(Metric).where(
            Metric.id == metric_id,
            Metric.internal_user_id == user.id,
            Metric.status.in_([MetricStatus.Active, MetricStatus.Archived]),
        )
    )
    metric = metric_row.scalar_one_or_none()
    if metric is None:
        await callback.message.answer(
            "Metric not found or access denied. Please re-issue the command."
        )
        return

    # Fetch last 3 entries for context (FR26)
    entries = await get_last_entries(session, metric.id, limit=3)
    context_text = format_last_values(metric, entries)

    state_data: dict = conv_state.state_data or {}
    command_context: str = state_data.get("command_context", "logging")
    original_timestamp = state_data.get("original_timestamp")

    await observability.emit(
        session,
        "picker_invocation_event",
        {
            "user_id": str(user.id),
            "command_context": command_context,
            "trigger_type": "selection",
            "metric_id": str(metric.id),
        },
    )

    if command_context == "logging":
        # Transition to PendingPickerValue — wait for user's numeric value
        conv_state.state = ConversationStateEnum.PendingPickerValue
        conv_state.state_data = {
            "metric_id": str(metric.id),
            "metric_name": metric.name,
            "original_timestamp": original_timestamp,
            "command_context": "logging",
        }
        await session.commit()

        await callback.message.answer(
            f"{context_text}\n\nEnter new value for <b>{metric.name}</b>:"
        )

    else:
        # Management command — dispatch to the appropriate execution function (T9)
        await _dispatch_management(
            callback, conv_state, session, user, metric, command_context
        )


async def _dispatch_management(
    callback: CallbackQuery,
    conv_state: ConversationState,
    session: AsyncSession,
    user: InternalUser,
    metric: Metric,
    command_context: str,
) -> None:
    """
    Dispatch post-selection logic for management commands.
    Implementations are wired in T9; stubs return informative errors until then.
    """
    from checkpoint_recorder.components import picker_management

    handler = {
        "archive": picker_management.execute_archive,
        "reactivate": picker_management.execute_reactivate,
        "delete": picker_management.execute_delete,
        "alert_set": picker_management.execute_alert_set,
        "chart": picker_management.execute_chart,
    }.get(command_context)

    if handler is None:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        await callback.message.answer(
            f"Unknown command context '{command_context}'. Action cancelled."
        )
        return

    reply = await handler(session, user, conv_state, metric, callback)
    if reply:
        await callback.message.answer(reply)
