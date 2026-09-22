"""add file_entities and file_topics flat index tables

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-19
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0019"
down_revision: str | None = "0018"


def upgrade() -> None:
    op.create_table(
        "file_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("archive_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_text", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["ner_id"],
            ["ner.id"],
            name="file_entities_ner_id_fkey",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_file_entities_archive", "file_entities", ["archive_id"])
    op.create_index("idx_file_entities_text", "file_entities", ["entity_text"])

    op.create_table(
        "file_topics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("archive_id", UUID(as_uuid=True), nullable=False),
        sa.Column("topic_detection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("topic_label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(
            ["topic_detection_id"],
            ["topic_detection.id"],
            name="file_topics_topic_detection_id_fkey",
            ondelete="CASCADE",
        ),
    )
    op.create_index("idx_file_topics_archive", "file_topics", ["archive_id"])
    op.create_index("idx_file_topics_label", "file_topics", ["topic_label"])


def downgrade() -> None:
    op.drop_index("idx_file_topics_label", table_name="file_topics")
    op.drop_index("idx_file_topics_archive", table_name="file_topics")
    op.drop_table("file_topics")

    op.drop_index("idx_file_entities_text", table_name="file_entities")
    op.drop_index("idx_file_entities_archive", table_name="file_entities")
    op.drop_table("file_entities")
