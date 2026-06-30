"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.06 — get_file_summaries_for_folder(): aggregatie van bestandssamenvattingen.

Story: "Geeft get_file_summaries_for_folder() alle samenvattingen terug voor
bestanden in een gegeven map — als basis voor de foldersamenvatting?"

Wat we testen:
  SummaryRepository.get_file_summaries_for_folder() retourneert de result-strings
  van alle bestanden waarvan parent_folder_id de opgegeven folder is.

  Opzet:
    map_correspondentie/
      brief_jan.txt    -> "Jan Hendrickx schreef over overdracht."
      brief_feb.txt    -> "Marie Claes vermeldt archiefstukken."
      brief_mar.txt    -> "Pieter Janssens rapporteert over Gent."

  Verwacht: 3 strings terugkrijgen, één per bestand.

  Geen Ollama nodig: we gebruiken vaste teststrings als samenvattingen.

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

SAMENVATTINGEN = [
    "Jan Hendrickx schreef in april 1952 over de overdracht van archiefstukken.",
    "Marie Claes vermeldt in haar brief de collectie van Amsab-ISG.",
    "Pieter Janssens rapporteert over de toestand van het Gemeentearchief Gent.",
]


@pytest.mark.asyncio
async def test_get_file_summaries_for_folder_geeft_alle_bestandssamenvattingen_terug(
    committing_db_session,
):
    """get_file_summaries_for_folder() retourneert exact de persisted result-strings
    voor alle bestanden in de opgegeven map."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "summary-test-aggregatie", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'correspondentie', :fp, 'correspondentie', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/correspondentie"},
    )
    for i, fid in enumerate(file_ids):
        naam = f"brief_{i + 1}.txt"
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
    for fid, samenvatting in zip(file_ids, SAMENVATTINGEN):
        await repo.persist(
            analysis_id=analysis_id,
            archive_id=archive_id,
            parent_folder_id=folder_id,
            file_id=fid,
            result=samenvatting,
        )
    await session.commit()

    gevonden = await repo.get_file_summaries_for_folder(
        analysis_id=analysis_id,
        folder_id=folder_id,
    )

    print(f"\n[M5.06] Verwacht {len(SAMENVATTINGEN)} samenvattingen, "
          f"gevonden: {len(gevonden)}")
    for i, s in enumerate(gevonden):
        print(f"        [{i}] {s!r}")

    assert len(gevonden) == len(SAMENVATTINGEN), (
        f"get_file_summaries_for_folder() retourneerde {len(gevonden)} strings, "
        f"verwacht {len(SAMENVATTINGEN)}. "
        "Controleer of persist() parent_folder_id correct opslaat."
    )

    for verwachte in SAMENVATTINGEN:
        assert verwachte in gevonden, (
            f"Samenvatting niet gevonden in resultaat: {verwachte!r}"
        )


@pytest.mark.asyncio
async def test_get_file_summaries_for_folder_sluit_ander_archief_uit(
    committing_db_session,
):
    """Samenvattingen van andere analyses worden niet gemengd — analysis_id-isolatie."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_id_a = uuid.uuid4()
    file_id_b = uuid.uuid4()
    analysis_id_correct = uuid.uuid4()
    analysis_id_anders = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "summary-test-isolatie", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'map1', :fp, 'map1', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/map1"},
    )
    for fid, naam in [(file_id_a, "brief_a.txt"), (file_id_b, "brief_b.txt")]:
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
                "fp": f"/tmp/summary-test/{archive_id}/map1/{naam}",
                "rp": f"map1/{naam}",
            },
        )
    for aid in [analysis_id_correct, analysis_id_anders]:
        await session.execute(
            text("""
                INSERT INTO archive_analysis (id, archive_id, type, model, status)
                VALUES (:id, :archive_id, 'SUMMARY', 'llama3.2', 'STARTED')
            """),
            {"id": str(aid), "archive_id": str(archive_id)},
        )
    await session.commit()
    cleanup_ids.append(archive_id)

    repo = SummaryRepository(session)
    await repo.persist(
        analysis_id=analysis_id_correct,
        archive_id=archive_id,
        parent_folder_id=folder_id,
        file_id=file_id_a,
        result="Correcte samenvatting van brief A.",
    )
    await repo.persist(
        analysis_id=analysis_id_anders,
        archive_id=archive_id,
        parent_folder_id=folder_id,
        file_id=file_id_b,
        result="Samenvatting van een andere analyse — mag niet teruggegeven worden.",
    )
    await session.commit()

    gevonden = await repo.get_file_summaries_for_folder(
        analysis_id=analysis_id_correct,
        folder_id=folder_id,
    )

    print(f"\n[M5.06] Isolatietest: gevonden samenvattingen voor correcte analysis_id: {gevonden}")

    assert len(gevonden) == 1, (
        f"get_file_summaries_for_folder() mengt samenvattingen van verschillende analyses: "
        f"verwacht 1, gekregen {len(gevonden)}."
    )
    assert "Correcte samenvatting van brief A." in gevonden
