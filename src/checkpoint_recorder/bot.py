"""
Bot and Dispatcher factory.
Handlers and middleware are registered here and imported from their modules.
"""
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


def make_bot() -> Bot:
    """Instantiated at startup, not at import time, so the token is never needed during tests."""
    from checkpoint_recorder.config import settings
    return Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


# Dispatcher — ConversationState is managed in DB directly (no FSM storage required)
dp = Dispatcher()


def register_all(dispatcher: Dispatcher) -> None:
    """
    Import and register routers/middleware.
    Called once at startup after DB is ready.
    Imports are deferred to avoid circular imports at module load time.
    """
    from checkpoint_recorder.middleware.session import DbSessionMiddleware
    from checkpoint_recorder.middleware.user_guard import UserSessionGuardMiddleware
    from checkpoint_recorder.handlers import router

    dispatcher.update.outer_middleware(DbSessionMiddleware())
    dispatcher.update.outer_middleware(UserSessionGuardMiddleware())
    dispatcher.include_router(router)
