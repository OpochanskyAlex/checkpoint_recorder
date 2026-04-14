"""
Alert Engine — FR-12: Alert Evaluation (Post-Entry).

Called after each Entry is durably stored.
Contract (EH-6): never raises; never rolls back the triggering Entry.
Emits alert_evaluation_event for every alert evaluated (NFR-11).
"""
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.db.models import (
    Alert,
    AlertStatus,
    Entry,
    InternalUser,
    Metric,
    MetricStatus,
)

log = structlog.get_logger()


async def evaluate_alerts(
    session: AsyncSession,
    bot,
    entry: Entry,
    metric: Metric,
    user: InternalUser,
) -> None:
    """
    Evaluate all Active Alerts for the entry's metric (FR-12).

    Wrapped in a top-level try/except so Entry is never affected by failure.
    """
    try:
        await _run_evaluation(session, bot, entry, metric, user)
    except Exception:
        log.exception(
            "alert_evaluation_unexpected_failure",
            entry_id=str(entry.id),
            user_id=str(user.id),
        )
        await observability.emit(
            session,
            "alert_evaluation_event",
            {
                "entry_id": str(entry.id),
                "metric_id": str(metric.id),
                "user_id": str(user.id),
                "outcome": "evaluation_error",
            },
        )
        try:
            await session.commit()
        except Exception:
            pass


async def _run_evaluation(
    session: AsyncSession,
    bot,
    entry: Entry,
    metric: Metric,
    user: InternalUser,
) -> None:
    # FR-12 rule 2: skip evaluation for Archived metrics
    if metric.status == MetricStatus.Archived:
        return

    rows = await session.execute(
        select(Alert).where(
            Alert.metric_id == metric.id,
            Alert.status == AlertStatus.Active,
        )
    )
    alerts = list(rows.scalars().all())
    if not alerts:
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    for alert in alerts:
        outcome = "not_triggered"
        try:
            # Determine the value to evaluate
            if alert.target_dimension is None:
                compare_value = entry.value
            else:
                assignments = entry.dimension_assignments or {}
                compare_value = assignments.get(alert.target_dimension)
                if compare_value is None:
                    log.warning(
                        "alert_dimension_missing",
                        alert_id=str(alert.id),
                        dimension=alert.target_dimension,
                    )
                    await observability.emit(
                        session,
                        "alert_evaluation_event",
                        {
                            "alert_id": str(alert.id),
                            "entry_id": str(entry.id),
                            "metric_id": str(metric.id),
                            "user_id": str(user.id),
                            "outcome": "dimension_missing",
                        },
                    )
                    await session.commit()
                    continue

            if compare_value is None:
                continue

            threshold = float(alert.threshold_value)
            v = float(compare_value)
            triggered = (
                alert.condition.value == "above" and v > threshold
            ) or (
                alert.condition.value == "below" and v < threshold
            )

            if triggered:
                alert.status = AlertStatus.Triggered
                alert.last_triggered_timestamp = now
                await session.commit()
                outcome = "triggered"

                # Dispatch notification with one retry (EH-7)
                dim_str = f" [{alert.target_dimension}]" if alert.target_dimension else ""
                notification = (
                    f"🔔 Alert triggered for <b>{metric.name}</b>{dim_str}\n"
                    f"Value <b>{v}</b> is {alert.condition.value} threshold <b>{threshold}</b>"
                )
                sent = False
                for attempt in range(2):
                    try:
                        await bot.send_message(
                            chat_id=user.telegram_user_id,
                            text=notification,
                        )
                        sent = True
                        break
                    except Exception:
                        if attempt == 0:
                            log.warning("alert_notification_retry", alert_id=str(alert.id))

                if not sent:
                    log.error("alert_notification_failed", alert_id=str(alert.id))
                    await observability.emit(
                        session,
                        "notification_dispatch_failure_event",
                        {
                            "alert_id": str(alert.id),
                            "user_id": str(user.id),
                        },
                    )
                    await session.commit()

        except Exception:
            log.exception("alert_item_evaluation_failed", alert_id=str(alert.id))
            outcome = "item_error"

        # NFR-11: emit for every evaluated alert
        await observability.emit(
            session,
            "alert_evaluation_event",
            {
                "alert_id": str(alert.id),
                "entry_id": str(entry.id),
                "metric_id": str(metric.id),
                "user_id": str(user.id),
                "outcome": outcome,
            },
        )
        await session.commit()
