"""add file_correspondents table

Revision ID: 0028
Revises: 0027
Create Date: 2026-10-15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0028"
down_revision: str | None = "0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_correspondents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("archive_id", UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("name", sa.String(500), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["files.id"],
            name="file_correspondents_file_id_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "email IS NOT NULL OR name IS NOT NULL",
            name="ck_file_correspondents_email_or_name",
        ),
    )
    op.create_index("idx_file_correspondents_file", "file_correspondents", ["file_id"])
    op.create_index(
        "idx_file_correspondents_archive_email",
        "file_correspondents",
        ["archive_id", sa.text("lower(email)")],
    )


def downgrade() -> None:
    op.drop_index("idx_file_correspondents_archive_email", table_name="file_correspondents")
    op.drop_index("idx_file_correspondents_file", table_name="file_correspondents")
    op.drop_table("file_correspondents")
