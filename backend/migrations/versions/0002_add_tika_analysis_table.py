"""add tika analysis table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0002"
down_revision: str | None = "249feff1ae97"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Maak de nieuwe tabel aan voor de Tika resultaten
    op.create_table(
        "tika_analyses",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Koppeling naar de bestaande 'files' tabel uit migratie 0001
        sa.Column(
            "file_id", 
            UUID(as_uuid=True), 
            sa.ForeignKey("files.id", ondelete="CASCADE"), 
            nullable=False, 
            unique=True
        ),
        sa.Column("mime_type", sa.String(255), nullable=True),
        sa.Column("tika_parser", sa.Text, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("language", sa.String(10), nullable=True),
        sa.Column("word_count", sa.Integer, nullable=True),
        sa.Column("author", sa.String(500), nullable=True),
        sa.Column("content_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    
    op.create_index("idx_analyses_file", "tika_analyses", ["file_id"])
    op.create_index("idx_analyses_lang", "tika_analyses", ["language"])


def downgrade() -> None:
    op.drop_index("idx_analyses_lang", table_name="tika_analyses")
    op.drop_index("idx_analyses_file", table_name="tika_analyses")
    op.drop_table("tika_analyses")