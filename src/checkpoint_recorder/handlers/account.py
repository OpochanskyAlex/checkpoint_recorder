"""
Account handlers — FR-16: Account Deletion, FR-17: Account Restoration.

Commands:
  /account_delete           → dispatch confirmation prompt
  /account_delete confirm   → execute deletion (no extra state needed)

Restoration confirmation (FR-17) is handled via handle_restoration_confirmation()
called from message.py when state = PendingRestorationConfirmation.
"""
from datetime import datetime, timedelta, timezone

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.db.models import (
    AccountStatus,
    ConversationState,
    ConversationStateEnum,
    InternalUser,
    ParseAttempt,
    ParseAttemptStatus,
)
from sqlalchemy import update

log = structlog.get_logger()
router = Router(name="account")

_DELETION_GRACE_HOURS = 72


@router.message(Command("account_delete"))
async def cmd_account_delete(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Initiate or confirm account deletion (FR-16).

    /account_delete          → show warning and instructions
    /account_delete confirm  → execute deletion
    """
    arg = (command.args or "").strip().lower()

    if arg != "confirm":
        # Step 1: display warning prompt
        await message.answer(
            "⚠️ <b>Account Deletion</b>\n\n"
            "This will schedule <b>permanent deletion</b> of your account and all "
            "associated data (metrics, entries, alerts, parse attempts) after a "
            "<b>72-hour grace period</b>.\n\n"
            "During the grace period you can restore your account by sending any message.\n\n"
            "To confirm, send:\n"
            "<code>/account_delete confirm</code>\n\n"
            "Or send /cancel to abort."
        )
        return

    # Step 2: execute — transition Pending ParseAttempts to Deferred first (AC-FR16-2)
    await session.execute(
        update(ParseAttempt)
        .where(
            ParseAttempt.internal_user_id == user.id,
            ParseAttempt.status == ParseAttemptStatus.Pending,
        )
        .values(status=ParseAttemptStatus.Deferred)
    )

    user.account_status = AccountStatus.PendingDeletion
    user.deletion_scheduled_timestamp = (
        datetime.now(timezone.utc) + timedelta(hours=_DELETION_GRACE_HOURS)
    )

    # Clear any active conversation state
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None

    await session.commit()

    deadline = user.deletion_scheduled_timestamp.strftime("%Y-%m-%d %H:%M UTC")
    await message.answer(
        "✅ Account scheduled for deletion.\n\n"
        f"All your data will be permanently deleted after <b>{deadline}</b>.\n\n"
        "To restore your account before the deadline, simply send any message."
    )


async def handle_restoration_confirmation(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
) -> str:
    """
    Process the user's response to the restoration prompt (FR-17).
    Called from message.py when state = PendingRestorationConfirmation.
    """
    key = text.strip().lower()

    if key not in ("yes", "confirm", "restore", "y", "да"):
        # Non-confirmation — inform user, reset to Idle so next message re-prompts
        deadline = (
            user.deletion_scheduled_timestamp.strftime("%Y-%m-%d %H:%M UTC")
            if user.deletion_scheduled_timestamp
            else "soon"
        )
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return (
            "Your account remains scheduled for deletion.\n"
            f"Deadline: <b>{deadline}</b>\n\n"
            "To restore it, send any message and reply <b>yes</b> to the prompt."
        )

    # AC-FR17-3: check grace period hasn't expired
    now = datetime.now(timezone.utc)
    if user.deletion_scheduled_timestamp is not None:
        scheduled = (
            user.deletion_scheduled_timestamp
            if user.deletion_scheduled_timestamp.tzinfo is not None
            else user.deletion_scheduled_timestamp.replace(tzinfo=timezone.utc)
        )
        if now >= scheduled:
            conv_state.state = ConversationStateEnum.Idle
            conv_state.state_data = None
            await session.commit()
            return (
                "Your grace period has expired and your account has been permanently deleted.\n"
                "You may register again by sending any message."
            )

    # AC-FR17-1: restore account
    user.account_status = AccountStatus.Active
    user.deletion_scheduled_timestamp = None
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()

    return (
        "✅ Your account has been restored!\n\n"
        "All your data is intact. You can continue logging entries as normal."
    )
