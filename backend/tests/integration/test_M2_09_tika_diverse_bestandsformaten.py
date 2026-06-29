"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.08 — Tika-analyse op diverse en minder gangbare bestandsformaten.

Story: "Kan Tika omgaan met formaten die buiten de standaard Office/PDF-reeks vallen?"

NOOT: we hebben ook audio en videoformaten om te testen!

Wat we testen:
  Elk bestandsformaat dat niet in M2.01-M2.07 past krijgt hier een eigen test.
  Het bestand hoort thuis in tests/testdata/data_M2/ en wordt mee gecommit.

  Voeg een nieuw formaat toe door:
    1. Het bestand toe te voegen aan tests/testdata/data_M2/
    2. Een nieuwe @pytest.mark.asyncio testfunctie toe te voegen aan dit bestand

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

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


FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M2"
HTM_BESTAND = FIXTURE_DIR / "lied_de_kindereter.htm"


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
async def test_tika_extraheert_tekst_uit_htm(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """HTML-bestand (.htm): tekst en mime_type worden correct geëxtraheerd.

    HTML heeft doorgaans geen author of created-metadata — die kolommen
    blijven NULL, wat het verwachte gedrag is.
    """
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, HTM_BESTAND.name, str(HTM_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "text/html", (
        f"mime_type: verwacht 'text/html', kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None and "Joep Conjaerts" in analyse["content"], (
        f"content bevat niet de verwachte tekst 'Joep Conjaerts': {analyse['content']!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )
