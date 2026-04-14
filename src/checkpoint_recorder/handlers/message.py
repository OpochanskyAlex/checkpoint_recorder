"""
General message handler — data entry, state routing, onboarding (FR-3, FR-4, FR-6).
"""
import structlog
from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components.account_manager import ONBOARDING_MESSAGE
from checkpoint_recorder.components.entry_processor import (
    handle_periodicity_response,
    process_entry,
)
from checkpoint_recorder.components.parse_attempt_manager import (
    handle_disambiguation_response,
)
from checkpoint_recorder.handlers.metric_management import (
    handle_metric_deletion_confirmation,
)
from checkpoint_recorder.db.models import ConversationState, ConversationStateEnum, InternalUser

log = structlog.get_logger()
router = Router(name="message")


@router.message(Command("start"))
async def cmd_start(
    message: Message,
    user: InternalUser,
    conv_state: ConversationState,
    is_new_user: bool,
    session: AsyncSession,
) -> None:
    """/start — show onboarding for new users, help text for returning ones."""
    if is_new_user:
        await message.answer(ONBOARDING_MESSAGE)
    else:
        await message.answer(
            "You're already registered!\n\n"
            "Send me a message like <b>weight 80</b> to log an entry, "
            "or use /metric_create to define a new metric."
        )


@router.message(Command("cancel"))
async def cmd_cancel(
    message: Message,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Cancel any pending conversation state and return to Idle."""
    if conv_state.state == ConversationStateEnum.Idle:
        await message.answer("Nothing to cancel.")
        return

    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None
    await session.commit()
    await message.answer("Cancelled. You're back to the main menu.")


@router.message(F.text)
async def handle_text(
    message: Message,
    user: InternalUser,
    conv_state: ConversationState,
    is_new_user: bool,
    session: AsyncSession,
) -> None:
    """
    Main text handler.  Routes based on ConversationState (FR-3).
    Sends onboarding first if this is the user's first message.
    """
    # Send onboarding for new users before processing the message (FR-1 rule 4&5)
    if is_new_user:
        try:
            await message.answer(ONBOARDING_MESSAGE)
        except Exception:
            log.exception("onboarding_dispatch_failed", user_id=str(user.id))
            await message.answer(
                "Registration succeeded but the onboarding message could not be sent. "
                "Please send your message again."
            )
            return

    state = conv_state.state

    # FR-3: route by conversation state
    if state == ConversationStateEnum.PendingPeriodicity:
        reply = await handle_periodicity_response(session, user, conv_state, message.text)
        await message.answer(reply)

    elif state == ConversationStateEnum.PendingDisambiguation:
        reply = await handle_disambiguation_response(
            session, user, conv_state, message.text, message.date
        )
        await message.answer(reply)

    elif state == ConversationStateEnum.PendingMetricDeletionConfirmation:
        reply = await handle_metric_deletion_confirmation(
            session, user, conv_state, message.text
        )
        await message.answer(reply)

    elif state == ConversationStateEnum.PendingRestorationConfirmation:
        # Stage 3 — not yet implemented
        await message.answer(
            "Your account is pending deletion. Restoration support coming soon."
        )

    else:
        # Idle — attempt data entry (FR-4)
        reply, stored = await process_entry(
            session, user, conv_state, message.text, message.date
        )
        # AC-2 (FR-5 / NFR-17): if process_entry created a ParseAttempt
        # (state is now PendingDisambiguation), wrap the prompt dispatch so
        # we can compensate atomically on failure — no dangling Pending PAs.
        if conv_state.state == ConversationStateEnum.PendingDisambiguation:
            try:
                await message.answer(reply)
            except Exception:
                log.exception("disambiguation_prompt_dispatch_failed", user_id=str(user.id))
                import uuid as _uuid
                from sqlalchemy import delete as _delete
                from checkpoint_recorder.db.models import ParseAttempt
                from checkpoint_recorder.components import observability
                state_data = conv_state.state_data or {}
                pa_id_str = state_data.get("parse_attempt_id")
                if pa_id_str:
                    try:
                        pa_id = _uuid.UUID(pa_id_str)
                        await session.execute(
                            _delete(ParseAttempt).where(ParseAttempt.id == pa_id)
                        )
                    except Exception:
                        log.exception("parse_attempt_compensation_failed", user_id=str(user.id))
                        await observability.emit(
                            session,
                            "dangling_parse_attempt_alert",
                            {"user_id": str(user.id), "parse_attempt_id": pa_id_str},
                        )
                conv_state.state = ConversationStateEnum.Idle
                conv_state.state_data = None
                await session.commit()
        else:
            await message.answer(reply)
