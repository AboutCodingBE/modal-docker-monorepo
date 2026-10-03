"""add embedding analysis type

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-26

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ADD VALUE kan niet in dezelfde transactie als statements die de nieuwe
    # waarde gebruiken — autocommit_block commit eerst, opent dan een nieuwe transactie.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE analysis_type ADD VALUE IF NOT EXISTS 'EMBEDDING'")


def downgrade() -> None:
    # Postgres ondersteunt geen ALTER TYPE ... DROP VALUE — de enum-waarde blijft staan.
    pass
