"""
UserSessionGuardMiddleware — FR-1, FR-2, FR-3 (partial).

Per message:
1. Extract Telegram user_id from the update.
2. Look up InternalUser. If not found (or Deleted) → register.
3. Check account_status — block PendingDeletion/Deleted as per spec.
4. Load ConversationState.
5. Inject user, conv_state, is_new_user into handler data.
6. After handler returns: update last_interaction_timestamp.
"""
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable

import structlog
from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, Update
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components.account_manager import (
    get_or_create_user,
    re_register_deleted_user,
)
from checkpoint_recorder.components import observability
from checkpoint_recorder.db.models import (
    AccountStatus,
    ConversationState,
    ConversationStateEnum,
    InternalUser,
)

log = structlog.get_logger()


def _extract_from_user(event: TelegramObject):
    """Return the Telegram User object from any supported update type."""
    if isinstance(event, Update):
        if event.message:
            return event.message.from_user
        if event.callback_query:
            return event.callback_query.from_user
    return None


class UserSessionGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        from_user = _extract_from_user(event)

        if from_user is None or from_user.is_bot:
            # No user context (channel posts, etc.) — pass through
            return await handler(event, data)

        session: AsyncSession = data["session"]
        telegram_user_id: int = from_user.id

        # 1. Fetch existing user
        row = await session.execute(
            select(InternalUser).where(
                InternalUser.telegram_user_id == telegram_user_id
            )
        )
        existing: InternalUser | None = row.scalar_one_or_none()

        is_new_user = False

        if existing is None:
            # First contact — register (FR-1)
            user, is_new_user = await get_or_create_user(session, telegram_user_id)
            await session.commit()
            log.info("user_registered", user_id=str(user.id))
            await observability.emit(
                session,
                "registration_event",
                {"user_id": str(user.id), "outcome": "registered"},
            )
            await session.commit()

        elif existing.account_status == AccountStatus.Deleted:
            # Deleted user re-sends — create a fresh record (AC-FR2-3)
            user, is_new_user = await re_register_deleted_user(session, telegram_user_id)
            await session.commit()
            log.info("user_re_registered", user_id=str(user.id))
            await observability.emit(
                session,
                "registration_event",
                {"user_id": str(user.id), "outcome": "re_registered"},
            )
            await session.commit()

        elif existing.account_status == AccountStatus.PendingDeletion:
            # Stage 3 will route to restoration; for now inform user
            if isinstance(event, Update) and event.message:
                await event.message.answer(
                    "Your account is scheduled for deletion.\n"
                    "Account restoration will be available in a future update."
                )
            return None

        else:
            user = existing

        # 2. Load ConversationState (created at registration; should always exist)
        conv_row = await session.execute(
            select(ConversationState).where(
                ConversationState.internal_user_id == user.id
            )
        )
        conv_state: ConversationState | None = conv_row.scalar_one_or_none()

        if conv_state is None:
            # Safety net for users registered before this schema existed
            conv_state = ConversationState(
                internal_user_id=user.id,
                state=ConversationStateEnum.Idle,
            )
            session.add(conv_state)
            await session.flush()

        # 3. Inject into handler data
        data["user"] = user
        data["conv_state"] = conv_state
        data["is_new_user"] = is_new_user

        # 4. Run handler
        result = await handler(event, data)

        # 5. Update last_interaction_timestamp
        try:
            user.last_interaction_timestamp = datetime.now(timezone.utc)
            await session.commit()
        except Exception:
            log.exception("last_interaction_update_failed", user_id=str(user.id))

        return result
