"""
Deferred ParseAttempt handlers — FR-15: Late Categorization.

Commands:
  /deferred_list
  /deferred_categorize <id> <metric_name>
"""
import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components.parse_attempt_manager import (
    categorize_deferred,
    list_deferred,
)
from checkpoint_recorder.db.models import InternalUser

log = structlog.get_logger()
router = Router(name="deferred")


@router.message(Command("deferred_list"))
async def cmd_deferred_list(
    message: Message,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """List all Deferred ParseAttempts (FR-15)."""
    items = await list_deferred(session, user.id)

    if not items:
        await message.answer("You have no deferred entries.")
        return

    lines = ["<b>Deferred entries:</b>\n"]
    for pa in items:
        ts = pa.created_timestamp.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"• <code>{pa.id}</code>\n"
            f"  Input: <i>{pa.raw_input}</i>\n"
            f"  Created: {ts}\n"
        )

    lines.append(
        "\nTo categorize: /deferred_categorize &lt;id&gt; &lt;metric_name&gt;"
    )
    await message.answer("\n".join(lines))


@router.message(Command("deferred_categorize"))
async def cmd_deferred_categorize(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    session: AsyncSession,
) -> None:
    """Categorize a Deferred ParseAttempt as a specific metric (FR-15)."""
    args = (command.args or "").split(maxsplit=1)
    if len(args) < 2:
        await message.answer(
            "Usage: /deferred_categorize <b>&lt;id&gt;</b> <b>&lt;metric name&gt;</b>\n\n"
            "Use /deferred_list to see your deferred entries."
        )
        return

    pa_id, metric_name = args[0], args[1]
    reply, success = await categorize_deferred(
        session, user, pa_id, metric_name, message.date, bot=message.bot
    )
    await message.answer(reply)
