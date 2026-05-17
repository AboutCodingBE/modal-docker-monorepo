import uuid

from sqlalchemy import text


def test_ner_insert(db_conn, ner_prerequisites):
    archive_id = ner_prerequisites["archive_id"]
    file_id = ner_prerequisites["file_id"]
    analysis_id = ner_prerequisites["analysis_id"]
    parent_folder_id = uuid.uuid4()
    ner_id = uuid.uuid4()

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

    row = db_conn.execute(
        text("SELECT * FROM ner WHERE id = :id"),
        {"id": str(ner_id)}
    ).mappings().one()

    assert row["person_count"] == 2
    assert "Jan Janssen" in row["persons"]
    assert row["locations"] == ["Gent"]
    assert row["organisations"] == ["Amsab-ISG"]
    assert row["misc"] is None
