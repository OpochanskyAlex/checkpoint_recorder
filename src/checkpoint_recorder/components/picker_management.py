"""
Post-selection execution functions for management commands in the smart-metric-picker.
Called by picker_callback._dispatch_management after metric ownership is validated.

Each function receives the resolved Metric and carries out the command action,
clearing ConversationState to Idle on completion. Returns a reply string or None
(None means the handler sent the reply itself, e.g. delete confirmation prompt).
"""
import asyncio
import math

import structlog
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.components.metric_manager import (
    archive_metric,
    reactivate_metric,
)
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    InternalUser,
    Metric,
    MetricStatus,
)

log = structlog.get_logger()


async def execute_archive(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    metric: Metric,
    callback: CallbackQuery,
) -> str:
    metric_obj, error = await archive_metric(session, user.id, metric.name)
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    if error:
        await session.commit()
        return error
    await session.commit()
    return (
        f"📦 Metric <b>{metric_obj.name}</b> has been archived.\n"
        "Alert evaluation is suspended. Use /metric_reactivate to restore it."
    )


async def execute_reactivate(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    metric: Metric,
    callback: CallbackQuery,
) -> str:
    metric_obj, error = await reactivate_metric(session, user.id, metric.name)
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    if error:
        await session.commit()
        return error
    await session.commit()
    return (
        f"✅ Metric <b>{metric_obj.name}</b> has been reactivated.\n"
        "Alert evaluation resumes."
    )


async def execute_delete(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    metric: Metric,
    callback: CallbackQuery,
) -> None:
    """Enter PendingMetricDeletionConfirmation for the resolved metric."""
    conv_state.state = ConversationStateEnum.PendingMetricDeletionConfirmation
    conv_state.state_data = {
        "pending_delete_metric_id": str(metric.id),
        "pending_delete_metric_name": metric.name,
    }
    await session.commit()
    await callback.message.answer(
        f"⚠️ Are you sure you want to permanently delete metric <b>{metric.name}</b>?\n\n"
        "This will delete all entries, alerts, and parse attempts.\n\n"
        "This action <b>cannot be undone</b>.\n\n"
        "Reply <b>yes</b> to confirm, or anything else (or /cancel) to abort."
    )
    return None


async def execute_alert_set(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    metric: Metric,
    callback: CallbackQuery,
) -> str:
    """Create alert for the resolved metric using args stored in state_data."""
    from checkpoint_recorder.db.models import Alert, AlertCondition, AlertStatus

    state_data: dict = conv_state.state_data or {}
    condition_str: str = state_data.get("alert_condition", "")
    threshold_raw = state_data.get("alert_threshold")

    if not condition_str or threshold_raw is None:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Alert parameters were lost. Please re-issue /alert_set with all arguments."

    try:
        threshold = float(threshold_raw)
    except (ValueError, TypeError):
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Invalid threshold stored. Please re-issue /alert_set."

    if not math.isfinite(threshold):
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Threshold must be a finite number."

    if metric.status == MetricStatus.Archived:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return (
            f"Metric '<b>{metric.name}</b>' is archived. "
            "Reactivate it first with /metric_reactivate before setting alerts."
        )

    condition = AlertCondition.above if condition_str == "above" else AlertCondition.below
    alert = Alert(
        metric_id=metric.id,
        internal_user_id=user.id,
        condition=condition,
        threshold_value=threshold,
        target_dimension=None,
        status=AlertStatus.Active,
    )
    session.add(alert)
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()

    return (
        f"✅ Alert created!\n\n"
        f"<b>Metric:</b> {metric.name}\n"
        f"<b>Condition:</b> {condition.value} {threshold}\n"
        f"<b>ID:</b> <code>{alert.id}</code>\n\n"
        "You'll receive a notification the next time a new entry meets this condition."
    )


async def execute_chart(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    metric: Metric,
    callback: CallbackQuery,
) -> None:
    """Deliver chart for the resolved metric (reuses _deliver_chart from chart handler)."""
    from checkpoint_recorder.handlers.chart import _deliver_chart
    from checkpoint_recorder.components import observability
    from checkpoint_recorder.config import settings as _settings

    state_data: dict = conv_state.state_data or {}
    days: int = int(state_data.get("chart_days", 30))

    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()

    await observability.emit(
        session,
        "chart_invocation_event",
        {"metric_id": str(metric.id), "user_id": str(user.id), "days": days},
    )
    await session.commit()

    await callback.message.answer(
        f"⏳ Generating chart for <b>{metric.name}</b> (last {days} days)…"
    )

    asyncio.create_task(
        _deliver_chart(
            bot=callback.bot,
            chat_id=callback.message.chat.id,
            user_id=user.id,
            metric_id=metric.id,
            metric_name=metric.name,
            unit=metric.unit,
            dimension_names=metric.dimension_names,
            days=days,
        )
    )
    return None
