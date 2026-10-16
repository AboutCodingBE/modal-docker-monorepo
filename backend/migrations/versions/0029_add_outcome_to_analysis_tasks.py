"""add outcome column to analysis_tasks

Revision ID: 0029
Revises: 0028
Create Date: 2026-10-16
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0029"
down_revision: str | None = "0028"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("analysis_tasks", sa.Column("outcome", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("analysis_tasks", "outcome")
