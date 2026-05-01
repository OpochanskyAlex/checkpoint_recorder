"""
ORM models.  All queries must filter by internal_user_id (NFR-7).
Entry rows are immutable — no UPDATE ever issued against the entries table (NFR-6).
"""
import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from checkpoint_recorder.db.engine import Base


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class AccountStatus(str, enum.Enum):
    Active = "Active"
    PendingDeletion = "PendingDeletion"
    Deleted = "Deleted"


class Periodicity(str, enum.Enum):
    daily = "daily"
    weekly = "weekly"


class MetricStatus(str, enum.Enum):
    Active = "Active"
    Archived = "Archived"
    Deleted = "Deleted"


class ConversationStateEnum(str, enum.Enum):
    Idle = "Idle"
    PendingPeriodicity = "PendingPeriodicity"
    PendingDisambiguation = "PendingDisambiguation"
    PendingMetricDeletionConfirmation = "PendingMetricDeletionConfirmation"
    PendingRestorationConfirmation = "PendingRestorationConfirmation"
    PendingMetricPicker = "PendingMetricPicker"
    PendingPickerValue = "PendingPickerValue"


class AlertCondition(str, enum.Enum):
    above = "above"
    below = "below"


class AlertStatus(str, enum.Enum):
    Active = "Active"
    Triggered = "Triggered"


class ParseAttemptStatus(str, enum.Enum):
    Pending = "Pending"
    Resolved = "Resolved"
    Deferred = "Deferred"
    Expired = "Expired"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class InternalUser(Base):
    __tablename__ = "internal_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    telegram_user_id: Mapped[int] = mapped_column(
        BigInteger, unique=True, nullable=False, index=True
    )
    account_status: Mapped[AccountStatus] = mapped_column(
        Enum(AccountStatus, name="account_status_enum"), nullable=False, default=AccountStatus.Active
    )
    registration_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_interaction_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    deletion_scheduled_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    metrics: Mapped[list["Metric"]] = relationship(back_populates="user", lazy="raise")
    conversation_state: Mapped["ConversationState | None"] = relationship(
        back_populates="user", uselist=False, lazy="raise"
    )


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (
        # AD-11: uniqueness enforced at DB layer, not application layer
        UniqueConstraint("internal_user_id", "name", name="uq_metric_user_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    internal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    periodicity: Mapped[Periodicity] = mapped_column(
        Enum(Periodicity, name="periodicity_enum"), nullable=False
    )
    unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    dimension_names: Mapped[list[str] | None] = mapped_column(
        ARRAY(String(50)), nullable=True
    )
    status: Mapped[MetricStatus] = mapped_column(
        Enum(MetricStatus, name="metric_status_enum"), nullable=False, default=MetricStatus.Active
    )
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["InternalUser"] = relationship(back_populates="metrics", lazy="raise")
    entries: Mapped[list["Entry"]] = relationship(back_populates="metric", lazy="raise")
    alerts: Mapped[list["Alert"]] = relationship(back_populates="metric", lazy="raise")


class Entry(Base):
    """
    Immutable after INSERT.  Application code must never issue UPDATE against this table (NFR-6).
    """
    __tablename__ = "entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Redundant FK to enforce isolation queries without a join (NFR-7)
    internal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    value: Mapped[float | None] = mapped_column(Numeric, nullable=True)
    dimension_assignments: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # raw_input stored verbatim; never emitted to observability (NFR-9)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    entry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stored_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    metric: Mapped["Metric"] = relationship(back_populates="entries", lazy="raise")


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    metric_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False, index=True
    )
    internal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    condition: Mapped[AlertCondition] = mapped_column(
        Enum(AlertCondition, name="alert_condition_enum"), nullable=False
    )
    threshold_value: Mapped[float] = mapped_column(Numeric, nullable=False)
    target_dimension: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[AlertStatus] = mapped_column(
        Enum(AlertStatus, name="alert_status_enum"), nullable=False, default=AlertStatus.Active
    )
    last_triggered_timestamp: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    metric: Mapped["Metric"] = relationship(back_populates="alerts", lazy="raise")


class ParseAttempt(Base):
    __tablename__ = "parse_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    internal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # raw_input never emitted to observability (NFR-9)
    raw_input: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_metrics: Mapped[list[Any]] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[ParseAttemptStatus] = mapped_column(
        Enum(ParseAttemptStatus, name="parse_attempt_status_enum"),
        nullable=False,
        default=ParseAttemptStatus.Pending,
    )
    expiry_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    resolved_metric_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("metrics.id", ondelete="SET NULL"), nullable=True
    )


class ConversationState(Base):
    """
    One row per user.  At most one non-Idle state at any time (enforced in User Session Guard).
    Survives process restarts (FR-3, AC-FR3-2).
    """
    __tablename__ = "conversation_states"

    internal_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("internal_users.id", ondelete="CASCADE"), primary_key=True
    )
    state: Mapped[ConversationStateEnum] = mapped_column(
        Enum(ConversationStateEnum, name="conversation_state_enum"),
        nullable=False,
        default=ConversationStateEnum.Idle,
    )
    # Stores flow-specific context: e.g. {"pending_metric_name": "weight"}
    state_data: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    updated_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    user: Mapped["InternalUser"] = relationship(back_populates="conversation_state", lazy="raise")


class ObservabilityEvent(Base):
    """
    Structured event store for business success metrics.
    Schema validation: raw_input must never appear in payload (NFR-9).
    """
    __tablename__ = "observability_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    # payload: IDs and outcome flags only — never free-text user content
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    emitted_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class SchedulerLock(Base):
    """
    Singleton row (id=1) used as a run-lock for the Scheduled Process.
    Atomic check-and-set prevents concurrent scheduler invocations.
    """
    __tablename__ = "scheduler_lock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    locked_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
