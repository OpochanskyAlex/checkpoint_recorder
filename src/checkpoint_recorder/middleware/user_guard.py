"""
UserSessionGuardMiddleware — stub for Stage 1a.
Full implementation (account status gate + conversation state loading) comes in Stage 1b.
"""
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject


class UserSessionGuardMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Stage 1b: load InternalUser, check account_status, load ConversationState
        return await handler(event, data)
