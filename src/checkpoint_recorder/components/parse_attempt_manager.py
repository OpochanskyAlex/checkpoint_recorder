"""
ParseAttempt Manager — FR-5: Ambiguous Entry lifecycle, FR-15: Late Categorization.

Atomicity rule (AD-9): if disambiguation prompt dispatch fails after ParseAttempt
creation, the ParseAttempt is deleted. If deletion also fails, a
dangling_parse_attempt_alert is emitted to Observability.
"""
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.config import settings
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    Entry,
    InternalUser,
    Metric,
    MetricStatus,
    ParseAttempt,
    ParseAttemptStatus,
)

log = structlog.get_logger()


async def get_pending_parse_attempt(
    session: AsyncSession, user_id
) -> ParseAttempt | None:
    """Return the single Pending ParseAttempt for this user, or None."""
    row = await session.execute(
        select(ParseAttempt).where(
            ParseAttempt.internal_user_id == user_id,
            ParseAttempt.status == ParseAttemptStatus.Pending,
        )
    )
    return row.scalar_one_or_none()


async def create_parse_attempt(
    session: AsyncSession,
    user: InternalUser,
    raw_input: str,
    candidates: list[str],
) -> tuple[ParseAttempt | None, str]:
    """
    Create a Pending ParseAttempt (FR-5).

    Returns (parse_attempt, error_message). error_message is "" on success.
    AC-FR5-1: At most one Pending ParseAttempt per user.
    """
    existing = await get_pending_parse_attempt(session, user.id)
    if existing is not None:
        return None, "You already have a pending disambiguation. Please resolve it first."

    expiry = datetime.now(timezone.utc) + timedelta(
        hours=settings.parse_attempt_expiry_hours
    )
    pa = ParseAttempt(
        internal_user_id=user.id,
        raw_input=raw_input,
        candidate_metrics=candidates,
        status=ParseAttemptStatus.Pending,
        expiry_timestamp=expiry,
    )
    session.add(pa)
    await session.flush()
    return pa, ""


def build_disambiguation_prompt(candidates: list[str], raw_input: str) -> str:
    """Build a numbered candidate list for the user to choose from."""
    lines = [
        f"I wasn't sure which metric you meant for: <b>{raw_input}</b>\n",
        "Which metric does this belong to?\n",
    ]
    for i, name in enumerate(candidates, start=1):
        lines.append(f"  {i}. {name}")
    lines.append("\nReply with the number, or <b>defer</b> to skip for now.")
    return "\n".join(lines)


async def handle_disambiguation_response(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
    message_date: datetime,
    bot=None,
) -> str:
    """
    Process user's response to a disambiguation prompt (FR-5).
    State data: {"parse_attempt_id": str, "candidates": [str, ...]}
    """
    state_data: dict = conv_state.state_data or {}
    pa_id_str: str | None = state_data.get("parse_attempt_id")
    candidates: list[str] = state_data.get("candidates", [])

    if not pa_id_str:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Something went wrong with your pending disambiguation. Please send your message again."

    # Reload the ParseAttempt to verify it still exists and is Pending
    import uuid
    try:
        pa_id = uuid.UUID(pa_id_str)
    except ValueError:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Something went wrong. Please send your message again."

    row = await session.execute(
        select(ParseAttempt).where(
            ParseAttempt.id == pa_id,
            ParseAttempt.internal_user_id == user.id,
        )
    )
    pa: ParseAttempt | None = row.scalar_one_or_none()

    if pa is None or pa.status != ParseAttemptStatus.Pending:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Your disambiguation has already been resolved or expired. Send your message again."

    # AC-4 (FR-5): if the ParseAttempt is past its expiry window, transition to Deferred
    now = datetime.now(timezone.utc)
    pa_expiry = (
        pa.expiry_timestamp
        if pa.expiry_timestamp.tzinfo is not None
        else pa.expiry_timestamp.replace(tzinfo=timezone.utc)
    )
    if now > pa_expiry:
        pa.status = ParseAttemptStatus.Deferred
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        await observability.emit(
            session,
            "parse_outcome_event",
            {
                "outcome": "deferred",
                "parse_attempt_id": str(pa.id),
                "user_id": str(user.id),
                "reason": "expired",
            },
        )
        await session.commit()
        return (
            "Your disambiguation has expired (24h). "
            "The entry has been deferred — use /deferred_list to categorize it later."
        )

    key = text.strip().lower()

    # Defer path
    if key in ("defer", "d", "skip", "later", "no"):
        pa.status = ParseAttemptStatus.Deferred
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()

        await observability.emit(
            session,
            "parse_outcome_event",
            {
                "outcome": "deferred",
                "parse_attempt_id": str(pa.id),
                "user_id": str(user.id),
            },
        )
        await session.commit()
        return (
            "Entry deferred. You can categorize it later with /deferred_list "
            "and /deferred_categorize."
        )

    # Numeric selection
    try:
        choice = int(key)
    except ValueError:
        return (
            "Please reply with a number to select a metric, "
            "or <b>defer</b> to skip.\n"
            "Send /cancel to abandon this disambiguation."
        )

    if choice < 1 or choice > len(candidates):
        return (
            f"Please choose a number between 1 and {len(candidates)}, "
            "or reply <b>defer</b> to skip."
        )

    metric_name = candidates[choice - 1]

    # Look up the metric
    metric_row = await session.execute(
        select(Metric).where(
            Metric.internal_user_id == user.id,
            Metric.name == metric_name,
            Metric.status.in_([MetricStatus.Active, MetricStatus.Archived]),
        )
    )
    metric: Metric | None = metric_row.scalar_one_or_none()

    if metric is None:
        return (
            f"Metric '{metric_name}' no longer exists. "
            "Please choose another or reply <b>defer</b>."
        )

    # Create Entry atomically with ParseAttempt resolution
    entry = Entry(
        metric_id=metric.id,
        internal_user_id=user.id,
        value=pa_value_from_raw(pa.raw_input),
        raw_input=pa.raw_input,
        entry_timestamp=message_date,
    )
    session.add(entry)

    pa.status = ParseAttemptStatus.Resolved
    pa.resolved_metric_id = metric.id

    conv_state.state = ConversationStateEnum.Idle
    conv_state.state_data = None

    await session.commit()

    await observability.emit(
        session,
        "parse_outcome_event",
        {
            "outcome": "resolved",
            "parse_attempt_id": str(pa.id),
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
    value = pa_value_from_raw(pa.raw_input)
    value_str = str(value) if value is not None else "?"
    return f"✓ Logged <b>{value_str}{unit_str}</b> for <b>{metric.name}</b>"


def pa_value_from_raw(raw_input: str) -> float | None:
    """Extract the first number from raw_input for Entry.value."""
    import re
    m = re.search(r"\b(\d+(?:[.,]\d+)?)\b", raw_input)
    if m:
        return float(m.group(1).replace(",", "."))
    return None


async def list_deferred(
    session: AsyncSession, user_id
) -> list[ParseAttempt]:
    """Return all Deferred ParseAttempts for the user (FR-15)."""
    rows = await session.execute(
        select(ParseAttempt).where(
            ParseAttempt.internal_user_id == user_id,
            ParseAttempt.status == ParseAttemptStatus.Deferred,
        ).order_by(ParseAttempt.created_timestamp.desc())
    )
    return list(rows.scalars().all())


async def categorize_deferred(
    session: AsyncSession,
    user: InternalUser,
    parse_attempt_id: str,
    metric_name: str,
    message_date: datetime,
    bot=None,
) -> tuple[str, bool]:
    """
    Late categorization of a Deferred ParseAttempt (FR-15).
    Returns (reply_text, success).
    """
    import uuid
    try:
        pa_id = uuid.UUID(parse_attempt_id)
    except ValueError:
        return "Invalid parse attempt ID.", False

    row = await session.execute(
        select(ParseAttempt).where(
            ParseAttempt.id == pa_id,
            ParseAttempt.internal_user_id == user.id,
            ParseAttempt.status == ParseAttemptStatus.Deferred,
        )
    )
    pa: ParseAttempt | None = row.scalar_one_or_none()

    if pa is None:
        return "Deferred entry not found or already categorized.", False

    metric_row = await session.execute(
        select(Metric).where(
            Metric.internal_user_id == user.id,
            Metric.name == metric_name.strip().lower(),
            Metric.status == MetricStatus.Active,
        )
    )
    metric: Metric | None = metric_row.scalar_one_or_none()

    if metric is None:
        return f"No active metric named '{metric_name}'. Use /metric_list to see your metrics.", False

    entry = Entry(
        metric_id=metric.id,
        internal_user_id=user.id,
        value=pa_value_from_raw(pa.raw_input),
        raw_input=pa.raw_input,
        entry_timestamp=pa.created_timestamp,
    )
    session.add(entry)

    pa.status = ParseAttemptStatus.Resolved
    pa.resolved_metric_id = metric.id

    await session.commit()

    await observability.emit(
        session,
        "late_categorization_event",
        {
            "parse_attempt_id": str(pa.id),
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
    value = pa_value_from_raw(pa.raw_input)
    value_str = str(value) if value is not None else "?"
    return f"✓ Categorized as <b>{metric.name}</b>: <b>{value_str}{unit_str}</b>", True
