"""
Account Manager — user registration and onboarding (FR-1, FR-2).

Registration is idempotent: INSERT ... ON CONFLICT DO NOTHING ensures
exactly one InternalUser record per Telegram user ID even under concurrent
first messages (AC-FR1-1).
"""
import uuid

import structlog
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.db.models import (
    AccountStatus,
    ConversationState,
    ConversationStateEnum,
    InternalUser,
)

log = structlog.get_logger()

ONBOARDING_MESSAGE = (
    "👋 Welcome to Checkpoint Recorder!\n\n"
    "Before we start, a few things to know:\n"
    "• Your data is retained for a minimum of 1 year\n"
    "• Data cannot be exported to external systems\n"
    "• Your raw messages are stored verbatim for processing\n"
    "• Threshold alerts fire once and must be manually re-armed\n\n"
    "To log a metric, just send me a message like:\n"
    "  <b>weight 80</b>  or  <b>ran 5 km</b>\n\n"
    "To create a metric explicitly: /metric_create"
)


async def get_or_create_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> tuple[InternalUser, bool]:
    """
    Return (user, is_new).  Atomic upsert — safe under concurrent first messages.
    Also creates the ConversationState row for new users.
    """
    new_id = uuid.uuid4()

    stmt = (
        pg_insert(InternalUser)
        .values(
            id=new_id,
            telegram_user_id=telegram_user_id,
            account_status=AccountStatus.Active,
        )
        .on_conflict_do_nothing(index_elements=["telegram_user_id"])
    )
    result = await session.execute(stmt)
    is_new = result.rowcount > 0

    # Fetch the definitive record (whether just inserted or pre-existing)
    row = await session.execute(
        select(InternalUser).where(InternalUser.telegram_user_id == telegram_user_id)
    )
    user: InternalUser = row.scalar_one()

    if is_new:
        # Create the conversation state row — one row per user, created at registration
        session.add(
            ConversationState(
                internal_user_id=user.id,
                state=ConversationStateEnum.Idle,
            )
        )
        await session.flush()

    return user, is_new


async def re_register_deleted_user(
    session: AsyncSession,
    telegram_user_id: int,
) -> tuple[InternalUser, bool]:
    """
    A Deleted user who sends a new message is treated as a brand-new registration
    (AC-FR2-3): a new InternalUser with a new internal_user_id is created.
    The old Deleted record is left untouched.

    Note: the unique constraint on telegram_user_id means we can't have two Active
    records for the same Telegram ID. We first mark the old record with a sentinel
    telegram_user_id so the new INSERT can proceed.
    """
    # Invalidate the old Deleted record's telegram_user_id so we can reuse it
    old_row = await session.execute(
        select(InternalUser).where(InternalUser.telegram_user_id == telegram_user_id)
    )
    old_user: InternalUser | None = old_row.scalar_one_or_none()
    if old_user and old_user.account_status == AccountStatus.Deleted:
        # Use a negative sentinel to free the unique slot
        old_user.telegram_user_id = -old_user.telegram_user_id
        await session.flush()

    return await get_or_create_user(session, telegram_user_id)
