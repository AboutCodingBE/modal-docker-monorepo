"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

De module bestaat uit twee klassen:
  - FolderAnalysis  — vraagt de agent om de mapinhoud en normaliseert de paden.
  - FileRepository  — slaat de entries op in PostgreSQL, met parent-id resolutie.

M1.01 — Exotische bestandsnamen worden exact bewaard.

Story: "Worden bestandsnamen met accenten, spaties, haakjes, ampersands,
unicode en andere bijzondere tekens correct opgeslagen in de database?
Dus geen autocorrecties, geen encoding-omzettingen, geen afkappingen."

Wat we testen:
  De agent scant tests/testdata/data_M1/ — een map met gecommitte lege bestanden
  waarvan de bestandsnaam het enige testgegeven is. We controleren dat elke naam
  byte-voor-byte teruggevonden wordt in de database.
  Dit bewaakt dat PostgreSQL, SQLAlchemy en de agent Unicode nergens aanpassen.

Teststrategie:
  ECHT: de agent (settings.agent_url) scant de echte testdata-map via /files?path=...
  ECHT: FolderAnalysis verwerkt de agent-response en normaliseert paden.
  ECHT: FileRepository slaat de entries op in PostgreSQL.

  De testdata-bestanden zijn gecommit en gegenereerd via:
      python tests/testdata/create_testdata.py

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Agent bereikbaar op AGENT_URL (zie .env); starten met:
      python agent/agent.py --dev   (alleen de filesystem-bridge, zonder Docker)
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.create_new_archive.file_repository import FileRepository
from app.create_new_archive.folder_analysis import FolderAnalysis


# Map met gecommitte lege bestanden waarvan de naam het testgegeven is.
# Gegenereerd via tests/testdata/create_testdata.py — dat is de enige
# plaats waar de bestandsnamen gedefinieerd worden. De test leest ze van
# schijf zodat een nieuw fixture-bestand automatisch meegenomen wordt.
DATA_DIR = Path(__file__).parent.parent / "testdata" / "data_M1"


@pytest.mark.asyncio
async def test_exotische_bestandsnamen_worden_exact_bewaard(
    async_db_session,
    requires_agent,   # faalt de test als de agent niet bereikbaar is; geeft agent-URL terug
):
    """Laat de echte agent tests/testdata/data_M1/ scannen en controleert
    dat elke exotische bestandsnaam ongewijzigd in de database staat.
    """
    assert DATA_DIR.is_dir(), (
        f"Testdata-map niet gevonden: {DATA_DIR} — "
        f"draai eerst: python tests/testdata/create_testdata.py\n"
        f"(agent bereikbaar op {requires_agent})"
    )

    archive_id = uuid.uuid4()

    # Maak een archief-rij aan in de database.
    # FileRepository vereist een bestaande archive_id als foreign key.
    # flush() schrijft de rij naar de DB binnen de huidige transactie zonder
    # te committen — de rollback aan het einde van async_db_session ruimt alles op.
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "exotische-namen-test", "root_path": str(DATA_DIR)},
    )
    await async_db_session.flush()

    # FolderAnalysis roept de echte agent aan: GET settings.agent_url/files?path=DATA_DIR
    # De agent scant de map recursief en geeft voor elk bestand de naam,
    # het absolute pad en het relatieve pad terug.
    entries = await FolderAnalysis().analyze(archive_id, str(DATA_DIR))

    # FileRepository slaat alle entries op in PostgreSQL.
    # flush() schrijft naar de DB binnen de transactie — nog geen commit.
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("""
            SELECT name FROM files
            WHERE archive_id = :archive_id AND is_directory = false
        """),
        {"archive_id": str(archive_id)},
    )
    stored_names = {row.name for row in result}

    # Lees de verwachte namen van schijf — create_testdata.py is de enige
    # bron van waarheid. Zo hoef je bij een nieuwe fixture-naam alleen dat
    # script aan te passen; de test pikt het automatisch op.
    expected_names = {f.name for f in DATA_DIR.iterdir() if f.is_file()}

    for name in expected_names:
        assert name in stored_names, f"Naam niet exact bewaard: {name!r}"
