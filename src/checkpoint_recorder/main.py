"""
Entrypoint.  Run with:  python -m checkpoint_recorder

POLLING_MODE=true  → long-polling (local dev, no public URL needed)
POLLING_MODE=false → webhook via aiohttp (Railway / production)
"""
import asyncio
import logging
import sys

import structlog
from aiohttp import web
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

from checkpoint_recorder.config import settings
from checkpoint_recorder.bot import make_bot, dp, register_all
from checkpoint_recorder.db.engine import engine


def configure_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        stream=sys.stderr,
        format="%(message)s",
    )
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


async def run_polling() -> None:
    log = structlog.get_logger()
    bot = make_bot()
    register_all(dp)
    log.info("polling_started")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()
        log.info("polling_stopped")


def build_webhook_app() -> web.Application:
    settings.require_webhook()
    bot = make_bot()
    register_all(dp)

    async def on_startup(app: web.Application) -> None:
        log = structlog.get_logger()
        await bot.set_webhook(
            url=settings.webhook_full_url,
            secret_token=settings.webhook_secret,
            drop_pending_updates=True,
        )
        log.info("webhook_set", url=settings.webhook_full_url)

    async def on_shutdown(app: web.Application) -> None:
        log = structlog.get_logger()
        await bot.delete_webhook()
        await bot.session.close()
        await engine.dispose()
        log.info("shutdown_complete")

    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_shutdown.append(on_shutdown)

    SimpleRequestHandler(
        dispatcher=dp,
        bot=bot,
        secret_token=settings.webhook_secret,
    ).register(app, path=settings.webhook_path)

    setup_application(app, dp, bot=bot)
    return app


def main() -> None:
    configure_logging()

    if settings.polling_mode:
        asyncio.run(run_polling())
    else:
        app = build_webhook_app()
        web.run_app(app, host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
