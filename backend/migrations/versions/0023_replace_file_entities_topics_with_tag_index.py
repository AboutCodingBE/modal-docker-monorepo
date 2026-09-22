"""replace file_entities and file_topics with tag_index

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-20

"""
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"


def upgrade() -> None:
    # Drop the indexes added in 0021 before dropping the tables
    op.drop_index("idx_file_entities_autocomplete", table_name="file_entities")
    op.drop_index("idx_file_topics_autocomplete", table_name="file_topics")

    # Drop the tables added in 0019
    op.drop_table("file_topics")
    op.drop_table("file_entities")

    # unaccent() is STABLE, not IMMUTABLE, so it cannot be used directly in an index
    # expression. Create a thin IMMUTABLE wrapper so we can index on it.
    op.execute("""
        CREATE OR REPLACE FUNCTION immutable_unaccent(text)
        RETURNS text LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT AS
        $$ SELECT unaccent($1) $$
    """)

    # Functional btree index on immutable_unaccent(value) for fast prefix autocomplete.
    # text_pattern_ops lets Postgres use this index for ILIKE 'prefix%' queries.
    op.execute(
        "CREATE INDEX ix_tag_index_unaccent_value ON tag_index "
        "(immutable_unaccent(value) text_pattern_ops)"
    )


def downgrade() -> None:
    import sqlalchemy as sa
    from sqlalchemy.dialects.postgresql import UUID

    op.execute("DROP INDEX IF EXISTS ix_tag_index_unaccent_value")
    op.execute("DROP FUNCTION IF EXISTS immutable_unaccent(text)")

    op.create_table(
        "file_entities",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("archive_id", UUID(as_uuid=True), nullable=False),
        sa.Column("ner_id", UUID(as_uuid=True), nullable=False),
        sa.Column("entity_text", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["ner_id"], ["ner.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_file_entities_autocomplete", "file_entities", ["archive_id", "entity_type", "entity_text"])

    op.create_table(
        "file_topics",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("file_id", UUID(as_uuid=True), nullable=False),
        sa.Column("archive_id", UUID(as_uuid=True), nullable=False),
        sa.Column("topic_detection_id", UUID(as_uuid=True), nullable=False),
        sa.Column("topic_label", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["topic_detection_id"], ["topic_detection.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_file_topics_autocomplete", "file_topics", ["archive_id", "topic_label"])
