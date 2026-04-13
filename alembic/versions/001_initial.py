"""Initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-13
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Enum type references for use inside op.create_table.
# create_type=False means "this type already exists — don't issue CREATE TYPE".
account_status_t = postgresql.ENUM(name="account_status_enum", create_type=False)
periodicity_t = postgresql.ENUM(name="periodicity_enum", create_type=False)
metric_status_t = postgresql.ENUM(name="metric_status_enum", create_type=False)
alert_condition_t = postgresql.ENUM(name="alert_condition_enum", create_type=False)
alert_status_t = postgresql.ENUM(name="alert_status_enum", create_type=False)
parse_attempt_status_t = postgresql.ENUM(name="parse_attempt_status_enum", create_type=False)
conversation_state_t = postgresql.ENUM(name="conversation_state_enum", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()

    # --- Enums (checkfirst=True: no-op if type already exists) ---
    sa.Enum("Active", "PendingDeletion", "Deleted",
            name="account_status_enum").create(bind, checkfirst=True)
    sa.Enum("daily", "weekly",
            name="periodicity_enum").create(bind, checkfirst=True)
    sa.Enum("Active", "Archived", "Deleted",
            name="metric_status_enum").create(bind, checkfirst=True)
    sa.Enum("above", "below",
            name="alert_condition_enum").create(bind, checkfirst=True)
    sa.Enum("Active", "Triggered",
            name="alert_status_enum").create(bind, checkfirst=True)
    sa.Enum("Pending", "Resolved", "Deferred", "Expired",
            name="parse_attempt_status_enum").create(bind, checkfirst=True)
    sa.Enum("Idle", "PendingPeriodicity", "PendingDisambiguation",
            "PendingMetricDeletionConfirmation", "PendingRestorationConfirmation",
            name="conversation_state_enum").create(bind, checkfirst=True)

    # --- internal_users ---
    op.create_table(
        "internal_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("telegram_user_id", sa.BigInteger, nullable=False),
        sa.Column("account_status", account_status_t, nullable=False, server_default="Active"),
        sa.Column("registration_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_interaction_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deletion_scheduled_timestamp", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_internal_users_telegram_user_id", "internal_users", ["telegram_user_id"], unique=True)

    # --- metrics ---
    op.create_table(
        "metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("internal_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("periodicity", periodicity_t, nullable=False),
        sa.Column("unit", sa.String(50), nullable=True),
        sa.Column("dimension_names", postgresql.ARRAY(sa.String(50)), nullable=True),
        sa.Column("status", metric_status_t, nullable=False, server_default="Active"),
        sa.Column("created_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_metrics_internal_user_id", "metrics", ["internal_user_id"])
    op.create_unique_constraint("uq_metric_user_name", "metrics", ["internal_user_id", "name"])

    # --- entries (immutable — no UPDATE ever issued) ---
    op.create_table(
        "entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("metric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("internal_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("value", sa.Numeric, nullable=True),
        sa.Column("dimension_assignments", postgresql.JSONB, nullable=True),
        sa.Column("raw_input", sa.Text, nullable=False),
        sa.Column("entry_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("stored_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_entries_metric_id", "entries", ["metric_id"])
    op.create_index("ix_entries_internal_user_id", "entries", ["internal_user_id"])

    # --- alerts ---
    op.create_table(
        "alerts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("metric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metrics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("internal_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("condition", alert_condition_t, nullable=False),
        sa.Column("threshold_value", sa.Numeric, nullable=False),
        sa.Column("target_dimension", sa.String(50), nullable=True),
        sa.Column("status", alert_status_t, nullable=False, server_default="Active"),
        sa.Column("last_triggered_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_alerts_metric_id", "alerts", ["metric_id"])
    op.create_index("ix_alerts_internal_user_id", "alerts", ["internal_user_id"])

    # --- parse_attempts ---
    op.create_table(
        "parse_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("internal_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("internal_users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("raw_input", sa.Text, nullable=False),
        sa.Column("candidate_metrics", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", parse_attempt_status_t, nullable=False, server_default="Pending"),
        sa.Column("expiry_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_metric_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("metrics.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_parse_attempts_internal_user_id", "parse_attempts", ["internal_user_id"])

    # --- conversation_states ---
    op.create_table(
        "conversation_states",
        sa.Column("internal_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("internal_users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("state", conversation_state_t, nullable=False, server_default="Idle"),
        sa.Column("state_data", postgresql.JSONB, nullable=True),
        sa.Column("updated_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # --- observability_events ---
    op.create_table(
        "observability_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", postgresql.JSONB, nullable=False),
        sa.Column("emitted_timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_observability_events_event_type", "observability_events", ["event_type"])
    op.create_index("ix_observability_events_emitted_timestamp", "observability_events", ["emitted_timestamp"])

    # --- scheduler_lock (singleton row) ---
    op.create_table(
        "scheduler_lock",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(255), nullable=True),
    )
    op.execute("INSERT INTO scheduler_lock (id) VALUES (1)")


def downgrade() -> None:
    op.drop_table("scheduler_lock")
    op.drop_table("observability_events")
    op.drop_table("conversation_states")
    op.drop_table("parse_attempts")
    op.drop_table("alerts")
    op.drop_table("entries")
    op.drop_table("metrics")
    op.drop_table("internal_users")

    bind = op.get_bind()
    sa.Enum(name="conversation_state_enum").drop(bind, checkfirst=True)
    sa.Enum(name="parse_attempt_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="alert_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="alert_condition_enum").drop(bind, checkfirst=True)
    sa.Enum(name="metric_status_enum").drop(bind, checkfirst=True)
    sa.Enum(name="periodicity_enum").drop(bind, checkfirst=True)
    sa.Enum(name="account_status_enum").drop(bind, checkfirst=True)
