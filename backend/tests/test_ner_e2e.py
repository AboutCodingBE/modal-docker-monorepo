"""
Run with:
    pytest tests/test_ner_e2e.py -v -s

End-to-end illustrative test for the full NER flow on real archive data.

Steps:
  1. Pick a real archive from the database
  2. Pick one file with Tika-extracted text
  3. Run the spaCy NER engine on that text
  4. Write the result to the ner table
  5. Read it back and print the findings

The -s flag is required to see the print output in the terminal.
All database writes are rolled back at the end — no permanent changes.
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import run_ner


def test_ner_end_to_end(db_conn):
    # ── Step 1: find a real archive ───────────────────────────────────────────
    archive_row = db_conn.execute(text("""
        SELECT a.id, a.name
        FROM archives a
        JOIN files f ON f.archive_id = a.id
        JOIN tika_analyses t ON t.file_id = f.id
        WHERE t.content IS NOT NULL
          AND t.word_count >= 30
        LIMIT 1
    """)).mappings().first()

    if archive_row is None:
        pytest.skip("No archive with analysed files found in the database.")

    archive_id = archive_row["id"]
    print(f"\n✔ Archive selected: '{archive_row['name']}' (id: {archive_id})")

    # ── Step 2: pick one file with tika content ───────────────────────────────
    file_row = db_conn.execute(text("""
        SELECT f.id, f.name, f.relative_path, f.parent_id, t.content, t.word_count
        FROM files f
        JOIN tika_analyses t ON t.file_id = f.id
        WHERE f.archive_id = :archive_id
          AND f.is_directory = false
          AND t.content IS NOT NULL
          AND t.word_count >= 30
        LIMIT 1
    """), {"archive_id": str(archive_id)}).mappings().first()

    if file_row is None:
        pytest.skip("No usable file found in the selected archive.")

    file_id = file_row["id"]
    parent_folder_id = file_row["parent_id"] or uuid.uuid4()
    content = file_row["content"]

    print(f"✔ File selected  : '{file_row['name']}' ({file_row['word_count']} words)")
    print(f"  Path           : {file_row['relative_path']}")
    print(f"  Text preview   : {content[:200].replace(chr(10), ' ')}...")

    # ── Step 3: run the NER engine ────────────────────────────────────────────
    print("\n⏳ Running spaCy NER...")
    result = run_ner(content)

    print(f"\n── NER results ──────────────────────────────────────────")
    print(f"  Persons        ({result['person_count']:>3}): {result['persons'][:5]}")
    print(f"  Locations      ({result['location_count']:>3}): {result['locations'][:5]}")
    print(f"  Organisations  ({result['organisations_count']:>3}): {result['organisations'][:5]}")
    print(f"  Misc           ({result['misc_count']:>3}): {result['misc'][:5]}")
    print(f"─────────────────────────────────────────────────────────")

    # ── Step 4: write to DB ───────────────────────────────────────────────────
    analysis_id = uuid.uuid4()
    ner_id = uuid.uuid4()

    # Create a temporary archive_analysis row to satisfy the foreign key
    db_conn.execute(text("""
        INSERT INTO archive_analysis (id, archive_id, type, model, status)
        VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
    """), {"id": str(analysis_id), "archive_id": str(archive_id)})

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
        **result,
    })

    print(f"\n✔ NER result written to DB (id: {ner_id})")

    # ── Step 5: read back and verify ──────────────────────────────────────────
    saved = db_conn.execute(
        text("SELECT * FROM ner WHERE id = :id"),
        {"id": str(ner_id)}
    ).mappings().one()

    print(f"✔ Read back from DB — person_count: {saved['person_count']}, "
          f"location_count: {saved['location_count']}, "
          f"organisations_count: {saved['organisations_count']}")

    # Minimal assertions — mainly checking the round-trip worked
    assert saved["person_count"] == result["person_count"]
    assert saved["location_count"] == result["location_count"]
    assert saved["organisations_count"] == result["organisations_count"]

    print("\n✔ All checks passed. Rolling back — no permanent changes made.")
