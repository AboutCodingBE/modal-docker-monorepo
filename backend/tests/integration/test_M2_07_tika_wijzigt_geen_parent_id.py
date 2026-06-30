"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.06 — TikaRepository schrijft uitsluitend naar tika_analyses, niet naar files.

Story: "Blijft parent_id van een bestand ongewijzigd na een Tika-stap?"

Wat we testen:
  PerformTikaAnalysis schrijft zijn resultaten naar tika_analyses. De files-tabel
  mag niet worden aangeraakt — parent_id, id en alle andere velden blijven gelijk.
  Dit test de isolatie tussen de twee tabellen op DB-niveau.

Teststrategie:
  ECHT: FileRepository.persist_all() en TikaRepository.persist() schrijven naar
        echte PostgreSQL.
  GEEN Tika-server nodig: TikaRepository.persist() wordt direct aangeroepen met
        vaste waarden — er wordt geen bestand naar Tika gestuurd.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.create_new_archive.file_repository import FileRepository
from app.perform_tika_analysis.tika_repository import TikaRepository
from app.shared.models import Archive

import uuid


async def _make_archive(session: AsyncSession, name: str, root_path: str) -> Archive:
    archive = Archive(
        id=uuid.uuid4(),
        name=name,
        root_path=root_path,
        analysis_status="pending",
        file_count=0,
        directory_count=0,
        total_size_bytes=0,
    )
    session.add(archive)
    await session.flush()
    return archive


@pytest.mark.asyncio
async def test_tika_stap_breekt_parent_id_niet(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Na een Tika-stap op een bestand in een submap moet parent_id ongewijzigd blijven.

    Schijfstructuur:
      tmp_path/
        Foto-archief/       ← map-record (parent_id = NULL)
          foto1.jpg         ← bestand met parent_id = id van Foto-archief

    TikaRepository.persist() schrijft alleen naar tika_analyses, niet naar files.
    We roepen het direct aan om te verifiëren dat de files-tabel onaangetast blijft.
    """
    (tmp_path / "Foto-archief").mkdir()
    (tmp_path / "Foto-archief" / "foto1.jpg").touch()

    archive = await _make_archive(async_db_session, "test-tika-parent-id", str(tmp_path))
    now = datetime.now(timezone.utc)

    entries = [
        {
            "archive_id": archive.id,
            "_parent_path": None,
            "name": "Foto-archief",
            "full_path": str(tmp_path / "Foto-archief").replace("\\", "/"),
            "relative_path": "Foto-archief",
            "is_directory": True,
            "extension": None, "size_bytes": None, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
        {
            "archive_id": archive.id,
            "_parent_path": str(tmp_path / "Foto-archief").replace("\\", "/"),
            "name": "foto1.jpg",
            "full_path": str(tmp_path / "Foto-archief" / "foto1.jpg").replace("\\", "/"),
            "relative_path": "Foto-archief/foto1.jpg",
            "is_directory": False,
            "extension": "jpg", "size_bytes": 0, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
    ]

    await FileRepository(async_db_session).persist_all(entries)

    result_voor = await async_db_session.execute(
        text("SELECT id, name, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    foto_voor = next((r for r in result_voor.fetchall() if r.name == "foto1.jpg"), None)
    assert foto_voor is not None, "'foto1.jpg' niet gevonden vóór Tika-run"

    await TikaRepository(async_db_session).persist(
        file_id=str(foto_voor.id),
        mime_type="image/jpeg",
        tika_parser="org.apache.tika.parser.image.ImageParser",
        content=None,
        language=None,
        word_count=0,
        author=None,
        content_created_at=None,
    )

    result_na = await async_db_session.execute(
        text("SELECT id, parent_id FROM files WHERE archive_id = :aid AND name = 'foto1.jpg'"),
        {"aid": str(archive.id)},
    )
    foto_na = result_na.fetchone()
    assert foto_na is not None, "'foto1.jpg' niet meer gevonden ná Tika-run"

    assert foto_na.parent_id == foto_voor.parent_id, (
        f"parent_id veranderd na Tika-run!\n"
        f"  vóór: {foto_voor.parent_id}\n"
        f"  na:   {foto_na.parent_id}"
    )
    assert foto_na.id == foto_voor.id, (
        f"Record-id veranderd na Tika-run — nieuw record aangemaakt!\n"
        f"  vóór: {foto_voor.id}\n"
        f"  na:   {foto_na.id}"
    )
