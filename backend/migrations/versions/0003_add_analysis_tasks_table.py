"""add analysis tasks table

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-05

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "analysis_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("archive_id", UUID(as_uuid=True), sa.ForeignKey("archives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(50), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("total_files", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_file", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="ck_analysis_tasks_status",
        ),
    )
    op.create_index("ix_analysis_tasks_archive_id", "analysis_tasks", ["archive_id"])


def downgrade() -> None:
    op.drop_index("ix_analysis_tasks_archive_id", table_name="analysis_tasks")
    op.drop_table("analysis_tasks")
