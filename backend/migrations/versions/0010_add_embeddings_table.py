"""add embeddings table

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-12

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "embeddings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Volgorde van de chunk binnen het brondocument
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        # Brontekst van de chunk, nodig om terug te tonen bij een zoekresultaat
        sa.Column("chunk_text", sa.Text(), nullable=False),
        # Optioneel, handig voor debugging/benchmark
        sa.Column("token_count", sa.Integer(), nullable=True),
        # qwen3-embedding output
        sa.Column("embedding", Vector(1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "chunk_index", name="uq_embeddings_file_id_chunk_index"),
    )


def downgrade() -> None:
    op.drop_table("embeddings")
