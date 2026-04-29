"""
Alert handlers — FR-11: Alert Configuration, FR-13: Alert Re-arming.

Commands:
  /alert_set <metric_name> <above|below> <threshold>
  /alert_rearm <alert_id>
"""
import math
import uuid

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components.metric_manager import (
    get_metric_by_name,
    get_metrics_ordered_by_recency,
    get_user_metric_names,
)
from checkpoint_recorder.components.picker_keyboard import (
    build_picker_keyboard,
    build_zero_match_message,
)
from checkpoint_recorder.db.models import (
    Alert,
    AlertCondition,
    AlertStatus,
    ConversationState,
    ConversationStateEnum,
    InternalUser,
    MetricStatus,
)

log = structlog.get_logger()
router = Router(name="alert")


@router.message(Command("alert_set"))
async def cmd_alert_set(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Configure a threshold alert on a metric (FR-11).

    Usage: /alert_set <metric_name> <above|below> <threshold>
    """
    from checkpoint_recorder.components.nlp_engine import fuzzy_match_metrics
    from checkpoint_recorder.config import settings

    args = (command.args or "").split()

    # Bare command or only metric name — need condition+threshold before we can intercept
    if len(args) < 3:
        await message.answer(
            "Usage: /alert_set <b>&lt;metric_name&gt;</b> <b>&lt;above|below&gt;</b> <b>&lt;threshold&gt;</b>\n\n"
            "Example: /alert_set weight above 90"
        )
        return

    metric_name = args[0]
    condition_str = args[1].lower()
    threshold_str = args[2]

    if condition_str not in ("above", "below"):
        await message.answer("Condition must be <b>above</b> or <b>below</b>.")
        return

    try:
        threshold = float(threshold_str)
    except ValueError:
        await message.answer("Threshold must be a number.")
        return

    if not math.isfinite(threshold):
        await message.answer(
            "Threshold must be a finite number (not NaN or Infinity)."
        )
        return

    # Picker intercept (FR22, FR23)
    metric = await get_metric_by_name(session, user.id, metric_name)
    if metric is None and settings.fuzzy_match_threshold > 0:
        known_names = await get_user_metric_names(session, user.id)
        fuzzy_names = fuzzy_match_metrics(metric_name, known_names, settings.fuzzy_match_threshold)
        extra = {"alert_condition": condition_str, "alert_threshold": threshold}
        if fuzzy_names:
            all_metrics = await get_metrics_ordered_by_recency(session, user.id)
            matching = [m for m in all_metrics if m.name in set(fuzzy_names)]
            conv_state.state = ConversationStateEnum.PendingMetricPicker
            conv_state.state_data = {"command_context": "alert_set", "typed_name": metric_name, **extra}
            await session.commit()
            await message.answer(
                f'No exact match for "<b>{metric_name}</b>". Did you mean:',
                reply_markup=build_picker_keyboard(matching),
            )
            return
        else:
            await message.answer(build_zero_match_message("alert_set"))
            return

    if metric is None:
        await message.answer(
            f"No metric named '<b>{metric_name}</b>' found. "
            "Use /metric_list to see your metrics."
        )
        return

    # AC-FR11-2: reject alerts on Archived metrics
    if metric.status == MetricStatus.Archived:
        await message.answer(
            f"Metric '<b>{metric.name}</b>' is archived. "
            "Reactivate it first with /metric_reactivate before setting alerts."
        )
        return

    condition = AlertCondition.above if condition_str == "above" else AlertCondition.below

    # AC-FR11-3: new Alert starts Active
    alert = Alert(
        metric_id=metric.id,
        internal_user_id=user.id,
        condition=condition,
        threshold_value=threshold,
        target_dimension=None,
        status=AlertStatus.Active,
    )
    session.add(alert)
    await session.commit()

    await message.answer(
        f"✅ Alert created!\n\n"
        f"<b>Metric:</b> {metric.name}\n"
        f"<b>Condition:</b> {condition.value} {threshold}\n"
        f"<b>ID:</b> <code>{alert.id}</code>\n\n"
        "You'll receive a notification the next time a new entry meets this condition."
    )


@router.message(Command("alert_rearm"))
async def cmd_alert_rearm(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """Re-arm a Triggered alert (FR-13).

    Usage: /alert_rearm <alert_id>
    """
    alert_id_str = (command.args or "").strip()
    if not alert_id_str:
        await message.answer("Usage: /alert_rearm <b>&lt;alert_id&gt;</b>")
        return

    try:
        alert_id = uuid.UUID(alert_id_str)
    except ValueError:
        await message.answer("Invalid alert ID. Use /metric_list to find alert IDs.")
        return

    row = await session.execute(
        select(Alert).where(
            Alert.id == alert_id,
            Alert.internal_user_id == user.id,
        )
    )
    alert: Alert | None = row.scalar_one_or_none()

    if alert is None:
        await message.answer("Alert not found.")
        return

    if alert.status == AlertStatus.Active:
        await message.answer(
            f"Alert <code>{alert.id}</code> is already active — nothing to re-arm."
        )
        return

    if alert.status != AlertStatus.Triggered:
        await message.answer(
            f"Alert <code>{alert.id}</code> cannot be re-armed "
            f"(current status: {alert.status.value})."
        )
        return

    # AC-FR13-1: reset to Active; AC-FR13-2: last_triggered_timestamp preserved
    alert.status = AlertStatus.Active
    await session.commit()

    await message.answer(
        f"✅ Alert <code>{alert.id}</code> has been re-armed.\n"
        "It will fire the next time a new entry meets the condition."
    )
