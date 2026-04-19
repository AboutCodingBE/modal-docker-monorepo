"""add ai analysis tables

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

analysis_type_enum = sa.Enum("STT", "NER", "SUMMARY", name="analysis_type")
archive_analysis_status_enum = sa.Enum("STARTED", "FAILED", "COMPLETED", name="archive_analysis_status")


def upgrade() -> None:
    # --- Enums ---
    analysis_type_enum.create(op.get_bind(), checkfirst=True)
    archive_analysis_status_enum.create(op.get_bind(), checkfirst=True)

    # --- analysis_configuration ---
    op.create_table(
        "analysis_configuration",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("type", analysis_type_enum, nullable=False),
        sa.Column("model", sa.String(255), nullable=False),
        sa.UniqueConstraint("type", name="uq_analysis_configuration_type"),
    )

    # Seed: SUMMARY → gemma3:1b
    op.execute(
        "INSERT INTO analysis_configuration (id, type, model) "
        "VALUES (gen_random_uuid(), 'SUMMARY', 'gemma3:1b')"
    )

    # --- archive_analysis ---
    op.create_table(
        "archive_analysis",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column(
            "archive_id",
            UUID(as_uuid=True),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("type", analysis_type_enum, nullable=False),
        sa.Column("date", sa.Date(), nullable=False, server_default=sa.func.current_date()),
        sa.Column("model", sa.String(255), nullable=False),
        sa.Column("status", archive_analysis_status_enum, nullable=False),
    )
    op.create_index("ix_archive_analysis_archive_id", "archive_analysis", ["archive_id"])

    # --- summary ---
    op.create_table(
        "summary",
        sa.Column(
            "analysis_id",
            UUID(as_uuid=True),
            sa.ForeignKey("archive_analysis.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "archive_id",
            UUID(as_uuid=True),
            sa.ForeignKey("archives.id", ondelete="CASCADE"),
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
            sa.ForeignKey("files.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("result", sa.Text(), nullable=True),
    )
    op.create_index("ix_summary_archive_id", "summary", ["archive_id"])
    op.create_index("ix_summary_file_id", "summary", ["file_id"])


def downgrade() -> None:
    op.drop_index("ix_summary_file_id", table_name="summary")
    op.drop_index("ix_summary_archive_id", table_name="summary")
    op.drop_table("summary")

    op.drop_index("ix_archive_analysis_archive_id", table_name="archive_analysis")
    op.drop_table("archive_analysis")

    op.drop_table("analysis_configuration")

    archive_analysis_status_enum.drop(op.get_bind(), checkfirst=True)
    analysis_type_enum.drop(op.get_bind(), checkfirst=True)
