"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.04 — parent_folder_id koppeling bij summary-persistentie.

Story: "Wordt de samenvatting van een bestand correct gekoppeld aan de map
waarin dat bestand zich bevindt?"

Wat we testen:
  SummaryRepository.persist() accepteert een parent_folder_id. We verifiëren dat:
    1. Een bestand in een map → summary-rij heeft parent_folder_id ingevuld.
    2. Een bestand in de root (geen parent) → parent_folder_id is NULL.

  Geen Ollama nodig: we gebruiken een vaste teststring als samenvatting.

Teststrategie:
  - ECHT: SummaryRepository.persist() schrijft naar echte PostgreSQL.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_summaries_for_archive.summary_repository import SummaryRepository


@pytest.mark.asyncio
async def test_summary_heeft_correct_parent_folder_id_voor_bestand_in_map(
    committing_db_session,
):
    """persist() slaat parent_folder_id op zodat de samenvatting aan de juiste
    map gekoppeld is — basis voor folderniveau-aggregatie."""
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
        {"id": str(archive_id), "name": "summary-test-koppeling", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'correspondentie', :fp, 'correspondentie', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/correspondentie"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :parent_id, 'brief.txt', :fp, 'correspondentie/brief.txt', false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "parent_id": str(folder_id),
            "fp": f"/tmp/summary-test/{archive_id}/correspondentie/brief.txt",
        },
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'SUMMARY', 'llama3.2', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    await SummaryRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=folder_id,
        file_id=file_id,
        result="Testbrief van Jan Hendrickx aan het Gemeentearchief.",
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT parent_folder_id FROM summary WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_parent_folder_id = rij.scalar()

    print(f"\n[M5.04] folder_id (verwacht):        {folder_id}")
    print(f"[M5.04] parent_folder_id (in DB):    {db_parent_folder_id}")

    assert str(db_parent_folder_id) == str(folder_id), (
        f"parent_folder_id in DB ({db_parent_folder_id}) verschilt van de opgegeven folder_id ({folder_id})."
    )


@pytest.mark.asyncio
async def test_summary_heeft_null_parent_folder_id_voor_bestand_in_root(
    committing_db_session,
):
    """persist() met parent_folder_id=None slaat NULL op voor rootbestanden."""
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
        {"id": str(archive_id), "name": "summary-test-root", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'readme.txt', :fp, 'readme.txt', false)
        """),
        {"id": str(file_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/readme.txt"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'SUMMARY', 'llama3.2', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    await SummaryRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        result="Rootbestand zonder bovenliggende map.",
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT parent_folder_id FROM summary WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_parent_folder_id = rij.scalar()

    print(f"\n[M5.04] parent_folder_id voor rootbestand: {db_parent_folder_id}")

    assert db_parent_folder_id is None, (
        f"parent_folder_id zou NULL moeten zijn voor een rootbestand, "
        f"maar is {db_parent_folder_id!r}."
    )
