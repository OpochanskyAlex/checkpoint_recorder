"""
Aggregates all routers into a single top-level router.
Individual routers added here as each stage is implemented.
"""
from aiogram import Router

router = Router(name="root")

# Stage 1b will register:
#   from checkpoint_recorder.handlers.registration import registration_router
#   from checkpoint_recorder.handlers.entry import entry_router
#   from checkpoint_recorder.handlers.metric import metric_router
#   router.include_router(registration_router)
#   router.include_router(entry_router)
#   router.include_router(metric_router)
