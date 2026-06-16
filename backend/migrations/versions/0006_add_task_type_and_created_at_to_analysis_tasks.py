"""add task_type and created_at to analysis_tasks

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-01

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "task_type",
            sa.String(20),
            nullable=False,
            server_default="analysis",
        ),
    )
    op.add_column(
        "analysis_tasks",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )


def downgrade() -> None:
    op.drop_column("analysis_tasks", "created_at")
    op.drop_column("analysis_tasks", "task_type")
