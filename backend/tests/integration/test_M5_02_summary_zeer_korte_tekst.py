"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.02 — Summary-generatie op een zeer korte tekst.

Story: "Wat doet de summary-engine met een tekst van slechts 1-2 zinnen?"

Wat we testen:
  De summary-pipeline gebruikt de eerste 1000 tekens van de tika-content.
  Voor een document van slechts 1-2 zinnen is de input dus erg kort.
  We verifiëren dat:
    1. generate() niet crasht op een korte tekst.
    2. Een niet-lege samenvatting wordt teruggestuurd.
    3. Het resultaat correct wordt opgeslagen in de database.

Teststrategie:
  - ECHT: generate() roept de echte Ollama-instantie aan.
  - ECHT: SummaryRepository.persist() schrijft naar echte PostgreSQL.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar en Ollama bereikbaar (docker compose up)
  - Model SUMMARY_MODEL beschikbaar in Ollama (ollama pull <model>)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_summaries_for_archive.ollama_client import generate
from app.create_summaries_for_archive.summary_repository import SummaryRepository

# Pas aan als het project een ander Ollama-model gebruikt.
SUMMARY_MODEL = "gemma2:2b"

KORTE_TEKST = "Jan Hendrickx schreef op 12 maart 1923 een brief aan Marie Claes."


@pytest.mark.asyncio
async def test_summary_engine_met_tekst_van_een_of_twee_zinnen(
    committing_db_session,
):
    """generate() op een korte tekst geeft een niet-lege samenvatting terug en
    die wordt correct opgeslagen in de database."""
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
        {"id": str(archive_id), "name": "summary-test-korte-tekst", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "korte_brief.txt",
            "full_path": f"/tmp/summary-test/{archive_id}/korte_brief.txt",
            "relative_path": "korte_brief.txt",
        },
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'SUMMARY', :model, 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id), "model": SUMMARY_MODEL},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    prompt = (
        "Geef een antwoord in een korte zin. Geef GEEN verdere toelichting bij je antwoord.\n\n"
        f"Vat deze tekst samen in het Nederlands:\n\n{KORTE_TEKST}"
    )
    samenvatting = await generate(SUMMARY_MODEL, prompt)

    print(f"\n[M5.02] Korte tekst ({len(KORTE_TEKST)} tekens):")
    print(f"        Input:      {KORTE_TEKST!r}")
    print(f"        Samenvatting: {samenvatting!r}")

    assert samenvatting and len(samenvatting.strip()) > 0, (
        "generate() gaf een lege samenvatting terug voor een korte tekst."
    )

    await SummaryRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        result=samenvatting,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT result FROM summary WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_result = rij.scalar()

    assert db_result == samenvatting, (
        f"DB-waarde verschilt van de gegenereerde samenvatting: {db_result!r} != {samenvatting!r}"
    )
