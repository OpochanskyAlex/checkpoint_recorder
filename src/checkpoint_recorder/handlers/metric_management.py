"""
Metric management handlers — FR-8, FR-9, FR-10.

Commands:
  /metric_list
  /metric_archive <name>
  /metric_reactivate <name>
  /metric_delete <name>
"""
import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.components.metric_manager import (
    archive_metric,
    delete_metric_cascade,
    list_metrics_with_activity,
    reactivate_metric,
    get_metric_by_name,
)
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    InternalUser,
    MetricStatus,
)

log = structlog.get_logger()
router = Router(name="metric_management")


@router.message(Command("metric_list"))
async def cmd_metric_list(
    message: Message,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """List all metrics with activity status (FR-8)."""
    items = await list_metrics_with_activity(session, user.id)

    if not items:
        await message.answer(
            "You have no metrics yet.\n\n"
            "Use /metric_create to define one, or just send a message like "
            "<b>weight 80</b> and I'll guide you through it."
        )
        return

    lines = ["<b>Your metrics:</b>\n"]
    for item in items:
        m = item.metric
        status_icon = "✅" if m.status == MetricStatus.Active else "📦"
        unit_str = f" [{m.unit}]" if m.unit else ""
        activity = f"{item.activity_label} ({item.periods_filled}/5 periods)"
        lines.append(
            f"{status_icon} <b>{m.name}</b>{unit_str} — {m.periodicity.value} — {activity}\n"
            f"   ID: <code>{m.id}</code>"
        )

    await message.answer("\n".join(lines))


@router.message(Command("metric_archive"))
async def cmd_metric_archive(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """Archive a metric (FR-9)."""
    name = (command.args or "").strip()
    if not name:
        await message.answer("Usage: /metric_archive <b>&lt;metric name&gt;</b>")
        return

    metric, error = await archive_metric(session, user.id, name)
    if error:
        await message.answer(error)
        return

    await session.commit()
    await message.answer(
        f"📦 Metric <b>{metric.name}</b> has been archived.\n"
        "Alert evaluation is suspended. Entries can still be added.\n"
        "Use /metric_reactivate to restore it."
    )


@router.message(Command("metric_reactivate"))
async def cmd_metric_reactivate(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """Reactivate an archived metric (FR-9)."""
    name = (command.args or "").strip()
    if not name:
        await message.answer("Usage: /metric_reactivate <b>&lt;metric name&gt;</b>")
        return

    metric, error = await reactivate_metric(session, user.id, name)
    if error:
        await message.answer(error)
        return

    await session.commit()
    await message.answer(
        f"✅ Metric <b>{metric.name}</b> has been reactivated.\n"
        "Alert evaluation resumes."
    )


@router.message(Command("metric_delete"))
async def cmd_metric_delete(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Initiate metric deletion — requires confirmation (FR-10)."""
    if conv_state.state != ConversationStateEnum.Idle:
        await message.answer(
            "You have a pending action. Please resolve it first, or send /cancel."
        )
        return

    name = (command.args or "").strip()
    if not name:
        await message.answer("Usage: /metric_delete <b>&lt;metric name&gt;</b>")
        return

    metric = await get_metric_by_name(session, user.id, name)
    if metric is None:
        await message.answer(
            f"No metric named '<b>{name}</b>' found. "
            "Use /metric_list to see your metrics."
        )
        return

    # Enter confirmation state
    conv_state.state = ConversationStateEnum.PendingMetricDeletionConfirmation
    conv_state.state_data = {
        "pending_delete_metric_id": str(metric.id),
        "pending_delete_metric_name": metric.name,
    }
    await session.commit()

    await message.answer(
        f"⚠️ Are you sure you want to permanently delete metric <b>{metric.name}</b>?\n\n"
        "This will delete:\n"
        "• All entries\n"
        "• All alerts\n"
        "• All parse attempts\n\n"
        "This action <b>cannot be undone</b>.\n\n"
        "Reply <b>yes</b> to confirm, or anything else (or /cancel) to abort."
    )


async def handle_metric_deletion_confirmation(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
) -> str:
    """
    Process user confirmation for metric deletion (FR-10).
    Called from message.py handle_text when state = PendingMetricDeletionConfirmation.
    """
    import uuid
    state_data: dict = conv_state.state_data or {}
    metric_id_str: str | None = state_data.get("pending_delete_metric_id")
    metric_name: str = state_data.get("pending_delete_metric_name", "")

    def _cancel(reason: str) -> str:
        return reason

    async def _reset_state() -> None:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()

    if not metric_id_str:
        await _reset_state()
        return "Something went wrong. Deletion cancelled."

    try:
        metric_id = uuid.UUID(metric_id_str)
    except ValueError:
        await _reset_state()
        return "Something went wrong. Deletion cancelled."

    key = text.strip().lower()

    if key not in ("yes", "confirm", "y", "да"):
        await _reset_state()
        return f"Deletion of <b>{metric_name}</b> cancelled."

    # Perform cascade deletion
    success, error = await delete_metric_cascade(session, user.id, metric_id)

    if not success:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return f"Could not delete metric: {error}"

    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()

    from checkpoint_recorder.components import observability
    await observability.emit(
        session,
        "metric_lifecycle_event",
        {
            "event": "metric_deleted_cascade",
            "metric_id": str(metric_id),
            "user_id": str(user.id),
        },
    )
    await session.commit()

    return f"🗑️ Metric <b>{metric_name}</b> and all associated data have been permanently deleted."
