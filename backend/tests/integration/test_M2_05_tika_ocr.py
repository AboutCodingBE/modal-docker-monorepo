"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.05 — OCR-kwaliteit: herkent Tika specifieke tekst uit gescande afbeeldingen?

Story: "Extraheert Tika via Tesseract OCR de juiste tekst uit gescande
       archiefafbeeldingen, ook als OCR een beperkt aantal tikfouten maakt?"

Wat we testen:
  Dat specifieke zinnen uit bekende archiefdocumenten teruggevonden worden
  in de OCR-output, met een tolerantie van maximaal 1 tikfout per zoekopdracht.

  De tikfout-tolerantie dekt reële OCR-imperfecties (bv. 'ult' i.p.v. 'uit')
  zonder slechte extractie door de vingers te zien. Meer dan 1 tikfout per zin
  wijst op een OCR-kwaliteitsprobleem of een gewijzigde Tika/Tesseract-versie.

  Of mime_type correct herkend wordt en of OCR überhaupt actief is,
  wordt getest in M2.04.

Teststrategie:
  - ECHT: de agent haalt bestandsbytes op van de fixture-bestanden op schijf.
  - ECHT: Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - ECHT: DB-INSERT via TikaRepository (echte PostgreSQL-transactie met commit).
  - Cleanup via committing_db_session (expliciete DELETEs op archive_id).

Fixture-bestanden (backend/tests/testdata/data_M2/):
  - Bij_de_buren_metOCRTekst.tif  — krantenartikel "Nodig een artiest uit"
  - st17.jpg                       — aankondiging "BIJ DE BUREN THUIS"

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


def _levenshtein(a: str, b: str) -> int:
    """Minimaal aantal enkelvoudige tekenbewerkingen om a in b te veranderen."""
    m, n = len(a), len(b)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, n + 1):
            temp = dp[j]
            dp[j] = prev if a[i - 1] == b[j - 1] else 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return dp[n]


def _bevat_met_tikfouten(ocr_tekst: str, verwacht: str, max_fouten: int = 1) -> bool:
    """Controleert of verwacht (met max max_fouten tikfouten) voorkomt in ocr_tekst.

    Newlines worden gelijkgesteld aan spaties zodat een zin die over twee
    regels verspreid staat toch als één geheel herkend wordt.
    """
    genormaliseerd = " ".join(ocr_tekst.split())
    zoekterm       = " ".join(verwacht.split())
    n = len(zoekterm)
    for i in range(len(genormaliseerd) - n + 1):
        if _levenshtein(genormaliseerd[i : i + n], zoekterm) <= max_fouten:
            return True
    return False


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
async def test_ocr_herkent_titel_in_tiff(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """TIFF krantenartikel: OCR herkent de titel 'Nodig een artiest uit' met ≤1 tikfout.

    De titel staat over twee regels in het krantenartikel. OCR produceert
    'Nodig een\\nartiest ult' — 1 tikfout ('ult' i.p.v. 'uit'), binnen tolerantie.
    """
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, TIFF_BESTAND.name, str(TIFF_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert _bevat_met_tikfouten(analyse["content"], "Nodig een artiest uit"), (
        f"OCR-tekst bevat 'Nodig een artiest uit' niet met ≤1 tikfout: "
        f"{analyse['content'][:300]!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )


@pytest.mark.asyncio
async def test_ocr_herkent_datum_in_jpeg(
    committing_db_session,
    requires_agent,
    requires_tika,
):
    """JPEG aankondiging: OCR herkent de datumvermelding '21 MAART EN 3 APRIL' correct.

    De koptekst 'BIJ DE BUREN THUIS' bevat een IJ-digraaf-fout in de OCR-output
    ('BU' i.p.v. 'BIJ', edit-afstand 2). De datumvermelding wordt wél foutloos
    herkend en is daardoor de betrouwbaardere ankertekst voor deze test.
    """
    session, cleanup_ids = committing_db_session
    archive_id, file_id, task_id = await _setup_archive_en_bestand(
        session, JPEG_BESTAND.name, str(JPEG_BESTAND).replace("\\", "/"),
    )
    cleanup_ids.append(archive_id)

    await PerformTikaAnalysis(session).execute(archive_id, task_id)

    rij = await session.execute(
        text("SELECT content, language FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    analyse = rij.mappings().one()

    assert _bevat_met_tikfouten(analyse["content"], "21 MAART EN 3 APRIL"), (
        f"OCR-tekst bevat '21 MAART EN 3 APRIL' niet met ≤1 tikfout: "
        f"{analyse['content'][:300]!r}"
    )
    assert analyse["language"] == "nl", (
        f"language: verwacht 'nl', kreeg {analyse['language']!r}"
    )
