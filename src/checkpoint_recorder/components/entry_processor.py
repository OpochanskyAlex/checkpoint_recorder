"""
Entry Processor — data entry flow (FR-4) and metric auto-creation (FR-6).

Transaction boundaries (per spec):
 - Entry is committed before confirmation is sent.
 - If confirmation dispatch fails, the entry is preserved (not rolled back).
 - Metric is NOT written until periodicity is confirmed (AC-FR6-1).
 - Metric + Entry creation is atomic in a single commit (AC-FR6-2).
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import nlp_engine, observability
from checkpoint_recorder.components.metric_manager import (
    create_metric,
    get_metric_by_name,
    get_user_metric_names,
)
from checkpoint_recorder.components.parse_attempt_manager import (
    build_disambiguation_prompt,
    create_parse_attempt,
)
from checkpoint_recorder.config import settings
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    Entry,
    InternalUser,
    Periodicity,
)

log = structlog.get_logger()

_PERIODICITY_PROMPT = (
    "New metric detected: <b>{name}</b>\n\n"
    "How often do you track this?\n"
    "Reply with <b>daily</b> or <b>weekly</b>"
)

_PERIODICITY_VALUES = {
    "daily": Periodicity.daily,
    "weekly": Periodicity.weekly,
    "d": Periodicity.daily,
    "w": Periodicity.weekly,
}


async def process_entry(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
    message_date: datetime,
    bot=None,
) -> tuple[str, bool]:
    """
    Parse and store a data entry for an Idle user.
    Returns (reply_text, entry_stored).
    """
    known_names = await get_user_metric_names(session, user.id)

    result = nlp_engine.parse(text, known_names, settings.nlp_confidence_threshold)

    if result.outcome == "unrecognized":
        await observability.emit(
            session,
            "parse_outcome_event",
            {
                "outcome": "unrecognized",
                "user_id": str(user.id),
            },
        )
        return (
            "I couldn't identify a metric and value in your message.\n"
            "Try something like: <b>weight 80</b> or <b>ran 5</b>",
            False,
        )

    if result.outcome == "ambiguous":
        # Create ParseAttempt + enter PendingDisambiguation state (FR-5)
        pa, error = await create_parse_attempt(
            session, user, text, result.candidate_metrics
        )
        if error:
            return error, False

        conv_state.state = ConversationStateEnum.PendingDisambiguation
        conv_state.state_data = {
            "parse_attempt_id": str(pa.id),
            "candidates": result.candidate_metrics,
        }
        await session.commit()

        await observability.emit(
            session,
            "parse_outcome_event",
            {
                "outcome": "ambiguous",
                "parse_attempt_id": str(pa.id),
                "user_id": str(user.id),
            },
        )
        await session.commit()

        prompt = build_disambiguation_prompt(result.candidate_metrics, text)
        return prompt, False

    # Outcome is auto-parse — look up or auto-create the metric
    metric = await get_metric_by_name(session, user.id, result.metric_name)

    if metric is None:
        # New metric — dispatch periodicity prompt, enter PendingPeriodicity (FR-6)
        conv_state.state = ConversationStateEnum.PendingPeriodicity
        conv_state.state_data = {
            "pending_metric_name": result.metric_name,
            "pending_value": result.value,
            "original_timestamp": message_date.isoformat(),
            "raw_input": text,  # stored in state_data only, never in observability
        }
        await session.commit()

        return _PERIODICITY_PROMPT.format(name=result.metric_name), False

    # Existing metric — write Entry atomically (FR-4)
    entry = Entry(
        metric_id=metric.id,
        internal_user_id=user.id,
        value=result.value,
        raw_input=text,
        entry_timestamp=message_date,
    )
    session.add(entry)
    await session.commit()

    await observability.emit(
        session,
        "parse_outcome_event",
        {
            "outcome": "success",
            "entry_id": str(entry.id),
            "metric_id": str(metric.id),
            "user_id": str(user.id),
        },
    )
    await session.commit()

    # Alert evaluation (FR-12) — after Entry is durable; never blocks or rolls back Entry
    if bot is not None:
        from checkpoint_recorder.components.alert_engine import evaluate_alerts
        await evaluate_alerts(session, bot, entry, metric, user)

    unit_str = f" {metric.unit}" if metric.unit else ""
    return f"✓ Logged <b>{result.value}{unit_str}</b> for <b>{metric.name}</b>", True


async def handle_periodicity_response(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
    bot=None,
) -> str:
    """
    Process the user's periodicity selection while in PendingPeriodicity state.
    Atomically creates Metric + Entry on confirmation (AC-FR6-2).
    Returns the reply text.
    """
    key = text.strip().lower()
    periodicity = _PERIODICITY_VALUES.get(key)

    if periodicity is None:
        return (
            "Please reply with <b>daily</b> or <b>weekly</b> to complete the entry.\n"
            "Or send /cancel to abandon this entry."
        )

    state_data: dict = conv_state.state_data or {}
    metric_name: str = state_data.get("pending_metric_name", "")
    value: float | None = state_data.get("pending_value")
    raw_input: str = state_data.get("raw_input", "")
    original_ts_str: str | None = state_data.get("original_timestamp")

    if not metric_name or value is None:
        # Corrupted state — clear and ask user to retry
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Something went wrong with your pending entry. Please send it again."

    original_timestamp = (
        datetime.fromisoformat(original_ts_str)
        if original_ts_str
        else datetime.now(timezone.utc)
    )

    # Atomic: create Metric + Entry in one commit (AC-FR6-2)
    metric, error = await create_metric(session, user, metric_name, periodicity)
    if error:
        # Metric name taken (race condition) — look it up and use it
        from checkpoint_recorder.components.metric_manager import get_metric_by_name
        metric = await get_metric_by_name(session, user.id, metric_name)
        if metric is None:
            conv_state.state = ConversationStateEnum.Idle
            conv_state.state_data = None
            await session.commit()
            return f"Could not create metric: {error}\nPlease try again."

    entry = Entry(
        metric_id=metric.id,
        internal_user_id=user.id,
        value=value,
        raw_input=raw_input,
        entry_timestamp=original_timestamp,
    )
    session.add(entry)

    # Clear conversation state
    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None

    await session.commit()

    await observability.emit(
        session,
        "parse_outcome_event",
        {
            "outcome": "success",
            "entry_id": str(entry.id),
            "metric_id": str(metric.id),
            "user_id": str(user.id),
        },
    )
    await session.commit()

    # Alert evaluation (FR-12) — after Entry is durable; never blocks or rolls back Entry
    if bot is not None:
        from checkpoint_recorder.components.alert_engine import evaluate_alerts
        await evaluate_alerts(session, bot, entry, metric, user)

    unit_str = f" {metric.unit}" if metric.unit else ""
    return (
        f"✓ Created metric <b>{metric.name}</b> ({periodicity.value}) "
        f"and logged <b>{value}{unit_str}</b>"
    )
