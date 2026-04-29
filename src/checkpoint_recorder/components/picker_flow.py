"""
Picker flow helpers — post-selection logic for the smart-metric-picker.

Covers:
  - Building the last-3-values context message (FR26)
  - Handling PendingPickerValue (user sends numeric value after metric selection)
  - Transitioning to PendingPeriodicity via Create button (FR27)
"""
from datetime import datetime, timezone

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.components.metric_manager import get_last_entries
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    Entry,
    InternalUser,
    Metric,
)

log = structlog.get_logger()


def format_last_values(metric: Metric, entries: list[Entry]) -> str:
    """Build the last-N-values context block shown after metric selection (FR26)."""
    if not entries:
        context = "No entries yet."
    else:
        lines = []
        for e in entries:
            ts = e.entry_timestamp.strftime("%b %d")
            unit = f" {metric.unit}" if metric.unit else ""
            val = e.value if e.value is not None else "—"
            lines.append(f"  • {ts}: <b>{val}{unit}</b>")
        context = "\n".join(lines)
    return f"<b>{metric.name}</b> — last {len(entries)} value(s):\n{context}"


async def handle_picker_value(
    session: AsyncSession,
    user: InternalUser,
    conv_state: ConversationState,
    text: str,
) -> str:
    """
    Handle a free-text message while in PendingPickerValue state.
    Expects a numeric value; creates Entry on success.
    Returns reply text; caller is responsible for sending it.
    """
    state_data: dict = conv_state.state_data or {}
    metric_id_str: str | None = state_data.get("metric_id")
    metric_name: str = state_data.get("metric_name", "metric")
    original_ts_str: str | None = state_data.get("original_timestamp")

    if not metric_id_str:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Something went wrong. Please re-issue your command."

    # Parse the value
    try:
        value = float(text.strip().replace(",", "."))
    except ValueError:
        return (
            f"Please enter a numeric value for <b>{metric_name}</b>.\n"
            "Or use /cancel to abort."
        )

    import uuid
    from sqlalchemy import select
    from checkpoint_recorder.db.models import Metric as MetricModel

    metric_id = uuid.UUID(metric_id_str)
    metric_row = await session.execute(
        select(MetricModel).where(
            MetricModel.id == metric_id,
            MetricModel.internal_user_id == user.id,
        )
    )
    metric = metric_row.scalar_one_or_none()
    if metric is None:
        conv_state.state = ConversationStateEnum.Idle
        conv_state.state_data = None
        await session.commit()
        return "Metric no longer found. Please re-issue your command."

    entry_timestamp = (
        datetime.fromisoformat(original_ts_str)
        if original_ts_str
        else datetime.now(timezone.utc)
    )

    entry = Entry(
        metric_id=metric.id,
        internal_user_id=user.id,
        value=value,
        raw_input=text,
        entry_timestamp=entry_timestamp,
    )
    session.add(entry)

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
            "via": "picker",
        },
    )
    await session.commit()

    unit_str = f" {metric.unit}" if metric.unit else ""
    return f"✓ Logged <b>{value}{unit_str}</b> for <b>{metric.name}</b>"
