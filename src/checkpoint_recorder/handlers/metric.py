"""
Metric command handlers — FR-7: explicit metric creation.

Command format:
  /metric_create <name> <daily|weekly> [unit]
  /metric_create blood_pressure daily mmhg
  /metric_create weight weekly kg
"""
import structlog
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.filters import CommandObject
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components.metric_manager import create_metric
from checkpoint_recorder.components import observability
from checkpoint_recorder.db.models import InternalUser, Periodicity

log = structlog.get_logger()
router = Router(name="metric")

_USAGE = (
    "Usage: /metric_create &lt;name&gt; &lt;daily|weekly&gt; [unit]\n\n"
    "Examples:\n"
    "  /metric_create weight daily kg\n"
    "  /metric_create steps daily\n"
    "  /metric_create blood_pressure weekly mmhg"
)


@router.message(Command("metric_create"))
async def cmd_metric_create(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """Create a metric explicitly (FR-7)."""
    args = (command.args or "").split()

    if len(args) < 2:
        await message.answer(_USAGE)
        return

    name = args[0]
    periodicity_str = args[1].lower()
    unit = args[2] if len(args) >= 3 else None

    if periodicity_str not in ("daily", "weekly"):
        await message.answer(
            f"Invalid periodicity: <b>{periodicity_str}</b>\n"
            "Must be <b>daily</b> or <b>weekly</b>."
        )
        return

    periodicity = Periodicity.daily if periodicity_str == "daily" else Periodicity.weekly

    metric, error = await create_metric(session, user, name, periodicity, unit)

    if error:
        await message.answer(error)
        return

    await session.commit()

    await observability.emit(
        session,
        "metric_lifecycle_event",
        {
            "event": "metric_created",
            "metric_id": str(metric.id),
            "user_id": str(user.id),
            "periodicity": periodicity.value,
        },
    )
    await session.commit()

    unit_str = f" (unit: {metric.unit})" if metric.unit else ""
    await message.answer(
        f"✓ Metric created!\n\n"
        f"<b>Name:</b> {metric.name}\n"
        f"<b>Periodicity:</b> {periodicity.value}{unit_str}\n"
        f"<b>ID:</b> <code>{metric.id}</code>\n\n"
        f"Now send me a message like <b>{metric.name} 80</b> to log an entry."
    )
