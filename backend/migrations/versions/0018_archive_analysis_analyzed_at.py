"""rename archive_analysis.date to analyzed_at (DateTime, not Date)

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-05
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"


def upgrade() -> None:
    op.add_column(
        "archive_analysis",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from the old date column — midnight UTC on that date, the
    # best available information for historical rows.
    op.execute("UPDATE archive_analysis SET analyzed_at = date::timestamptz")
    op.alter_column("archive_analysis", "analyzed_at", nullable=False, server_default=sa.func.now())
    op.drop_column("archive_analysis", "date")


def downgrade() -> None:
    op.add_column(
        "archive_analysis",
        sa.Column("date", sa.Date(), nullable=True, server_default=sa.func.current_date()),
    )
    op.execute("UPDATE archive_analysis SET date = analyzed_at::date")
    op.alter_column("archive_analysis", "date", nullable=False)
    op.drop_column("archive_analysis", "analyzed_at")
