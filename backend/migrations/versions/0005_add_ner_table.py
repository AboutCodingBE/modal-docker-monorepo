"""add ner table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-17

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --- ner ---
    op.create_table(
        "ner",
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
        sa.Column("parent_folder_id", UUID(as_uuid=True), nullable=False),
        sa.Column(
            "file_id",
            UUID(as_uuid=True),
            sa.ForeignKey("files.id", ondelete="CASCADE"), #FK to file that is undergoing NER analysis
            nullable=False,
        ), 
        #NER output: persons, locations, organisations and MISC
        sa.Column("persons", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("person_count", sa.Integer(), nullable=True),
        sa.Column("locations", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("location_count", sa.Integer(), nullable=True),
        sa.Column("organisations", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("organisations_count", sa.Integer(), nullable=True),
        sa.Column("misc", sa.ARRAY(sa.Text()), nullable=True),
        sa.Column("misc_count", sa.Integer(), nullable=True),
    )
    #indexes on all FK columns
    op.create_index("ix_ner_archive_id", "ner", ["archive_id"])
    op.create_index("ix_ner_analysis_id", "ner", ["analysis_id"])
    op.create_index("ix_ner_file_id", "ner", ["file_id"])


def downgrade() -> None: 
    op.drop_index("ix_ner_file_id", table_name="ner")
    op.drop_index("ix_ner_analysis_id", table_name="ner")
    op.drop_index("ix_ner_archive_id", table_name="ner")
    op.drop_table("ner")
