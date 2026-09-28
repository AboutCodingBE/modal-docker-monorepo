"""add composite index on files(archive_id, relative_path) for list view prefix queries

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-19
"""
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"


def upgrade() -> None:
    op.create_index(
        "idx_files_archive_relative_path",
        "files",
        ["archive_id", "relative_path"],
    )


def downgrade() -> None:
    op.drop_index("idx_files_archive_relative_path", table_name="files")
