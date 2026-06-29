"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.04 — Koppeling van het NER-resultaat aan de juiste map.

Story: "Wordt het NER-resultaat gekoppeld aan de correcte map via
parent_folder_id?"

Wat we testen:
  In een archief staan bestanden in mappen. Het NER-resultaat moet via
  parent_folder_id verwijzen naar de map waarin het bestand zit, zodat
  downstream-queries (bv. "alle entiteiten uit map X") correct werken.

  CreateNerForArchive haalt parent_id op via FileRepository en geeft die
  door aan NerRepository.persist(). Deze test verifieert dat de koppeling
  correct in de DB terechtkomt.

  We testen twee gevallen:
    1. Bestand in een map → parent_folder_id = map-id
    2. Bestand in de root → parent_folder_id = NULL

Teststrategie:
  - Geen run_ner() nodig — we testen de FK-koppeling, niet de NER-engine.
  - ECHT: NerRepository.persist() schrijft naar echte PostgreSQL.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_repository import NerRepository


_LEEG_NER_RESULTAAT = {
    "persons": [], "persons_count": 0,
    "locations": [], "locations_count": 0,
    "organisations": [], "organisations_count": 0,
    "misc": [], "misc_count": 0,
}


@pytest.mark.asyncio
async def test_ner_resultaat_gekoppeld_aan_correcte_map_via_parent_folder_id(
    committing_db_session,
):
    """Een bestand in een map krijgt parent_folder_id = map-id in de ner-rij."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-parent-folder", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    # Map-rij: is_directory=true, geen parent (staat in de root van het archief)
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, true)
        """),
        {
            "id": str(folder_id),
            "archive_id": str(archive_id),
            "name": "correspondentie",
            "full_path": f"/tmp/ner-test/{archive_id}/correspondentie",
            "relative_path": "correspondentie",
        },
    )
    # Bestandsrij: parent_id wijst naar de map hierboven
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :parent_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "parent_id": str(folder_id),
            "name": "brief_1952.txt",
            "full_path": f"/tmp/ner-test/{archive_id}/correspondentie/brief_1952.txt",
            "relative_path": "correspondentie/brief_1952.txt",
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

    # parent_folder_id = folder_id — zoals CreateNerForArchive dat doorgeeft
    # vanuit file["parent_id"] in FileRepository.get_files_with_tika_content()
    await NerRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=folder_id,
        file_id=file_id,
        ner_result=_LEEG_NER_RESULTAAT,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT parent_folder_id FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    ner_rij = rij.mappings().one()

    print(f"\n[M3.04] parent_folder_id in DB: {ner_rij['parent_folder_id']}")
    print(f"[M3.04] verwacht:               {folder_id}")

    assert ner_rij["parent_folder_id"] == folder_id, (
        f"parent_folder_id in DB is {ner_rij['parent_folder_id']!r}, "
        f"maar verwacht {folder_id!r}. "
        "Controleer of CreateNerForArchive file['parent_id'] correct doorgeeft "
        "aan NerRepository.persist()."
    )


@pytest.mark.asyncio
async def test_ner_resultaat_heeft_null_parent_folder_id_voor_rootbestand(
    committing_db_session,
):
    """Een bestand in de root van het archief (geen map) krijgt parent_folder_id = NULL."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-root-bestand", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "losse_brief.txt",
            "full_path": f"/tmp/ner-test/{archive_id}/losse_brief.txt",
            "relative_path": "losse_brief.txt",
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

    await NerRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        ner_result=_LEEG_NER_RESULTAAT,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT parent_folder_id FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    ner_rij = rij.mappings().one()

    print(f"\n[M3.04] parent_folder_id voor rootbestand: {ner_rij['parent_folder_id']}")

    assert ner_rij["parent_folder_id"] is None, (
        f"parent_folder_id moet NULL zijn voor een rootbestand, "
        f"maar is {ner_rij['parent_folder_id']!r}."
    )
