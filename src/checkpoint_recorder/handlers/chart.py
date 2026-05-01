"""
Chart handler — FR-14: Chart Generation and Delivery.

Command:
  /chart <metric_name> [days]

Flow (AD-10):
  1. Validate metric — return error immediately on failure.
  2. Dispatch acknowledgment ≤5s (AC-FR14-1).
  3. Fire background coroutine — chart is rendered and delivered asynchronously.
     Delivery ≤30s from command (AC-FR14-2).
  4. Emit chart_invocation_event and chart_delivery_outcome_event (AC-FR14-3).
"""
import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import structlog
from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import BufferedInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.components.chart_generator import render_chart
from checkpoint_recorder.components.metric_manager import (
    get_metric_by_name,
    get_metrics_ordered_by_recency,
    get_user_metric_names,
)
from checkpoint_recorder.components.picker_keyboard import (
    build_picker_keyboard,
    build_zero_match_message,
)
from checkpoint_recorder.db.engine import AsyncSessionFactory
from checkpoint_recorder.db.models import (
    ConversationState,
    ConversationStateEnum,
    Entry,
    InternalUser,
    MetricStatus,
)

log = structlog.get_logger()
router = Router(name="chart")

_DEFAULT_DAYS = 30


@router.message(Command("chart"))
async def cmd_chart(
    message: Message,
    command: CommandObject,
    user: InternalUser,
    conv_state: ConversationState,
    session: AsyncSession,
) -> None:
    """Generate and deliver a time-series chart for a metric (FR-14)."""
    from checkpoint_recorder.components.nlp_engine import fuzzy_match_metrics
    from checkpoint_recorder.config import settings

    args = (command.args or "").split()
    days = _DEFAULT_DAYS

    if args and len(args) >= 2:
        try:
            days = int(args[1])
            if days < 1 or days > 3650:
                await message.answer("Days must be between 1 and 3650.")
                return
        except ValueError:
            await message.answer("Days must be a whole number.")
            return

    metric_name = args[0] if args else ""

    if not metric_name:
        # Bare /chart — show picker with all metrics (FR22)
        all_metrics = await get_metrics_ordered_by_recency(session, user.id)
        if not all_metrics:
            await message.answer("You have no metrics yet.")
            return
        conv_state.state = ConversationStateEnum.PendingMetricPicker
        conv_state.state_data = {"command_context": "chart", "typed_name": "", "chart_days": days}
        await session.commit()
        await message.answer(
            "Which metric would you like to chart?",
            reply_markup=build_picker_keyboard(all_metrics),
        )
        return

    # Validate metric (AC-FR14-4: Archived is allowed)
    metric = await get_metric_by_name(session, user.id, metric_name)

    if metric is None and settings.fuzzy_match_threshold > 0:
        known_names = await get_user_metric_names(session, user.id)
        fuzzy_names = fuzzy_match_metrics(metric_name, known_names, settings.fuzzy_match_threshold)
        if fuzzy_names:
            all_metrics = await get_metrics_ordered_by_recency(session, user.id)
            matching = [m for m in all_metrics if m.name in set(fuzzy_names)]
            conv_state.state = ConversationStateEnum.PendingMetricPicker
            conv_state.state_data = {"command_context": "chart", "typed_name": metric_name, "chart_days": days}
            await session.commit()
            await message.answer(
                f'No exact match for "<b>{metric_name}</b>". Did you mean:',
                reply_markup=build_picker_keyboard(matching),
            )
            return
        await message.answer(build_zero_match_message("chart"))
        return

    if metric is None:
        await message.answer(
            f"No metric named '<b>{metric_name}</b>' found. "
            "Use /metric_list to see your metrics."
        )
        return

    if metric.status == MetricStatus.Deleted:
        await message.answer(f"Metric '<b>{metric_name}</b>' has been deleted.")
        return

    # Emit chart_invocation_event (AC-FR14-3)
    await observability.emit(
        session,
        "chart_invocation_event",
        {
            "metric_id": str(metric.id),
            "user_id": str(user.id),
            "days": days,
        },
    )
    await session.commit()

    # AC-FR14-1: send acknowledgment immediately (≤5s)
    await message.answer(
        f"⏳ Generating chart for <b>{metric.name}</b> (last {days} days)…"
    )

    # Fire background task — uses its own session (handler session closes after return)
    asyncio.create_task(
        _deliver_chart(
            bot=message.bot,
            chat_id=message.chat.id,
            user_id=user.id,
            metric_id=metric.id,
            metric_name=metric.name,
            unit=metric.unit,
            dimension_names=metric.dimension_names,
            days=days,
        )
    )


async def _deliver_chart(
    bot,
    chat_id: int,
    user_id: uuid.UUID,
    metric_id: uuid.UUID,
    metric_name: str,
    unit: str | None,
    dimension_names: list[str] | None,
    days: int,
) -> None:
    """
    Background coroutine: fetch entries, render chart, deliver via Telegram.
    Opens its own DB session — independent of the handler's session lifecycle.
    """
    outcome = "failure"
    try:
        async with AsyncSessionFactory() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            rows = await session.execute(
                select(Entry)
                .where(
                    Entry.metric_id == metric_id,
                    Entry.internal_user_id == user_id,
                    Entry.entry_timestamp >= cutoff,
                )
                .order_by(Entry.entry_timestamp.asc())
            )
            entries_db = list(rows.scalars().all())

            # AC-FR14-4: no chart for zero entries
            if not entries_db:
                await bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"No entries found for <b>{metric_name}</b> "
                        f"in the last {days} days."
                    ),
                )
                await observability.emit(
                    session,
                    "chart_delivery_outcome_event",
                    {
                        "metric_id": str(metric_id),
                        "user_id": str(user_id),
                        "outcome": "no_entries",
                    },
                )
                await session.commit()
                return

            # Build entry tuples for renderer
            entry_tuples = [
                (e.entry_timestamp, e.value, e.dimension_assignments)
                for e in entries_db
            ]

            # Render chart (CPU-bound but small; run inline for simplicity)
            png_bytes = render_chart(metric_name, unit, dimension_names, entry_tuples)

            # Deliver image (AC-FR14-2: within 30s total)
            photo = BufferedInputFile(png_bytes, filename=f"{metric_name}_chart.png")
            await bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=f"📈 <b>{metric_name}</b> — last {days} days ({len(entries_db)} entries)",
            )
            outcome = "success"

            await observability.emit(
                session,
                "chart_delivery_outcome_event",
                {
                    "metric_id": str(metric_id),
                    "user_id": str(user_id),
                    "outcome": outcome,
                    "entry_count": len(entries_db),
                },
            )
            await session.commit()

    except Exception:
        log.exception(
            "chart_delivery_failed", metric_id=str(metric_id), user_id=str(user_id)
        )
        try:
            await bot.send_message(
                chat_id=chat_id,
                text=f"Sorry, I couldn't generate the chart for <b>{metric_name}</b>. Please try again.",
            )
        except Exception:
            log.exception("chart_error_dispatch_failed", chat_id=chat_id)

        try:
            async with AsyncSessionFactory() as session:
                await observability.emit(
                    session,
                    "chart_delivery_outcome_event",
                    {
                        "metric_id": str(metric_id),
                        "user_id": str(user_id),
                        "outcome": "failure",
                    },
                )
                await session.commit()
        except Exception:
            log.exception("chart_outcome_event_failed")
