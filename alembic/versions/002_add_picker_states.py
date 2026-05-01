"""Add PendingMetricPicker and PendingPickerValue to conversation_state_enum

Revision ID: 002
Revises: 001
Create Date: 2026-04-29

Notes:
  ALTER TYPE ... ADD VALUE cannot run inside a transaction block on PostgreSQL.
  We use autocommit_block() as required (RISK-F1 mitigation).
  Downgrade is a no-op: PostgreSQL has no DROP VALUE support; the enum values
  are simply unused after rollback until the migration is re-applied.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE conversation_state_enum "
            "ADD VALUE IF NOT EXISTS 'PendingMetricPicker'"
        )
        op.execute(
            "ALTER TYPE conversation_state_enum "
            "ADD VALUE IF NOT EXISTS 'PendingPickerValue'"
        )


def downgrade() -> None:
    # PostgreSQL does not support removing enum values.
    # After downgrade the values become unused but remain in the type.
    pass
