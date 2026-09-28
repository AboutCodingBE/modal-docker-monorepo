"""enable unaccent extension and replace file_entities/file_topics text indexes with archive-scoped composite indexes

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-19
"""
from alembic import op

revision: str = "0021"
down_revision: str | None = "0020"


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")

    # Replace single-column entity_text index with composite for autocomplete
    # (archive_id, entity_type, entity_text) lets Postgres narrow by archive+type
    # before applying the unaccent ILIKE condition on entity_text.
    op.drop_index("idx_file_entities_text", table_name="file_entities")
    op.create_index(
        "idx_file_entities_autocomplete",
        "file_entities",
        ["archive_id", "entity_type", "entity_text"],
    )

    # Replace single-column topic_label index with archive-scoped composite
    op.drop_index("idx_file_topics_label", table_name="file_topics")
    op.create_index(
        "idx_file_topics_autocomplete",
        "file_topics",
        ["archive_id", "topic_label"],
    )


def downgrade() -> None:
    op.drop_index("idx_file_topics_autocomplete", table_name="file_topics")
    op.create_index("idx_file_topics_label", "file_topics", ["topic_label"])

    op.drop_index("idx_file_entities_autocomplete", table_name="file_entities")
    op.create_index("idx_file_entities_text", "file_entities", ["entity_text"])

    # Note: unaccent extension is not dropped on downgrade to avoid breaking
    # other objects that might depend on it.
