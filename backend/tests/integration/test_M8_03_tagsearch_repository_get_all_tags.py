"""M8 — tag_search_archive: zoeken in de tag_index-tabel (app/tag_search_archive/).

M8.03 — TagIndexRepository.get_all_tags(): unieke tags voor een filterpaneel.

Story: "Geeft get_all_tags() alle unieke tags van een archief terug (gededupliceerd
over bestanden heen), en enkel de tags van 1 categorie als er gefilterd wordt?"

Testarchief: 2 bestanden.
  - file_1: "Jan Janssens" (persons), "Gent" (locations)
  - file_2: "Jan Janssens" (persons) opnieuw -> moet NIET dubbel in het resultaat

Teststrategie:
  - ECHT: TagIndexRepository.get_all_tags() op echte PostgreSQL.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository


@pytest.mark.asyncio
async def test_get_all_tags_zonder_filter_dedupliceert_over_bestanden(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)
    await _seed_tags(session, archive_id, analysis_id)
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.get_all_tags(archive_id)

    gevonden_waarden = {r["value"] for r in resultaten}
    assert gevonden_waarden == {"Jan Janssens", "Gent"}, (
        f"Verwacht 2 unieke tags (Jan Janssens komt op 2 bestanden voor), gevonden: {gevonden_waarden}"
    )
    assert len(resultaten) == 2, "Jan Janssens mag maar 1x voorkomen ondanks 2 bestanden"


@pytest.mark.asyncio
async def test_get_all_tags_met_category_filter(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)
    await _seed_tags(session, archive_id, analysis_id)
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.get_all_tags(archive_id, category="locations")

    assert [r["value"] for r in resultaten] == ["Gent"]


async def _setup(session, cleanup_ids) -> tuple[uuid.UUID, uuid.UUID]:
    archive_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tagsearch-getall-test", "root_path": f"/tmp/tagsearch-getall/{archive_id}"},
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


async def _seed_tags(session, archive_id: uuid.UUID, analysis_id: uuid.UUID) -> None:
    file_1 = await _insert_file(session, archive_id, "brief_1.txt")
    file_2 = await _insert_file(session, archive_id, "brief_2.txt")

    await _insert_tag(session, archive_id, analysis_id, file_1, "persons", "Jan Janssens")
    await _insert_tag(session, archive_id, analysis_id, file_1, "locations", "Gent")
    await _insert_tag(session, archive_id, analysis_id, file_2, "persons", "Jan Janssens")


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
            "full_path": f"/tmp/tagsearch-getall/{archive_id}/{name}",
            "relative_path": name,
        },
    )
    return file_id


async def _insert_tag(
    session, archive_id: uuid.UUID, analysis_id: uuid.UUID, file_id: uuid.UUID, category: str, value: str
) -> None:
    await session.execute(
        text("""
            INSERT INTO tag_index (id, archive_id, analysis_id, file_id, source, category, value, count)
            VALUES (gen_random_uuid(), :archive_id, :analysis_id, :file_id, 'ner', :category, :value, 1)
        """),
        {
            "archive_id": str(archive_id),
            "analysis_id": str(analysis_id),
            "file_id": str(file_id),
            "category": category,
            "value": value,
        },
    )
