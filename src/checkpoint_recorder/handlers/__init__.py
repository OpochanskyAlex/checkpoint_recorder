from aiogram import Router

from checkpoint_recorder.handlers.metric import router as metric_router
from checkpoint_recorder.handlers.metric_management import router as metric_management_router
from checkpoint_recorder.handlers.deferred import router as deferred_router
from checkpoint_recorder.handlers.alert import router as alert_router
from checkpoint_recorder.handlers.account import router as account_router
from checkpoint_recorder.handlers.message import router as message_router

router = Router(name="root")
# Command routers first so slash commands are matched before the catch-all text handler
router.include_router(metric_router)
router.include_router(metric_management_router)
router.include_router(deferred_router)
router.include_router(alert_router)
router.include_router(account_router)
router.include_router(message_router)
