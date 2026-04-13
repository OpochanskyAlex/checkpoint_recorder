"""
Metric Manager — metric creation, lookup, listing, archival, and deletion.

FR-7: Explicit metric creation.
FR-8: Metric listing with MetricActivityStatus (computed on read, AD-4).
FR-9: Archival and Reactivation.
FR-10: Cascade deletion.
"""
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.db.models import (
    Alert,
    Entry,
    InternalUser,
    Metric,
    MetricStatus,
    ParseAttempt,
    Periodicity,
)

log = structlog.get_logger()


async def get_user_metric_names(session: AsyncSession, user_id) -> list[str]:
    """Return names of all Active and Archived metrics for a user (for NLP matching)."""
    rows = await session.execute(
        select(Metric.name).where(
            Metric.internal_user_id == user_id,
            Metric.status.in_([MetricStatus.Active, MetricStatus.Archived]),
        )
    )
    return [r[0] for r in rows.all()]


async def get_metric_by_name(
    session: AsyncSession, user_id, name: str
) -> Metric | None:
    """Exact-match lookup (case-insensitive). Returns None if not found."""
    row = await session.execute(
        select(Metric).where(
            Metric.internal_user_id == user_id,
            Metric.name == name.lower(),
            Metric.status.in_([MetricStatus.Active, MetricStatus.Archived]),
        )
    )
    return row.scalar_one_or_none()


async def create_metric(
    session: AsyncSession,
    user: InternalUser,
    name: str,
    periodicity: Periodicity,
    unit: str | None = None,
    dimension_names: list[str] | None = None,
) -> tuple[Metric | None, str]:
    """
    Create a Metric.  Returns (metric, error_message).
    error_message is empty on success.

    Validation mirrors FR-7 rules.
    Uniqueness is enforced at the DB layer (AD-11) — IntegrityError = duplicate.
    """
    name = name.strip().lower()

    # Validate name
    if not name:
        return None, "Metric name cannot be empty."
    if len(name) > 100:
        return None, "Metric name must be 100 characters or fewer."

    # Validate periodicity
    if periodicity not in (Periodicity.daily, Periodicity.weekly):
        return None, "Periodicity must be 'daily' or 'weekly'."

    # Validate unit
    if unit is not None:
        unit = unit.strip()
        if not unit or len(unit) > 50:
            return None, "Unit must be between 1 and 50 characters."

    # Validate dimension_names
    if dimension_names is not None:
        if len(dimension_names) < 2:
            # Degenerate compound (FR-7): treat as single-value metric
            dimension_names = None
        else:
            for d in dimension_names:
                if not d or len(d.strip()) > 50:
                    return None, "Each dimension name must be 1–50 characters."
            if len(dimension_names) != len(set(d.strip() for d in dimension_names)):
                return None, "Dimension names must be unique within the metric."
            dimension_names = [d.strip() for d in dimension_names]

    metric = Metric(
        internal_user_id=user.id,
        name=name,
        periodicity=periodicity,
        unit=unit,
        dimension_names=dimension_names,
        status=MetricStatus.Active,
    )

    try:
        session.add(metric)
        await session.flush()
    except IntegrityError:
        await session.rollback()
        return None, f"You already have a metric named '{name}'. Use /metric_list to view your metrics."

    return metric, ""


async def get_metric_by_id(
    session: AsyncSession, user_id, metric_id: uuid.UUID
) -> Metric | None:
    """Fetch a metric by UUID, scoped to user."""
    row = await session.execute(
        select(Metric).where(
            Metric.id == metric_id,
            Metric.internal_user_id == user_id,
        )
    )
    return row.scalar_one_or_none()


@dataclass
class MetricWithActivity:
    metric: Metric
    periods_filled: int
    activity_label: str  # "Active" or "Inactive"


async def _compute_periods_filled(
    session: AsyncSession, metric_id: uuid.UUID, periodicity: Periodicity
) -> int:
    """Count distinct periods with ≥1 entry in last 5 periods (FR-8)."""
    now = datetime.now(timezone.utc)

    if periodicity == Periodicity.daily:
        cutoff = now - timedelta(days=5)
        rows = await session.execute(
            select(func.date(Entry.entry_timestamp))
            .where(
                Entry.metric_id == metric_id,
                Entry.entry_timestamp >= cutoff,
            )
            .distinct()
        )
    else:  # weekly
        cutoff = now - timedelta(weeks=5)
        rows = await session.execute(
            select(
                func.extract("year", Entry.entry_timestamp).label("yr"),
                func.extract("week", Entry.entry_timestamp).label("wk"),
            )
            .where(
                Entry.metric_id == metric_id,
                Entry.entry_timestamp >= cutoff,
            )
            .distinct()
        )
    return len(rows.all())


async def list_metrics_with_activity(
    session: AsyncSession, user_id
) -> list[MetricWithActivity]:
    """Return all Active/Archived metrics with computed MetricActivityStatus (FR-8)."""
    rows = await session.execute(
        select(Metric).where(
            Metric.internal_user_id == user_id,
            Metric.status.in_([MetricStatus.Active, MetricStatus.Archived]),
        ).order_by(Metric.name)
    )
    metrics = list(rows.scalars().all())

    result = []
    for m in metrics:
        periods_filled = await _compute_periods_filled(session, m.id, m.periodicity)
        activity_label = "Active" if periods_filled >= 4 else "Inactive"
        result.append(MetricWithActivity(m, periods_filled, activity_label))
    return result


async def archive_metric(
    session: AsyncSession, user_id, name: str
) -> tuple[Metric | None, str]:
    """Set metric status to Archived (FR-9). Returns (metric, error)."""
    metric = await get_metric_by_name(session, user_id, name)
    if metric is None:
        return None, f"No metric named '{name}' found."
    if metric.status == MetricStatus.Archived:
        return metric, f"Metric '{name}' is already archived."
    if metric.status == MetricStatus.Deleted:
        return None, f"Metric '{name}' has been deleted."
    metric.status = MetricStatus.Archived
    await session.flush()
    return metric, ""


async def reactivate_metric(
    session: AsyncSession, user_id, name: str
) -> tuple[Metric | None, str]:
    """Set metric status back to Active (FR-9). Returns (metric, error)."""
    row = await session.execute(
        select(Metric).where(
            Metric.internal_user_id == user_id,
            Metric.name == name.strip().lower(),
            Metric.status == MetricStatus.Archived,
        )
    )
    metric: Metric | None = row.scalar_one_or_none()
    if metric is None:
        # Check if it exists at all
        existing = await get_metric_by_name(session, user_id, name)
        if existing is None:
            return None, f"No metric named '{name}' found."
        return existing, f"Metric '{name}' is already active."
    metric.status = MetricStatus.Active
    await session.flush()
    return metric, ""


async def delete_metric_cascade(
    session: AsyncSession, user_id, metric_id: uuid.UUID
) -> tuple[bool, str]:
    """
    Atomically delete a metric and all associated data (FR-10, AC-FR10-2).

    SQLAlchemy CASCADE on the FK handles Entries, Alerts, ParseAttempts.
    All within one transaction (caller must commit).
    Returns (success, error_message).
    """
    metric = await get_metric_by_id(session, user_id, metric_id)
    if metric is None:
        return False, "Metric not found."
    if metric.status == MetricStatus.Deleted:
        return False, "Metric has already been deleted."

    # Explicit cascade deletes (DB-level CASCADE handles the rest, but we delete
    # explicitly here to guarantee raw_input purge is confirmed at app level)
    await session.execute(
        delete(Entry).where(Entry.metric_id == metric_id)
    )
    await session.execute(
        delete(Alert).where(Alert.metric_id == metric_id)
    )
    await session.execute(
        delete(ParseAttempt).where(ParseAttempt.resolved_metric_id == metric_id)
    )
    await session.delete(metric)
    await session.flush()
    return True, ""
