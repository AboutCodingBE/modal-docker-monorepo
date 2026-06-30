"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.08 — Tika-analyse op grote bestanden (10MB+).

Story: "Verwerkt Tika bestanden van 10MB+ zonder timeout of geheugenprobleem?"

Wat we testen:
  Een tekstbestand van exact 10MB wordt aangeboden aan de volledige pipeline
  (agent → Tika → DB). De test slaagt als:
  - de pipeline niet crasht of een timeout gooit
  - content niet NULL is (Tika heeft de tekst geëxtraheerd)
  - word_count significant is (> 10.000 woorden)

  Het fixture-bestand is gegenereerd via create_testdata.py met herhalende
  Nederlandse tekst en wordt mee gecommit.

Teststrategie:
  - ECHT: de agent haalt 10MB bestandsbytes op van schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

Fixture-bestand (backend/tests/testdata/data_M2/):
  - groot_bestand.txt  — 10MB herhalende Nederlandse tekst (create_testdata.py)

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


FIXTURE_DIR   = Path(__file__).parent.parent / "testdata" / "data_M2"
GROOT_BESTAND = FIXTURE_DIR / "groot_bestand.txt"


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
async def test_tika_verwerkt_bestand_van_10mb_plus_zonder_timeout_of_geheugenprobleem(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """10MB tekstbestand: pipeline voltooit zonder crash, content en word_count zijn gevuld."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, GROOT_BESTAND.name, str(GROOT_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT content, word_count, mime_type FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["content"] is not None, (
        "content is NULL — Tika kon het grote bestand niet verwerken"
    )
    assert analyse["word_count"] > 10_000, (
        f"word_count te laag ({analyse['word_count']}): verwacht > 10.000 woorden in een 10MB tekstbestand"
    )
    assert analyse["mime_type"] == "text/plain", (
        f"mime_type: verwacht 'text/plain', kreeg {analyse['mime_type']!r}"
    )
