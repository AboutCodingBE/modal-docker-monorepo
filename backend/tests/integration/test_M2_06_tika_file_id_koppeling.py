"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.06 — Koppeling van het Tika-resultaat aan het juiste file-record.

Story: "Wordt het Tika-resultaat altijd gekoppeld aan het correcte
       file-record, ook bij meerdere bestanden in één archief?"

Wat we testen:
  Eén archief met twee bestanden van een verschillend formaat (PDF en DOCX)
  wordt in één execute()-aanroep verwerkt. Daarna controleren we dat elke
  tika_analyses-rij de mime_type heeft die overeenkomt met het bestand waarnaar
  de file_id verwijst.

  Als de file_id-koppeling onjuist zou zijn (rijen verwisseld of dubbel
  opgeslagen), zou de mime_type niet overeenkomen met het verwachte formaat
  en falen de assertions.

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

Fixture-bestanden (backend/tests/testdata/data_M2/):
  - normaal_document.pdf   — mime_type: application/pdf
  - normaal_document.docx  — mime_type: application/vnd.openxmlformats-...wordprocessingml.document

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Agent bereikbaar op AGENT_URL (start met: python agent/agent.py --dev)
  - Apache Tika bereikbaar op TIKA_URL (start met: docker compose up)
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.perform_tika_analysis.perform_tika_analysis import PerformTikaAnalysis


FIXTURE_DIR  = Path(__file__).parent.parent / "testdata" / "data_M2"
PDF_BESTAND  = FIXTURE_DIR / "normaal_document.pdf"
DOCX_BESTAND = FIXTURE_DIR / "normaal_document.docx"


@pytest.mark.asyncio
async def test_tika_resultaat_gekoppeld_aan_correct_file_record_bij_meerdere_bestanden(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Twee bestanden in één archief: elke tika_analyses-rij is gekoppeld aan het juiste file-record.

    Bewijs: de mime_type in elke rij moet overeenkomen met het bestandsformaat
    waarnaar de file_id verwijst. Verwisseling zou onmiddellijk opvallen.
    """
    session, cleanup_ids = committing_db_session

    archive_id   = uuid.uuid4()
    pdf_file_id  = uuid.uuid4()
    docx_file_id = uuid.uuid4()
    task_id      = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, 'tika-test-koppeling', :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "root_path": str(FIXTURE_DIR)},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id":            str(pdf_file_id),
            "archive_id":    str(archive_id),
            "name":          PDF_BESTAND.name,
            "full_path":     str(PDF_BESTAND).replace("\\", "/"),
            "relative_path": PDF_BESTAND.name,
        },
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id":            str(docx_file_id),
            "archive_id":    str(archive_id),
            "name":          DOCX_BESTAND.name,
            "full_path":     str(DOCX_BESTAND).replace("\\", "/"),
            "relative_path": DOCX_BESTAND.name,
        },
    )
    await session.execute(
        text("""
            INSERT INTO analysis_tasks (id, archive_id, status, task_type,
                                        total_files, processed, failed_count)
            VALUES (:id, :archive_id, 'pending', 'tika', 0, 0, 0)
        """),
        {"id": str(task_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    pdf_rij = await session.execute(
        text("SELECT mime_type FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(pdf_file_id)},
    )
    pdf_analyse = pdf_rij.mappings().one()

    docx_rij = await session.execute(
        text("SELECT mime_type FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(docx_file_id)},
    )
    docx_analyse = docx_rij.mappings().one()

    assert pdf_analyse["mime_type"] == "application/pdf", (
        f"PDF file_id gekoppeld aan verkeerde mime_type: {pdf_analyse['mime_type']!r}"
    )
    assert docx_analyse["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document", (
        f"DOCX file_id gekoppeld aan verkeerde mime_type: {docx_analyse['mime_type']!r}"
    )
