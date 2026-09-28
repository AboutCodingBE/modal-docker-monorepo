"""
Story: "Als een archive_analysis-rij verwijderd wordt (bv. bij een redo),
moeten de bijhorende tag_index-rijen automatisch mee verdwijnen (CASCADE)?"
"""

import uuid

from sqlalchemy import text


def test_M7_02_tagindex_cascade_bij_redo(ner_prerequisites, db_conn):
    ids = ner_prerequisites
    tag_id = uuid.uuid4()

    db_conn.execute(text("""
        INSERT INTO tag_index (id, archive_id, analysis_id, file_id, source, category, value, count)
        VALUES (:id, :archive_id, :analysis_id, :file_id, 'ner', 'persons', 'Jan Janssens', 1)
    """), {
        "id": str(tag_id),
        "archive_id": str(ids["archive_id"]),
        "analysis_id": str(ids["analysis_id"]),
        "file_id": str(ids["file_id"]),
    })

    # Sanity check: de rij staat er voor we de cascade triggeren.
    before = db_conn.execute(text("SELECT id FROM tag_index WHERE id = :id"), {"id": str(tag_id)})
    assert before.first() is not None

    db_conn.execute(text("DELETE FROM archive_analysis WHERE id = :id"), {"id": str(ids["analysis_id"])})

    after = db_conn.execute(text("SELECT id FROM tag_index WHERE id = :id"), {"id": str(tag_id)})
    assert after.first() is None
