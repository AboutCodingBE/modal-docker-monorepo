"""refactor ner: JSONB entities met counts, drop ARRAY en count kolommen

Revision ID: 0010
Revises: 0009
Create Date: 2026-07-01

Vervangt de vier ARRAY(Text)-kolommen en de vier *_count Integer-kolommen door
vier JSONB-kolommen die op bestandsniveau [{entity, count: 1}] opslaan en op
mapniveau [{entity, count: N}] na aggregatie. Dit maakt folder-aggregatie via
een simpele GROUP BY SUM mogelijk zonder aparte kolommen.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_JSONB = sa.text("'[]'::jsonb")
_CATEGORIES = ("persons", "locations", "organisations", "misc")


def upgrade() -> None:
    for col in (f"{c}_count" for c in _CATEGORIES):
        op.drop_column("ner", col)
    for col in _CATEGORIES:
        op.drop_column("ner", col)
    for col in _CATEGORIES:
        op.add_column("ner", sa.Column(col, JSONB(), nullable=False, server_default=_EMPTY_JSONB))


def downgrade() -> None:
    for col in reversed(_CATEGORIES):
        op.drop_column("ner", col)
    for col in _CATEGORIES:
        op.add_column("ner", sa.Column(col, sa.ARRAY(sa.Text()), nullable=True))
    for col in (f"{c}_count" for c in _CATEGORIES):
        op.add_column("ner", sa.Column(col, sa.Integer(), nullable=True))
