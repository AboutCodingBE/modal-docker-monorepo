"""add embedding analysis type

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-26

"""
from collections.abc import Sequence

from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ALTER TYPE ADD VALUE kan niet in dezelfde transactie als statements die de nieuwe
    # waarde gebruiken — autocommit_block commit eerst, opent dan een nieuwe transactie.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE analysis_type ADD VALUE IF NOT EXISTS 'EMBEDDING'")

    # Seed: EMBEDDING → qwen3-embedding:0.6b (zie settings.embedding_model in app/config.py —
    # hardcoded i.p.v. geïmporteerd, want een migratie moet reproduceerbaar blijven ongeacht
    # latere settings-wijzigingen).
    op.execute(
        "INSERT INTO analysis_configuration (id, type, model) "
        "VALUES (gen_random_uuid(), 'EMBEDDING', 'qwen3-embedding:0.6b')"
    )


def downgrade() -> None:
    # Postgres ondersteunt geen ALTER TYPE ... DROP VALUE — de enum-waarde zelf blijft
    # dus staan, net als bij TOPIC_DETECTION. Enkel de geseede config-rij wordt verwijderd.
    op.execute("DELETE FROM analysis_configuration WHERE type = 'EMBEDDING'")
