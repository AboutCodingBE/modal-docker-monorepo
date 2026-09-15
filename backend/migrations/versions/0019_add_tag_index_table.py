"""add tag_index table

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-15

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019"
down_revision: str | None = "0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tag_index",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("archive_id", UUID(as_uuid=True), sa.ForeignKey("archives.id", ondelete="CASCADE"), nullable=False),
        sa.Column("analysis_id", UUID(as_uuid=True), sa.ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_id", UUID(as_uuid=True), sa.ForeignKey("files.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("category", sa.String(20), nullable=True),
        sa.Column("value", sa.String(500), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("file_id", "source", "category", "value", name="uq_tag_index_file_source_category_value"),
    )
    op.create_index("ix_tag_index_archive_id_value", "tag_index", ["archive_id", "value"])
    op.create_index("ix_tag_index_analysis_id", "tag_index", ["analysis_id"])
    op.create_index("ix_tag_index_file_id", "tag_index", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_tag_index_file_id", table_name="tag_index")
    op.drop_index("ix_tag_index_analysis_id", table_name="tag_index")
    op.drop_index("ix_tag_index_archive_id_value", table_name="tag_index")
    op.drop_table("tag_index")
