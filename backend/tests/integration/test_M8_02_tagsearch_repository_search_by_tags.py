"""M8 — tag_search_archive: zoeken in de tag_index-tabel (app/tag_search_archive/).

M8.02 — TagIndexRepository.search_by_tags(): multi-tag filter (AND/OR) voor een
filterpaneel waar de gebruiker al concrete tags heeft aangeklikt.

Story: "Geeft search_by_tags() bij match='all' enkel bestanden terug die ALLE
opgegeven tags hebben, bij match='any' bestanden met MINSTENS 1 ervan, en een lege
lijst als er geen enkele match is?"

Testarchief: 3 bestanden.
  - file_A: "Jan Janssens" + "Gent"   (heeft beide)
  - file_B: "Jan Janssens"            (heeft er maar 1)
  - file_C: "Gent"                    (heeft er maar 1, de andere)

Teststrategie:
  - ECHT: TagIndexRepository.search_by_tags() op echte PostgreSQL.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_tag_index_for_archive.tag_index_repository import TagIndexRepository


@pytest.mark.asyncio
async def test_search_by_tags_match_all_enkel_bestand_met_beide_tags(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)
    file_a, file_b, file_c = await _seed_bestanden(session, archive_id, analysis_id)
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.search_by_tags(
        archive_id, values=["Jan Janssens", "Gent"], top_n=25, match="all"
    )

    gevonden_bestanden = {r["file_id"] for r in resultaten}
    assert gevonden_bestanden == {file_a}, (
        f"Verwacht enkel file_a (heeft beide tags), gevonden bestanden: {gevonden_bestanden}"
    )
    assert len(resultaten) == 2, "file_a heeft 2 matchende tags -> 2 rijen (1 per tag)"


@pytest.mark.asyncio
async def test_search_by_tags_match_any_alle_bestanden_met_minstens_1_tag(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)
    file_a, file_b, file_c = await _seed_bestanden(session, archive_id, analysis_id)
    await session.commit()

    repo = TagIndexRepository(session)
    resultaten = await repo.search_by_tags(
        archive_id, values=["Jan Janssens", "Gent"], top_n=25, match="any"
    )

    gevonden_bestanden = {r["file_id"] for r in resultaten}
    assert gevonden_bestanden == {file_a, file_b, file_c}, (
        f"Verwacht alle 3 bestanden (elk heeft minstens 1 tag), gevonden: {gevonden_bestanden}"
    )
    assert len(resultaten) == 4, "file_a levert 2 rijen op (beide tags), file_b en file_c elk 1"


@pytest.mark.asyncio
async def test_search_by_tags_geen_match_geeft_lege_lijst(committing_db_session):
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _setup(session, cleanup_ids)
    await _seed_bestanden(session, archive_id, analysis_id)
    await session.commit()

    repo = TagIndexRepository(session)

    assert await repo.search_by_tags(archive_id, values=["xyz"], top_n=25, match="any") == []
    assert await repo.search_by_tags(archive_id, values=["xyz"], top_n=25, match="all") == []


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
        {"id": str(archive_id), "name": "tagsearch-and-or-test", "root_path": f"/tmp/tagsearch-and-or/{archive_id}"},
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


async def _seed_bestanden(session, archive_id: uuid.UUID, analysis_id: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """file_a: Jan Janssens + Gent, file_b: enkel Jan Janssens, file_c: enkel Gent."""
    file_a = await _insert_file(session, archive_id, "brief_a.txt")
    file_b = await _insert_file(session, archive_id, "brief_b.txt")
    file_c = await _insert_file(session, archive_id, "brief_c.txt")

    await _insert_tag(session, archive_id, analysis_id, file_a, "Jan Janssens")
    await _insert_tag(session, archive_id, analysis_id, file_a, "Gent")
    await _insert_tag(session, archive_id, analysis_id, file_b, "Jan Janssens")
    await _insert_tag(session, archive_id, analysis_id, file_c, "Gent")

    return file_a, file_b, file_c


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
            "full_path": f"/tmp/tagsearch-and-or/{archive_id}/{name}",
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
