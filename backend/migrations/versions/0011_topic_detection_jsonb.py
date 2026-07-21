"""refactor topic_detection: JSONB topics met counts, drop ARRAY en count kolom

Revision ID: 0011
Revises: 0010
Create Date: 2026-07-01

Vervangt de ARRAY(Text)-kolom en de topics_count Integer-kolom door één
JSONB-kolom die op bestandsniveau [{"topic": "...", "count": 1}] opslaat en op
mapniveau [{"topic": "...", "count": N}] na aggregatie. Dit maakt
folder-aggregatie via een simpele GROUP BY SUM mogelijk, consistent met de
aanpak voor NER.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0011"
down_revision: str | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EMPTY_JSONB = sa.text("'[]'::jsonb")


def upgrade() -> None:
    op.drop_column("topic_detection", "topics_count")
    op.drop_column("topic_detection", "topics")
    op.add_column(
        "topic_detection",
        sa.Column("topics", JSONB(), nullable=False, server_default=_EMPTY_JSONB),
    )


def downgrade() -> None:
    op.drop_column("topic_detection", "topics")
    op.add_column(
        "topic_detection",
        sa.Column("topics", sa.ARRAY(sa.Text()), nullable=True),
    )
    op.add_column(
        "topic_detection",
        sa.Column("topics_count", sa.Integer(), nullable=True),
    )
