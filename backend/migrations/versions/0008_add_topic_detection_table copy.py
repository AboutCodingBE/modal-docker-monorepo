"""add topic detection table

Revision ID: 0008
Revises: 0007
Create Date: 2026-06-16

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- ner ---
    op.create_table(
        "topic_detection",
        sa.Column("id",
            UUID(as_uuid=True), #UUID 128-bit format
            primary_key=True, #PK => NOT NULL
            server_default=sa.text("gen_random_uuid()")), #gen_random_uuid() generates random_key
        sa.Column(
            "archive_id",
            UUID(as_uuid=True),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("archive_analysis.id", ondelete="CASCADE"), #FK to archive_analysis table
            nullable=False,
        ),
        sa.Column(
            "parent_folder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"), #FK to file that is undergoing Topic Detection analysis
            nullable=False,
        ), 
        sa.Column("topics", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("ptopics_count", sa.Integer(), nullable=True),
    )
    #indexes on all FK columns
    op.create_index("ix_topic_detection_archive_id", "topic_detection", ["archive_id"])
    op.create_index("ix_topic_detection_analysis_id", "topic_detection", ["analysis_id"])
    op.create_index("ix_topic_detection_file_id", "topic_detection", ["file_id"])

    op.execute(
        "INSERT INTO analysis_configuration (id, type, model) "
        "VALUES (gen_random_uuid(), 'Topic Detection', 'BERTopic')"
    )

def downgrade() -> None:
    op.execute("DELETE FROM analysis_configuration WHERE type = 'Topic Detection'")
    op.drop_index("ix_topic_detection_file_id", table_name="topic_detection")
    op.drop_index("ix_topic_detection_analysis_id", table_name="topic_detection")
    op.drop_index("ix_topic_detection_archive_id", table_name="topic_detection")
    op.drop_table("topic_detection")
