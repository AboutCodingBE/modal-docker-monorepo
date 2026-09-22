"""M8 — tag_search_archive: zoeken in de tag_index-tabel (app/tag_search_archive/).

M8.01 — TagIndexRepository.search(): prefix-zoekopdracht voor de typeahead-zoekbalk.

Story: "Geeft search() alle tags terug die met een gegeven prefix beginnen (case-
insensitive, join met File), en een lege lijst als niets matcht?"

Teststrategie:
  - ECHT: TagIndexRepository.search() op echte PostgreSQL.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository


@pytest.mark.asyncio
async def test_search_prefix_matcht_beide_tags(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)

    file_1 = await _insert_file(session, archive_id, "brief_jan.txt")
    file_2 = await _insert_file(session, archive_id, "brief_janwillem.txt")
    await _insert_tag(session, archive_id, analysis_id, file_1, "Jan Janssens")
    await _insert_tag(session, archive_id, analysis_id, file_2, "Janwillem")
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.search(archive_id, prefix="Jan", top_n=25)

    gevonden_waarden = {r["value"] for r in resultaten}
    assert gevonden_waarden == {"Jan Janssens", "Janwillem"}


@pytest.mark.asyncio
async def test_search_geen_match_geeft_lege_lijst(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)

    file_1 = await _insert_file(session, archive_id, "brief_jan.txt")
    await _insert_tag(session, archive_id, analysis_id, file_1, "Jan Janssens")
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.search(archive_id, prefix="xyz", top_n=25)

    assert resultaten == []


async def _setup(session, cleanup_ids) -> tuple[uuid.UUID, uuid.UUID]:
    """Maakt een minimaal archief + archive_analysis-rij aan, geeft (archive_id, analysis_id) terug."""
    archive_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tagsearch-test", "root_path": f"/tmp/tagsearch-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'COMPLETED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    return archive_id, analysis_id


async def _insert_file(session, archive_id: uuid.UUID, name: str) -> uuid.UUID:
    file_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": name,
            "full_path": f"/tmp/tagsearch-test/{archive_id}/{name}",
            "relative_path": name,
        },
    )
    return file_id


async def _insert_tag(session, archive_id: uuid.UUID, analysis_id: uuid.UUID, file_id: uuid.UUID, value: str) -> None:
    await session.execute(
        text("""
            INSERT INTO tag_index (id, archive_id, analysis_id, file_id, source, category, value, count)
            VALUES (gen_random_uuid(), :archive_id, :analysis_id, :file_id, 'ner', 'persons', :value, 1)
        """),
        {"archive_id": str(archive_id), "analysis_id": str(analysis_id), "file_id": str(file_id), "value": value},
    )
