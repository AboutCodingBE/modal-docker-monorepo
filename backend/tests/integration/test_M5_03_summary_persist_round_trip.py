"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.03 — SummaryRepository persisteert de samenvatting correct in de database.

Story: "Wordt de gegenereerde samenvatting exact opgeslagen en teruggelezen?"

Wat we testen:
  SummaryRepository.persist() slaat een samenvattingstekst op in de summary-tabel.
  We verifiëren dat de tekst byte-voor-byte identiek terugkomt uit de database
  — inclusief speciale tekens, accenten en witruimte.

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

TESTSAMENVATTING = (
    "Jan Hendrickx schreef in april 1952 een brief over de overdracht "
    "van archiefstukken aan het Gemeentearchief Gent. "
    "De brief bevat verwijzingen naar Marie Claes en Amsab-ISG."
)


@pytest.mark.asyncio
async def test_summary_persist_bewaart_tekst_exact_in_db(committing_db_session):
    """SummaryRepository.persist() slaat de samenvattingstekst exact op — geen
    truncatie, encoding-verlies of andere transformatie."""
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
        {"id": str(archive_id), "name": "summary-test-round-trip", "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief.txt",
            "full_path": f"/tmp/summary-test/{archive_id}/brief.txt",
            "relative_path": "brief.txt",
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
        parent_folder_id=None,
        file_id=file_id,
        result=TESTSAMENVATTING,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT result FROM summary WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_result = rij.scalar()

    print(f"\n[M5.03] Opgeslagen: {TESTSAMENVATTING!r}")
    print(f"[M5.03] Teruggelezen: {db_result!r}")

    assert db_result == TESTSAMENVATTING, (
        f"DB-waarde verschilt van de ingevoerde tekst.\n"
        f"Verwacht: {TESTSAMENVATTING!r}\n"
        f"Gekregen: {db_result!r}"
    )
