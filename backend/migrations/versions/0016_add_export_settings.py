"""add export_settings table

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-29
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "export_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("default_export_path", sa.String(2000), nullable=True),
        sa.Column("content_char_limit", sa.Integer(), nullable=False, server_default="2000"),
    )
    op.execute(
        "INSERT INTO export_settings (id, default_export_path, content_char_limit) "
        "VALUES (gen_random_uuid(), NULL, 2000)"
    )


def downgrade() -> None:
    op.drop_table("export_settings")
