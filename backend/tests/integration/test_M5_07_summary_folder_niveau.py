"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.07 — Folderniveau-samenvatting: opslag en uitsluiting door aggregatie.

Story: "Wordt een foldersamenvatting (file_id = folder_id) correct opgeslagen,
en sluit get_file_summaries_for_folder() die terecht uit om oneindige recursie
te vermijden?"

Wat we testen:
  In de applicatie wordt een foldersamenvatting opgeslagen met file_id = folder_id.
  get_file_summaries_for_folder() filtert rijen met file_id == folder_id eruit
  (zodat de foldersamenvatting zichzelf niet recursief insluit).

  Opzet:
    map_correspondentie/
      brief_jan.txt  -> summary (file_id = brief_jan_id, parent_folder_id = folder_id)
      brief_feb.txt  -> summary (file_id = brief_feb_id, parent_folder_id = folder_id)
    map_correspondentie zelf -> folder summary (file_id = folder_id)

  Verwacht voor get_file_summaries_for_folder(folder_id):
    - 2 strings (de bestandssamenvattingen)
    - NIET de foldersamenvatting zelf

  Verificaties:
    1. Foldersamenvatting staat in de DB met file_id = folder_id.
    2. get_file_summaries_for_folder() geeft 2 strings terug (geen folder).
    3. De foldersamenvatting-tekst zit NIET in de geretourneerde lijst.

Teststrategie:
  - ECHT: SummaryRepository.persist() + get_file_summaries_for_folder()
    op echte PostgreSQL.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_summaries_for_archive.summary_repository import SummaryRepository

SAMENVATTING_BRIEF_JAN = "Jan Hendrickx schreef over de overdracht van archiefdocumenten."
SAMENVATTING_BRIEF_FEB = "Marie Claes beschrijft de toestand van de collectie in 1953."
SAMENVATTING_MAP = "De map bevat correspondentie over archiefoverdrachten uit 1952-1953."


@pytest.mark.asyncio
async def test_foldersamenvatting_wordt_opgeslagen_met_file_id_gelijk_aan_folder_id(
    committing_db_session,
):
    """persist() met file_id = folder_id slaat de foldersamenvatting op — de
    applicatie gebruikt dit om de samenvatting per map bij te houden."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "summary-test-folder-niveau", "root_path": f"/tmp/summary-test/{archive_id}"},
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
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'SUMMARY', 'llama3.2', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    # Sla foldersamenvatting op: file_id = folder_id (conventie uit create_summaries_for_archive.py)
    await SummaryRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=folder_id,
        result=SAMENVATTING_MAP,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT file_id, result FROM summary WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(folder_id), "aid": str(analysis_id)},
    )
    db_rij = rij.mappings().one_or_none()

    print(f"\n[M5.07] Foldersamenvatting in DB: {db_rij}")

    assert db_rij is not None, (
        "Geen summary-rij gevonden met file_id = folder_id na persist() — "
        "foldersamenvatting werd niet opgeslagen."
    )
    assert db_rij["result"] == SAMENVATTING_MAP


@pytest.mark.asyncio
async def test_get_file_summaries_for_folder_sluit_foldersamenvatting_zelf_uit(
    committing_db_session,
):
    """get_file_summaries_for_folder() retourneert bestandssamenvattingen maar
    NIET de foldersamenvatting zelf (file_id != folder_id filter)."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_id_jan = uuid.uuid4()
    file_id_feb = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "summary-test-folder-uitsluiting", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'correspondentie', :fp, 'correspondentie', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/correspondentie"},
    )
    for fid, naam in [(file_id_jan, "brief_jan.txt"), (file_id_feb, "brief_feb.txt")]:
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid),
                "archive_id": str(archive_id),
                "parent_id": str(folder_id),
                "name": naam,
                "fp": f"/tmp/summary-test/{archive_id}/correspondentie/{naam}",
                "rp": f"correspondentie/{naam}",
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

    repo = SummaryRepository(session)
    await repo.persist(
        analysis_id=analysis_id, archive_id=archive_id,
        parent_folder_id=folder_id, file_id=file_id_jan, result=SAMENVATTING_BRIEF_JAN,
    )
    await repo.persist(
        analysis_id=analysis_id, archive_id=archive_id,
        parent_folder_id=folder_id, file_id=file_id_feb, result=SAMENVATTING_BRIEF_FEB,
    )
    # Foldersamenvatting: file_id = folder_id (ZOU moeten worden uitgesloten)
    await repo.persist(
        analysis_id=analysis_id, archive_id=archive_id,
        parent_folder_id=None, file_id=folder_id, result=SAMENVATTING_MAP,
    )
    await session.commit()

    gevonden = await repo.get_file_summaries_for_folder(
        analysis_id=analysis_id,
        folder_id=folder_id,
    )

    print(f"\n[M5.07] 2 bestandssamenvattingen + 1 foldersamenvatting opgeslagen.")
    print(f"[M5.07] get_file_summaries_for_folder() retourneerde: {len(gevonden)} items")
    for s in gevonden:
        print(f"        {s!r}")

    assert len(gevonden) == 2, (
        f"get_file_summaries_for_folder() moet exact 2 bestandssamenvattingen teruggeven "
        f"(foldersamenvatting uitgesloten), maar gaf {len(gevonden)} terug."
    )
    assert SAMENVATTING_BRIEF_JAN in gevonden
    assert SAMENVATTING_BRIEF_FEB in gevonden
    assert SAMENVATTING_MAP not in gevonden, (
        "get_file_summaries_for_folder() geeft de foldersamenvatting zelf terug — "
        "dat zou leiden tot oneindige recursie bij een volgende foldersamenvatting."
    )
