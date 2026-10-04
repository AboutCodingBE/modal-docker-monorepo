"""add embedding_settings table

Revision ID: 0027
Revises: 0026
Create Date: 2026-10-03

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0027"
down_revision: str | None = "0026"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "embedding_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("embedding_chunk_size", sa.Integer(), nullable=False, server_default="512"),
        sa.Column("embedding_max_chunks_per_file", sa.Integer(), nullable=True),
        sa.Column("search_max_distance", sa.Float(), nullable=False, server_default="0.7"),
        sa.Column("search_top_n", sa.Integer(), nullable=False, server_default="25"),
        sa.Column("embedding_model_downloaded", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.execute(
        "INSERT INTO embedding_settings "
        "(id, embedding_chunk_size, embedding_max_chunks_per_file, search_max_distance, search_top_n, embedding_model_downloaded) "
        "VALUES (gen_random_uuid(), 512, 1, 0.7, 25, false)"
    )


def downgrade() -> None:
    op.drop_table("embedding_settings")
