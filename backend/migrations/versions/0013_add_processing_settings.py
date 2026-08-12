"""add processing_settings table

Revision ID: 0013
Revises: 0012
Create Date: 2026-07-30
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("summary_char_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("topic_char_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("ner_llm_char_limit", sa.Integer(), nullable=False, server_default="6000"),
    )
    # Seed the single row the app always expects to exist.
    op.execute(
        "INSERT INTO processing_settings (id, summary_char_limit, topic_char_limit, ner_llm_char_limit) "
        "VALUES (gen_random_uuid(), 1000, 1000, 6000)"
    )


def downgrade() -> None:
    op.drop_table("processing_settings")
