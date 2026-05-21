"""add generictype table

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-19

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
    # Maak de nieuwe tabel aan voor de Tika resultaten
    op.create_table(
        "generic_types",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        # Koppeling naar de bestaande 'files' tabel uit migratie 0001
        sa.Column(
            "file_id", 
            UUID(as_uuid=True), 
            sa.ForeignKey("files.id", ondelete="CASCADE"), 
            nullable=False, 
            unique=True
        ),
        sa.Column("generic_type", sa.String(255), nullable=True),
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("generic_type")