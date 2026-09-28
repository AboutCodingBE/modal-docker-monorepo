"""M7 — create_tag_index_for_archive: tag_index-tabel vullen vanuit Ner/TopicDetection
(app/create_tag_index_for_archive/).

M7.03 — TagIndexRepository.persist()/exists().

Story: "Geeft exists() True terug na een eerste persist, en wat gebeurt er als
dezelfde tag (file_id, source, category, value) twee keer gepersist wordt?"

Wat we testen:
  1. persist() van 2 entries voor 1 bestand → exists(analysis_id, file_id) is True,
     en beide rijen staan in de tabel.
  2. Een dubbele insert van exact dezelfde (file_id, source, category, value) wordt
     stilzwijgend genegeerd (ON CONFLICT DO NOTHING op de UniqueConstraint) —
     geen exception, geen duplicaat.

Teststrategie:
  - ECHT: TagIndexRepository.persist() en exists() op echte PostgreSQL.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository


@pytest.mark.asyncio
async def test_tagindex_exists_geeft_true_na_persist(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, file_id, analysis_id = await _setup(session, cleanup_ids)

    repo = TagIndexRepository(session)
    await repo.persist(archive_id, analysis_id, file_id, [
        ("ner", "persons", "Jan Janssens", 1),
        ("ner", "locations", "Gent", 1),
    ])
    await session.commit()

    bestaat = await repo.exists(analysis_id, file_id)
    assert bestaat, "exists() geeft False terug na persist()"

    rij = await session.execute(
        text("SELECT COUNT(*) FROM tag_index WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(file_id), "aid": str(analysis_id)},
    )
    assert rij.scalar() == 2


@pytest.mark.asyncio
async def test_tagindex_dubbele_tag_wordt_genegeerd(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, file_id, analysis_id = await _setup(session, cleanup_ids)

    repo = TagIndexRepository(session)
    entry = [("ner", "persons", "Jan Janssens", 1)]

    await repo.persist(archive_id, analysis_id, file_id, entry)
    await session.commit()

    # Zelfde (file_id, source, category, value) nogmaals persisten — mag niet falen
    # en mag geen duplicaat aanmaken (UniqueConstraint + ON CONFLICT DO NOTHING).
    await repo.persist(archive_id, analysis_id, file_id, entry)
    await session.commit()

    rij = await session.execute(
        text("SELECT COUNT(*) FROM tag_index WHERE file_id = :fid AND value = 'Jan Janssens'"),
        {"fid": str(file_id)},
    )
    aantal = rij.scalar()
    print(f"\n[M7.03] Aantal tag_index-rijen na twee keer persist() van dezelfde tag: {aantal}")

    assert aantal == 1, (
        f"Twee keer persist() van dezelfde tag heeft {aantal} rijen aangemaakt — "
        "verwacht 1 (ON CONFLICT DO NOTHING op uq_tag_index_file_source_category_value)."
    )


async def _setup(session, cleanup_ids) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Maakt minimale DB-rijen aan en geeft (archive_id, file_id, analysis_id) terug."""
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tagindex-test-persist", "root_path": f"/tmp/tagindex-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief_1952.txt",
            "full_path": f"/tmp/tagindex-test/{archive_id}/brief_1952.txt",
            "relative_path": "brief_1952.txt",
        },
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    return archive_id, file_id, analysis_id
