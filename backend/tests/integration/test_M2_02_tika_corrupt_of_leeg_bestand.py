"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.02 — Tika-analyse op een corrupt of leeg bestand.

Story: "Wat doet Tika met een corrupt of leeg bestand — crasht de pipeline
of gaat die verder?"

Wat we testen:
  Twee scenario's die de robuustheid van de pipeline bewaken:

  1. Corrupt bestand: een PDF-header gevolgd door ongeldige bytes.
     Tika probeert het te parsen maar slaagt er niet volledig in.
     De pipeline mag niet crashen — de taak eindigt als 'completed',
     ook als het bestand als 'failed' wordt geteld.

  2. Leeg bestand: een bestand van 0 bytes (geen inhoud).
     Tika retourneert een lege content. De pipeline slaat het op
     met content=NULL en word_count=0 — geen skip, geen crash.

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via expliciete DELETE-statements na de test (zie committing_db_session
    in conftest.py) — de code roept intern commit() aan, dus rollback werkt niet.

Fixture-bestanden (backend/tests/testdata/data_M2/):
  - corrupt_document.pdf  — %PDF-header + ongeldige bytes
  - leeg_bestand.txt      — 0 bytes
  Aangemaakt via backend/tests/testdata/create_testdata.py.

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
CORRUPT_PDF  = FIXTURE_DIR / "corrupt_document.pdf"
LEEG_BESTAND = FIXTURE_DIR / "leeg_bestand.txt"


async def _setup_archive_en_bestand(
    session: AsyncSession,
    bestandsnaam: str,
    full_path: str,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Maakt de minimale DB-rijen aan die PerformTikaAnalysis.execute() verwacht.

    Geeft (archive_id, file_id, task_id) terug zodat de test er asserts op kan doen.
    De aanroeper is verantwoordelijk voor session.commit() na deze functie.
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
async def test_tika_pipeline_crasht_niet_op_corrupt_bestand(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Corrupt PDF-bestand: de pipeline crasht niet en de taak eindigt als 'completed'.

    Een crash zou zich uiten als task.status = 'failed' (de outer except-handler
    in perform_tika_analysis.py roept fail_task aan). 'completed' bewijst dat
    de pipeline het bestand heeft overgeslagen zonder zichzelf te breken.
    """
    session, cleanup_ids = committing_db_session
    archive_id, _, task_id = await _setup_archive_en_bestand(
        session,
        "corrupt_document.pdf",
        str(CORRUPT_PDF).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    taak = await session.execute(
        text("SELECT status FROM analysis_tasks WHERE id = :id"),
        {"id": str(task_id)},
    )
    taak_status = taak.scalar_one()

    assert taak_status == "completed", (
        f"Pipeline-status na corrupt bestand: verwacht 'completed', kreeg {taak_status!r}.\n"
        f"'failed' betekent dat de outer except-handler getriggerd werd — de pipeline crashte."
    )


@pytest.mark.asyncio
async def test_tika_pipeline_crasht_niet_op_leeg_bestand(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """Leeg bestand (0 bytes): de pipeline slaat het op met content=NULL en word_count=0.

    Een leeg bestand is geen mislukte extractie — Tika heeft het correct verwerkt
    en gevonden dat er geen tekst is. Het bestand hoort een tika_analyses-rij te
    krijgen met content=NULL en word_count=0, en mag niet als 'failed' worden geteld.
    """
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session,
        "leeg_bestand.txt",
        str(LEEG_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT content, word_count FROM tika_analyses WHERE file_id = :file_id"),
        {"file_id": str(file_id)},
    )
    analyse = rij.mappings().one_or_none()

    assert analyse is not None, (
        "Geen tika_analyses-rij gevonden voor het lege bestand — "
        "een leeg bestand is geen extractiefout en mag niet als 'failed' worden geteld"
    )
    assert analyse["content"] is None, (
        f"content moet NULL zijn voor een leeg bestand, kreeg: {analyse['content']!r}"
    )
    assert analyse["word_count"] == 0, (
        f"word_count moet 0 zijn voor een leeg bestand, kreeg: {analyse['word_count']}"
    )
