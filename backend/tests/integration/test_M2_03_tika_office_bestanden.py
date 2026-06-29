"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.03 — Tika-analyse op Office-bestanden: DOC, DOCX en XLS.

Story: "Extraheert Tika tekst correct uit gangbare Office-formaten?"

Wat we testen:
  Drie veelvoorkomende Office-formaten worden aangeboden aan Tika. We controleren
  per formaat dat mime_type correct wordt gedetecteerd, tekstinhoud daadwerkelijk
  wordt geëxtraheerd en taaldetectie slaagt.

  DOC en XLS zijn echte archiefdocumenten met Nederlandse tekst.
  DOCX is gegenereerd via create_testdata.py.

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

Fixture-bestanden (backend/tests/testdata/data_M2/):
  - UITNODIGING_via_post.doc               — echt archiefdocument, Word 97-2003
  - normaal_document.docx                  — gegenereerd via create_testdata.py
  - Speellijst_lanceerv_huiskamerv_2007.xls — echt archiefdocument, Excel 97-2003

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Agent bereikbaar op AGENT_URL (start met: python agent/agent.py --dev)
  - Apache Tika bereikbaar op TIKA_URL (start met: docker compose up)
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.perform_tika_analysis.perform_tika_analysis import PerformTikaAnalysis


FIXTURE_DIR  = Path(__file__).parent.parent / "testdata" / "data_M2"
DOC_BESTAND  = FIXTURE_DIR / "UITNODIGING_via_post.doc"
DOCX_BESTAND = FIXTURE_DIR / "normaal_document.docx"
XLS_BESTAND  = FIXTURE_DIR / "Speellijst_lanceerv_huiskamerv_2007.xls"


async def _setup_archive_en_bestand(
    session: AsyncSession,
    bestandsnaam: str,
    full_path: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Maakt de minimale DB-rijen aan die PerformTikaAnalysis.execute() verwacht.

    Geeft (archive_id, file_id, task_id) terug.
    De aanroeper voegt archive_id toe aan cleanup_ids voor opruiming na de test.
    """
    archive_id = uuid.uuid4()
    file_id    = uuid.uuid4()
    task_id    = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": f"tika-test-{bestandsnaam}", "root_path": str(FIXTURE_DIR)},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id":            str(file_id),
            "archive_id":    str(archive_id),
            "name":          bestandsnaam,
            "full_path":     full_path,
            "relative_path": bestandsnaam,
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
    return archive_id, file_id, task_id


@pytest.mark.asyncio
async def test_tika_extraheert_tekst_uit_doc(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Word 97-2003 (.doc): tekst, mime_type en taal worden correct geëxtraheerd."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, DOC_BESTAND.name, str(DOC_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "application/msword", (
        f"mime_type: verwacht 'application/msword', kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None and "UITNODIGING" in analyse["content"], (
        f"content bevat niet de verwachte tekst 'UITNODIGING': {analyse['content']!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )


@pytest.mark.asyncio
async def test_tika_extraheert_tekst_uit_docx(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Word 2007+ (.docx): tekst, mime_type en taal worden correct geëxtraheerd."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, DOCX_BESTAND.name, str(DOCX_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document", (
        f"mime_type: verwacht DOCX mime_type, kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None and "gemeentearchief" in analyse["content"], (
        f"content bevat niet de verwachte tekst 'gemeentearchief': {analyse['content']!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )


@pytest.mark.asyncio
async def test_tika_extraheert_tekst_uit_xls(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Excel 97-2003 (.xls): tekst, mime_type en taal worden correct geëxtraheerd."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, XLS_BESTAND.name, str(XLS_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "application/vnd.ms-excel", (
        f"mime_type: verwacht 'application/vnd.ms-excel', kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None and "Bij de buren" in analyse["content"], (
        f"content bevat niet de verwachte tekst 'Bij de buren': {analyse['content']!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )
