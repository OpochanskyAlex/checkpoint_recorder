"""
Scheduled Process — FR-18: Data Purge and Retention Enforcement.

Jobs (run every scheduler_interval_hours, default 12h):
  1. Run-lock acquisition (abort on concurrent invocation)
  2. PendingDeletion purge — cascade delete users past their grace period
  3. 1-year retention review — emit event for long-inactive Active users
  4. Stale Deferred ParseAttempt cleanup → Expired
  5. Stale PendingPeriodicity state cleanup → Idle
  6. Stale PendingMetricPicker / PendingPickerValue cleanup → Idle (SU-009)
  7. Emit scheduler_heartbeat on successful completion

All jobs are idempotent (AC-FR18-7).
Cascade deletion per user is atomic; failure skips that user and continues (AD-7).
"""
import logging
from datetime import datetime, timedelta, timezone

import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from checkpoint_recorder.components import observability
from checkpoint_recorder.db.engine import AsyncSessionFactory
from checkpoint_recorder.db.models import (
    AccountStatus,
    Alert,
    ConversationState,
    ConversationStateEnum,
    Entry,
    InternalUser,
    Metric,
    ParseAttempt,
    ParseAttemptStatus,
    SchedulerLock,
)

log = structlog.get_logger()


def make_scheduler(interval_hours: int) -> AsyncIOScheduler:
    """Create and return a configured APScheduler instance (not yet started)."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        run_scheduled_jobs,
        trigger="interval",
        hours=interval_hours,
        id="maintenance",
        replace_existing=True,
        # Also run once shortly after startup so the first heartbeat is immediate
        next_run_time=datetime.now(timezone.utc) + timedelta(minutes=1),
    )
    return scheduler


async def run_scheduled_jobs() -> None:
    """Entry point called by APScheduler on each interval."""
    async with AsyncSessionFactory() as session:
        acquired = await _acquire_lock(session)
        if not acquired:
            return  # overlap detected; event already emitted

        try:
            await _purge_pending_deletion(session)
            await _retention_review(session)
            await _cleanup_stale_parse_attempts(session)
            await _cleanup_stale_periodicity(session)
            await _cleanup_stale_picker_states(session)

            # AC-FR18-1: heartbeat on every successful run
            await observability.emit(session, "scheduler_heartbeat", {"status": "ok"})
            await session.commit()
            log.info("scheduler_run_complete")
        except Exception:
            log.exception("scheduler_run_failed")
        finally:
            await _release_lock(session)


# ---------------------------------------------------------------------------
# Run-lock
# ---------------------------------------------------------------------------

async def _acquire_lock(session: AsyncSession) -> bool:
    """
    Acquire the scheduler run-lock.
    Returns True if lock acquired; False if a non-stale lock exists.
    """
    from checkpoint_recorder.config import settings

    now = datetime.now(timezone.utc)
    stale_threshold = now - timedelta(hours=settings.scheduler_interval_hours * 2)

    # SELECT FOR UPDATE to serialize concurrent scheduler invocations
    row = await session.execute(
        select(SchedulerLock).where(SchedulerLock.id == 1).with_for_update()
    )
    lock: SchedulerLock | None = row.scalar_one_or_none()

    if lock is None:
        lock = SchedulerLock(id=1, locked_at=now, locked_by="scheduler")
        session.add(lock)
        await session.commit()
        return True

    if lock.locked_at is not None and lock.locked_at > stale_threshold:
        # Lock is held and not stale — abort (AC-FR18-2)
        log.warning("scheduler_overlap_detected", locked_at=str(lock.locked_at))
        await observability.emit(
            session,
            "scheduler_overlap_event",
            {"locked_at": lock.locked_at.isoformat(), "locked_by": lock.locked_by or ""},
        )
        await session.commit()
        return False

    # Lock is free or stale — acquire
    lock.locked_at = now
    lock.locked_by = "scheduler"
    await session.commit()
    return True


async def _release_lock(session: AsyncSession) -> None:
    row = await session.execute(
        select(SchedulerLock).where(SchedulerLock.id == 1)
    )
    lock: SchedulerLock | None = row.scalar_one_or_none()
    if lock:
        lock.locked_at = None
        lock.locked_by = None
        try:
            await session.commit()
        except Exception:
            log.exception("scheduler_lock_release_failed")


# ---------------------------------------------------------------------------
# Job 1: PendingDeletion purge
# ---------------------------------------------------------------------------

async def _purge_pending_deletion(session: AsyncSession) -> None:
    """
    Cascade-delete all data for users past their deletion grace period (FR-18 rule 2).
    AC-FR18-5: atomic per user — failure skips that user and continues.
    NFR-14: only purge if deletion_scheduled_timestamp ≤ now().
    NFR-13: never purge Active users.
    """
    now = datetime.now(timezone.utc)

    rows = await session.execute(
        select(InternalUser).where(
            InternalUser.account_status == AccountStatus.PendingDeletion,
            InternalUser.deletion_scheduled_timestamp <= now,
        )
    )
    users = list(rows.scalars().all())

    for user in users:
        try:
            await _cascade_delete_user_data(session, user)
            log.info("user_purged", user_id=str(user.id))
        except Exception:
            log.exception("user_purge_failed", user_id=str(user.id))
            await session.rollback()
            await observability.emit(
                session,
                "user_purge_failure_event",
                {"user_id": str(user.id)},
            )
            await session.commit()


async def _cascade_delete_user_data(session: AsyncSession, user: InternalUser) -> None:
    """
    Atomically delete all data for a user and mark them Deleted.
    AC-FR18-3: no Entry, Alert, ParseAttempt, or raw_input data remains.
    AC-FR18-5: entire operation is in one transaction.
    """
    uid = user.id

    # Delete in dependency order; DB CASCADE handles nested FKs
    await session.execute(delete(ParseAttempt).where(ParseAttempt.internal_user_id == uid))
    await session.execute(delete(Entry).where(Entry.internal_user_id == uid))
    await session.execute(delete(Alert).where(Alert.internal_user_id == uid))
    await session.execute(delete(Metric).where(Metric.internal_user_id == uid))
    await session.execute(
        delete(ConversationState).where(ConversationState.internal_user_id == uid)
    )

    user.account_status = AccountStatus.Deleted
    user.deletion_scheduled_timestamp = None

    await observability.emit(
        session,
        "user_purge_event",
        {"user_id": str(uid)},
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Job 2: 1-year retention review
# ---------------------------------------------------------------------------

async def _retention_review(session: AsyncSession) -> None:
    """
    Emit retention_review_event for Active users inactive for ≥1 year (FR-18 rule 3).
    NFR-13: no auto-deletion — operator action required.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=365)
    rows = await session.execute(
        select(InternalUser).where(
            InternalUser.account_status == AccountStatus.Active,
            InternalUser.last_interaction_timestamp < cutoff,
        )
    )
    users = list(rows.scalars().all())
    for user in users:
        await observability.emit(
            session,
            "retention_review_event",
            {
                "user_id": str(user.id),
                "last_interaction": user.last_interaction_timestamp.isoformat(),
            },
        )
    if users:
        await session.commit()


# ---------------------------------------------------------------------------
# Job 3: Stale Deferred ParseAttempt cleanup
# ---------------------------------------------------------------------------

async def _cleanup_stale_parse_attempts(session: AsyncSession) -> None:
    """
    Transition Deferred ParseAttempts older than SU-006 window to Expired (FR-18 rule 4).
    """
    from checkpoint_recorder.config import settings
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.deferred_cleanup_days)

    result = await session.execute(
        update(ParseAttempt)
        .where(
            ParseAttempt.status == ParseAttemptStatus.Deferred,
            ParseAttempt.created_timestamp < cutoff,
        )
        .values(status=ParseAttemptStatus.Expired)
        .returning(ParseAttempt.id)
    )
    expired_ids = result.scalars().all()

    if expired_ids:
        await observability.emit(
            session,
            "parse_attempt_expiry_event",
            {"expired_count": len(expired_ids)},
        )
        await session.commit()
        log.info("stale_parse_attempts_expired", count=len(expired_ids))


# ---------------------------------------------------------------------------
# Job 4: Stale PendingPeriodicity cleanup
# ---------------------------------------------------------------------------

async def _cleanup_stale_periodicity(session: AsyncSession) -> None:
    """
    Clear ConversationState rows stuck in PendingPeriodicity beyond SU-009 (FR-18 rule 5).
    AC-FR18-4: cleared to Idle.
    """
    from checkpoint_recorder.config import settings
    now = datetime.now(timezone.utc)
    expiry = timedelta(hours=settings.periodicity_prompt_expiry_hours)

    rows = await session.execute(
        select(ConversationState).where(
            ConversationState.state == ConversationStateEnum.PendingPeriodicity
        )
    )
    states = list(rows.scalars().all())

    cleared = 0
    for cs in states:
        # Use original_timestamp from state_data (set when periodicity prompt was dispatched)
        data = cs.state_data or {}
        orig_ts_str = data.get("original_timestamp")
        if orig_ts_str:
            try:
                orig_ts = datetime.fromisoformat(orig_ts_str)
                if orig_ts.tzinfo is None:
                    orig_ts = orig_ts.replace(tzinfo=timezone.utc)
                entered = orig_ts
            except ValueError:
                entered = cs.updated_timestamp
        else:
            entered = cs.updated_timestamp

        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)

        if now - entered > expiry:
            cs.state = ConversationStateEnum.Idle
            cs.state_data = None
            cleared += 1
            await observability.emit(
                session,
                "periodicity_prompt_event",
                {
                    "user_id": str(cs.internal_user_id),
                    "outcome": "abandoned",
                },
            )

    if cleared:
        await session.commit()
        log.info("stale_periodicity_states_cleared", count=cleared)


# Job 6: Stale PendingMetricPicker / PendingPickerValue cleanup
# ---------------------------------------------------------------------------

async def _cleanup_stale_picker_states(session: AsyncSession) -> None:
    """
    Clear ConversationState rows stuck in PendingMetricPicker or PendingPickerValue
    beyond periodicity_prompt_expiry_hours (reuses SU-009, Q-PM-3 Option A).
    Notifies users via conversation_state_event; no Telegram message sent here
    (users receive re-prompt from handle_text on next interaction before scheduler runs).
    """
    from checkpoint_recorder.config import settings
    from checkpoint_recorder.db.models import ConversationStateEnum
    now = datetime.now(timezone.utc)
    expiry = timedelta(hours=settings.periodicity_prompt_expiry_hours)

    rows = await session.execute(
        select(ConversationState).where(
            ConversationState.state.in_([
                ConversationStateEnum.PendingMetricPicker,
                ConversationStateEnum.PendingPickerValue,
            ])
        )
    )
    states = list(rows.scalars().all())

    cleared = 0
    for cs in states:
        entered = cs.updated_timestamp
        if entered.tzinfo is None:
            entered = entered.replace(tzinfo=timezone.utc)
        if now - entered <= expiry:
            continue
        old_state = cs.state.value
        cs.state = ConversationStateEnum.Idle
        cs.state_data = None
        cleared += 1
        await observability.emit(
            session,
            "conversation_state_event",
            {
                "user_id": str(cs.internal_user_id),
                "type": "picker_timeout",
                "previous_state": old_state,
            },
        )

    if cleared:
        await session.commit()
        log.info("stale_picker_states_cleared", count=cleared)
