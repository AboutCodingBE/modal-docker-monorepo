"""add ner frequency columns

Revision ID: 0010
Revises: 0009
Create Date: 2026-06-30

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

_EMPTY_JSONB = sa.text("'[]'::jsonb")

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("ner", sa.Column("persons_frequencies", JSONB(), nullable=False, server_default=_EMPTY_JSONB))
    op.add_column("ner", sa.Column("locations_frequencies", JSONB(), nullable=False, server_default=_EMPTY_JSONB))
    op.add_column("ner", sa.Column("organisations_frequencies", JSONB(), nullable=False, server_default=_EMPTY_JSONB))
    op.add_column("ner", sa.Column("misc_frequencies", JSONB(), nullable=False, server_default=_EMPTY_JSONB))


def downgrade() -> None:
    op.drop_column("ner", "misc_frequencies")
    op.drop_column("ner", "organisations_frequencies")
    op.drop_column("ner", "locations_frequencies")
    op.drop_column("ner", "persons_frequencies")
