"""
Run with:
    pytest tests/test_ner_insert.py -v

End-to-end database test for the ner table.

This test verifies that a NER result can be written to and read back from
the database correctly. It uses a real database connection (configured via
DATABASE_URL_SYNC in backend/.env).

All data inserted during this test is rolled back at the end — the database
is left exactly as it was before the test ran.

The test depends on two fixtures defined in conftest.py:
  - db_conn         : an open database connection that auto-rollbacks after the test
  - ner_prerequisites: inserts the required parent rows (archive, file, archive_analysis)
                       that the ner table's foreign keys point to
"""

import uuid

from sqlalchemy import text


# NOTE: the function arguments match fixture names from conftest.py.
# pytest automatically finds and injects them — no manual import needed.
def test_ner_insert(db_conn, ner_prerequisites):
    # Retrieve the IDs of the parent rows created by the fixture
    archive_id = ner_prerequisites["archive_id"]
    file_id = ner_prerequisites["file_id"]
    analysis_id = ner_prerequisites["analysis_id"]

    # parent_folder_id has no foreign key constraint, so any UUID is valid
    parent_folder_id = uuid.uuid4()
    ner_id = uuid.uuid4()

    # Insert a NER result row with realistic test data
    db_conn.execute(text("""
        INSERT INTO ner (
            id, archive_id, analysis_id, parent_folder_id, file_id,
            persons, person_count,
            locations, location_count,
            organisations, organisations_count,
            misc, misc_count
        ) VALUES (
            :id, :archive_id, :analysis_id, :parent_folder_id, :file_id,
            :persons, :person_count,
            :locations, :location_count,
            :organisations, :organisations_count,
            :misc, :misc_count
        )
    """), {
        "id": str(ner_id),
        "archive_id": str(archive_id),
        "analysis_id": str(analysis_id),
        "parent_folder_id": str(parent_folder_id),
        "file_id": str(file_id),
        "persons": ["Jan Janssen", "Piet De Smet"],
        "person_count": 2,
        "locations": ["Gent"],
        "location_count": 1,
        "organisations": ["Amsab-ISG"],
        "organisations_count": 1,
        "misc": None,
        "misc_count": 0,
    })

    # Read the row back from the database to verify it was stored correctly
    row = db_conn.execute(
        text("SELECT * FROM ner WHERE id = :id"),
        {"id": str(ner_id)}
    ).mappings().one()

    # Assert that every field matches what we inserted
    assert row["person_count"] == 2
    assert "Jan Janssen" in row["persons"]
    assert row["locations"] == ["Gent"]
    assert row["organisations"] == ["Amsab-ISG"]
    assert row["misc"] is None
