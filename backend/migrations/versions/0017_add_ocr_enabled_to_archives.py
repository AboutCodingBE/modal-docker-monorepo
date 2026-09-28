"""add ocr_enabled to archives

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-05

"""
import sqlalchemy as sa
from alembic import op

revision: str = "0017"
down_revision: str | None = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "archives",
        sa.Column("ocr_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("archives", "ocr_enabled")
