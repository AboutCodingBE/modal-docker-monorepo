"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.03 — Lege en binaire bestanden worden correct opgeslagen.

Story: "Wat gebeurt er met bestanden van 0 bytes of met binaire extensies zoals
.exe, .db, Thumbs.db?"

Wat we testen:
  Het systeem filtert geen bestanden op basis van grootte of extensie bij het
  inladen van een archief. Elk bestand dat de agent rapporteert wordt opgeslagen,
  inclusief lege bestanden (0 bytes) en bekende binaire formaten.

  Twee aparte tests zodat een falend scenario de andere niet verbergt.

Teststrategie:
  ECHT: de agent scant een tijdelijke map met echte bestanden op schijf.
  ECHT: FileRepository slaat de entries op in PostgreSQL.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Agent bereikbaar op AGENT_URL (zie .env); starten met:
      python agent/agent.py --dev   (alleen de filesystem-bridge, zonder Docker)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_new_archive.file_repository import FileRepository
from app.create_new_archive.folder_analysis import FolderAnalysis


async def _scan_en_sla_op(async_db_session, tmp_path) -> dict:
    """Scant tmp_path via de echte agent en geeft de opgeslagen rijen terug als dict
    {bestandsnaam: {name, size_bytes, ...}}.

    Hulpfunctie om herhaling te vermijden — het opzetten van een archief en het
    aanroepen van FolderAnalysis + FileRepository is identiek voor beide tests.
    """
    archive_id = uuid.uuid4()

    # flush() schrijft binnen de huidige transactie zonder te committen —
    # de rollback in async_db_session ruimt alles op na de test.
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "lege-binaire-test", "root_path": str(tmp_path)},
    )
    await async_db_session.flush()

    entries = await FolderAnalysis().analyze(archive_id, str(tmp_path))
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("""
            SELECT name, size_bytes FROM files
            WHERE archive_id = :archive_id AND is_directory = false
        """),
        {"archive_id": str(archive_id)},
    )
    return {row.name: dict(row._mapping) for row in result}


@pytest.mark.asyncio
async def test_leeg_bestand_wordt_correct_opgeslagen(
    async_db_session,
    requires_agent,   # faalt de test als de agent niet bereikbaar is; geeft agent-URL terug
    tmp_path,
):
    """Controleert dat een bestand van 0 bytes correct wordt opgeslagen met size_bytes=0."""
    agent_url = requires_agent  # bevestigt dat de agent bereikbaar is op dit adres
    # Path.touch() maakt een leeg bestand aan — 0 bytes, geen inhoud.
    (tmp_path / "leeg_bestand.txt").touch()

    rows = await _scan_en_sla_op(async_db_session, tmp_path)

    assert "leeg_bestand.txt" in rows, (
        "Leeg bestand niet gevonden in de database — "
        "het systeem mag niet filteren op bestandsgrootte bij het inladen"
    )
    assert rows["leeg_bestand.txt"]["size_bytes"] == 0, (
        f"size_bytes: verwacht 0 voor een leeg bestand, "
        f"kreeg {rows['leeg_bestand.txt']['size_bytes']!r}"
    )


@pytest.mark.asyncio
async def test_binaire_bestanden_worden_correct_opgeslagen(
    async_db_session,
    requires_agent,   # faalt de test als de agent niet bereikbaar is; geeft agent-URL terug
    tmp_path,
):
    """Controleert dat bestanden met binaire extensies (.exe, .db, Thumbs.db) worden
    opgeslagen zonder filtering — het systeem mag bij M1 niet filteren op extensie.
    """
    agent_url = requires_agent  # bevestigt dat de agent bereikbaar is op dit adres
    # Schrijf de typische magic bytes zodat ook de bestandsgrootte > 0 is.
    BINARY_FILES = {
        "programma.exe": b"\x4d\x5a",           # MZ-header (Windows executable)
        "database.db":   b"SQLite format 3\x00", # SQLite magic bytes
        "Thumbs.db":     b"\xd0\xcf\x11\xe0",   # OLE2 compound document (Windows thumbnails)
    }
    for naam, inhoud in BINARY_FILES.items():
        (tmp_path / naam).write_bytes(inhoud)

    rows = await _scan_en_sla_op(async_db_session, tmp_path)

    for naam in BINARY_FILES:
        assert naam in rows, (
            f"Binair bestand niet gevonden in de database: {naam!r} — "
            f"het systeem mag bij M1 niet filteren op extensie. "
            f"Gevonden: {sorted(rows.keys())}"
        )
        assert rows[naam]["size_bytes"] > 0, (
            f"size_bytes van '{naam}' moet > 0 zijn, "
            f"kreeg {rows[naam]['size_bytes']!r}"
        )
