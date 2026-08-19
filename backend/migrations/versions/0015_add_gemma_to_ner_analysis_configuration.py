"""add gemma3:1b to NER analysis_configuration

Revision ID: 0015
Revises: 0014
Create Date: 2026-07-31
"""
from alembic import op

revision: str = "0015"
down_revision: str | None = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO analysis_configuration (id, type, model, is_default)
        VALUES (gen_random_uuid(), 'NER', 'gemma3:1b', false)
        """
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM analysis_configuration WHERE type = 'NER' AND model = 'gemma3:1b'"
    )
