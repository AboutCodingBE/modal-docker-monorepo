"""add CANCELLED status to archive_analysis and analysis_tasks

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-13

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Add CANCELLED to the PostgreSQL enum used by archive_analysis.status
    op.execute("ALTER TYPE archive_analysis_status ADD VALUE IF NOT EXISTS 'CANCELLED'")

    # Update the check constraint on analysis_tasks to allow 'cancelled'
    op.drop_constraint("ck_analysis_tasks_status", "analysis_tasks", type_="check")
    op.create_check_constraint(
        "ck_analysis_tasks_status",
        "analysis_tasks",
        "status IN ('pending', 'running', 'completed', 'failed', 'cancelled')",
    )


def downgrade() -> None:
    # Restore the original check constraint (without 'cancelled')
    op.drop_constraint("ck_analysis_tasks_status", "analysis_tasks", type_="check")
    op.create_check_constraint(
        "ck_analysis_tasks_status",
        "analysis_tasks",
        "status IN ('pending', 'running', 'completed', 'failed')",
    )
    # Note: PostgreSQL does not support removing enum values; CANCELLED remains in the type
