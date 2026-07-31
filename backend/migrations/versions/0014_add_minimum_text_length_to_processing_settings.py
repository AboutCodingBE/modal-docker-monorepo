"""add minimum_text_length to processing_settings

Revision ID: 0014
Revises: 0013
Create Date: 2026-07-31
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "processing_settings",
        sa.Column("minimum_text_length", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("processing_settings", "minimum_text_length")
