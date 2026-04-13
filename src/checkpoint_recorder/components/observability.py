"""
Observability Collector — structured event emission.

Contract (NFR-9): raw_input must NEVER appear in any event payload.
A schema guard enforces this at the emission boundary.
Failure contract: fire-and-forget — emission failure is logged but never
blocks or rolls back the calling flow.
"""
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.db.models import ObservabilityEvent

log = structlog.get_logger()

# Keys that must never appear in any event payload
_FORBIDDEN_KEYS = frozenset({"raw_input", "text", "message_text", "content", "message"})


async def emit(session: AsyncSession, event_type: str, payload: dict) -> None:
    """
    Store a structured event. Silently drops forbidden keys and logs a warning.
    Never raises — caller must not depend on this succeeding.
    """
    forbidden = _FORBIDDEN_KEYS & payload.keys()
    if forbidden:
        log.warning(
            "observability_schema_violation",
            event_type=event_type,
            forbidden_keys=sorted(forbidden),
        )
        payload = {k: v for k, v in payload.items() if k not in _FORBIDDEN_KEYS}

    try:
        session.add(ObservabilityEvent(event_type=event_type, payload=payload))
        await session.flush()
    except Exception:
        log.exception("observability_emit_failed", event_type=event_type)
