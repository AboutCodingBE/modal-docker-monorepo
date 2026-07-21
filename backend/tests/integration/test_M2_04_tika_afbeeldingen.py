"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.04 — Tika-analyse op afbeeldingen: mime_type-herkenning en OCR-activering.

Story: "Herkent Tika het mime_type van gescande archiefafbeeldingen en
       activeert het automatisch OCR?"

Wat we testen:
  - mime_type wordt correct gedetecteerd (image/tiff, image/jpeg)
  - content is niet NULL: de Tika-image (apache/tika:latest-full) bevat
    Tesseract OCR en extraheert automatisch tekst uit afbeeldingen met
    gedrukte tekst

  De kwaliteit van de OCR-output (welke woorden correct worden herkend)
  wordt apart getest in M2.05.

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

Fixture-bestanden (backend/tests/testdata/data_M2/):
  - Bij_de_buren_metOCRTekst.tif  — krantenartikel, gedrukte Nederlandse tekst
  - st17.jpg                       — aankondiging theater-bij-jou-thuis project

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
TIFF_BESTAND = FIXTURE_DIR / "Bij_de_buren_metOCRTekst.tif"
JPEG_BESTAND = FIXTURE_DIR / "st17.jpg"


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
async def test_tika_herkent_mime_type_tiff(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """TIFF-bestand: mime_type correct gedetecteerd en OCR geactiveerd (content niet NULL)."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, TIFF_BESTAND.name, str(TIFF_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "image/tiff", (
        f"mime_type: verwacht 'image/tiff', kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None, (
        "content is NULL — Tika OCR heeft geen tekst herkend in het TIFF-bestand"
    )


@pytest.mark.asyncio
async def test_tika_herkent_mime_type_jpeg(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """JPEG-bestand: mime_type correct gedetecteerd en OCR geactiveerd (content niet NULL)."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, JPEG_BESTAND.name, str(JPEG_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT mime_type, content FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert analyse["mime_type"] == "image/jpeg", (
        f"mime_type: verwacht 'image/jpeg', kreeg {analyse['mime_type']!r}"
    )
    assert analyse["content"] is not None, (
        "content is NULL — Tika OCR heeft geen tekst herkend in het JPEG-bestand"
    )
