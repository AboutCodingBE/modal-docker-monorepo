"""add is_default to analysis_configuration, drop per-type uniqueness

Revision ID: 0012
Revises: 0011
Create Date: 2026-07-30
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop the unique constraint on type so multiple rows per type are allowed.
    op.drop_constraint("uq_analysis_configuration_type", "analysis_configuration", type_="unique")

    op.add_column(
        "analysis_configuration",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Today there is exactly one row per type — that row becomes the initial default.
    op.execute("UPDATE analysis_configuration SET is_default = true")


def downgrade() -> None:
    op.drop_column("analysis_configuration", "is_default")
    op.create_unique_constraint("uq_analysis_configuration_type", "analysis_configuration", ["type"])
