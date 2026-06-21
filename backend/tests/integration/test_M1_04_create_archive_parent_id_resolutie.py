"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.04 — parent_id-resolutie: elk bestand krijgt de juiste parent_id.

Story: "Krijgt elk bestand in een submap de juiste parent_id die verwijst naar
de map erboven? En werkt dat ook op Windows, waar paden backslashes bevatten?"

Wat we testen:
  FileRepository.persist_all() bouwt intern een path_to_id-opzoektabel om
  _parent_path te vertalen naar de UUID van de bovenliggende map. Dit werkt
  alleen als _parent_path en full_path van de map exact dezelfde string zijn
  — inclusief path-separator. Op Windows stuurt de agent backslashes; die
  moeten eerst genormaliseerd worden naar forward slashes.

  De tests bouwen de entries-lijst zelf (geen agent-aanroep) zodat we de
  path_to_id-logica in isolatie kunnen testen.

  test_01  Sanity: lege map → 0 rijen, geen crash
  test_02  Bestand in root → parent_id IS NULL
  test_03  Bestand in submap → parent_id == id van die submap
  test_04  Twee niveaus diep: keten van parent_ids
  test_05  Tika-stap breekt parent_id niet
  test_06  Windows backslash-paden in persist_all
  test_07  Genormaliseerde agent-paden (backslash → forward slash)

Teststrategie:
  ECHT: FileRepository.persist_all() schrijft naar echte PostgreSQL.
  GEEN agent nodig: entries worden direct opgebouwd vanuit schijf of hardcoded.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.create_new_archive.file_repository import FileRepository
from app.shared.models import Archive


# ---------------------------------------------------------------------------
# Hulpfuncties
# ---------------------------------------------------------------------------

def _build_tree(base: Path, structure: dict) -> None:
    """Maak een echte bestandsstructuur op schijf aan vanuit een dict.

    Formaat:
        {
            "files":   ["a.txt", "b.txt"],
            "folders": {"sub": {"files": ["c.txt"], "folders": {}}}
        }
    """
    for filename in structure.get("files", []):
        (base / filename).write_text("")
    for folder_name, sub in structure.get("folders", {}).items():
        child = base / folder_name
        child.mkdir()
        _build_tree(child, sub)


def _build_entries(
    archive_id: uuid.UUID,
    root: Path,
    current: Path,
    parent_path: str | None = None,
) -> list[dict]:
    """Vertaal een map op schijf naar entries zoals FileRepository die verwacht.

    Volgorde is parent-first: een map staat altijd vóór zijn eigen bestanden,
    anders vindt path_to_id de UUID niet op het moment dat een bestand hem zoekt.

    Het '_parent_path'-veld is de absolute schijfpath van de bovenliggende map.
    FileRepository gebruikt dit om de UUID op te zoeken. Root-items krijgen None.
    """
    entries: list[dict] = []
    now = datetime.now(timezone.utc)

    for item in sorted(current.iterdir()):
        entry: dict = {
            "archive_id": archive_id,
            "_parent_path": parent_path,
            "name": item.name,
            "full_path": str(item),
            "relative_path": str(item.relative_to(root)),
            "is_directory": item.is_dir(),
            "extension": None,
            "size_bytes": None,
            "sha256_hash": None,
            "created_at": None,
            "modified_at": datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc),
            "discovered_at": now,
        }
        if not item.is_dir():
            suffix = item.suffix.lstrip(".")
            entry["extension"] = suffix if suffix else None
            entry["size_bytes"] = item.stat().st_size
        entries.append(entry)
        if item.is_dir():
            entries.extend(_build_entries(archive_id, root, item, str(item)))

    return entries


async def _make_archive(session: AsyncSession, name: str, root_path: str) -> Archive:
    """Maak een minimaal Archive-record aan in de database en geef het terug.

    flush() schrijft de INSERT binnen de lopende transactie zonder te committen.
    De FK-check op files.archive_id slaagt, en rollback ruimt alles op na de test.
    """
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_01_baseline_leeg_archief_werkt(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Sanity check: lege map geeft 0 bestanden, geen errors."""
    archive = await _make_archive(async_db_session, "test-leeg", str(tmp_path))

    await FileRepository(async_db_session).persist_all([])

    result = await async_db_session.execute(
        text("SELECT COUNT(*) FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    assert result.scalar() == 0


@pytest.mark.asyncio
async def test_02_bestand_in_root_heeft_parent_id_null(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Bestand direct in archief-root: parent_id moet NULL zijn."""
    _build_tree(tmp_path, {"files": ["readme.txt"], "folders": {}})
    archive = await _make_archive(async_db_session, "test-root-bestand", str(tmp_path))
    entries = _build_entries(archive.id, tmp_path, tmp_path)
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("SELECT name, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    rows = result.fetchall()

    assert len(rows) == 1, f"Verwacht 1 bestand, maar {len(rows)} gevonden"
    assert rows[0].name == "readme.txt"
    assert rows[0].parent_id is None, (
        f"parent_id moet NULL zijn voor root-bestand, maar was: {rows[0].parent_id}"
    )


@pytest.mark.asyncio
async def test_03_bestand_in_submap_krijgt_parent_id_van_submap(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Bestand in een submap moet parent_id krijgen die verwijst naar die submap.

    Schijfstructuur:
      tmp_path/
        Foto-archief/       ← map-record (parent_id = NULL)
          foto1.jpg         ← bestand met parent_id = id van Foto-archief
    """
    _build_tree(tmp_path, {
        "files": [],
        "folders": {"Foto-archief": {"files": ["foto1.jpg"], "folders": {}}},
    })
    archive = await _make_archive(async_db_session, "test-submap", str(tmp_path))
    entries = _build_entries(archive.id, tmp_path, tmp_path)
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    rows = result.fetchall()

    assert len(rows) == 2, (
        f"Verwacht 2 records (map + bestand), maar {len(rows)} gevonden: "
        f"{[r.name for r in rows]}"
    )

    folder = next((r for r in rows if r.name == "Foto-archief"), None)
    foto   = next((r for r in rows if r.name == "foto1.jpg"), None)

    assert folder is not None, "Map 'Foto-archief' niet gevonden in files-tabel"
    assert foto   is not None, "Bestand 'foto1.jpg' niet gevonden in files-tabel"

    assert folder.parent_id is None, (
        f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL"
    )
    assert foto.parent_id == folder.id, (
        f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
        f"maar verwacht parent_id={folder.id} (id van 'Foto-archief')\n"
        f"  foto1.jpg    full_path = {foto.full_path!r}\n"
        f"  Foto-archief full_path = {folder.full_path!r}"
    )


@pytest.mark.asyncio
async def test_04_twee_niveaus_diep_keten_van_parent_ids(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Diepere structuur: keten portret_1.jpg → Personen → Foto-archief → root.

    Schijfstructuur:
      tmp_path/
        Foto-archief/           ← parent_id = NULL
          Personen/             ← parent_id = id van Foto-archief
            portret_1.jpg       ← parent_id = id van Personen
    """
    _build_tree(tmp_path, {
        "files": [],
        "folders": {
            "Foto-archief": {
                "files": [],
                "folders": {"Personen": {"files": ["portret_1.jpg"], "folders": {}}},
            }
        },
    })
    archive = await _make_archive(async_db_session, "test-twee-niveaus", str(tmp_path))
    entries = _build_entries(archive.id, tmp_path, tmp_path)
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    rows = result.fetchall()

    assert len(rows) == 3, (
        f"Verwacht 3 records, maar {len(rows)} gevonden: {[r.name for r in rows]}"
    )

    foto_archief = next((r for r in rows if r.name == "Foto-archief"), None)
    personen     = next((r for r in rows if r.name == "Personen"), None)
    portret      = next((r for r in rows if r.name == "portret_1.jpg"), None)

    assert foto_archief is not None, "'Foto-archief' niet gevonden"
    assert personen     is not None, "'Personen' niet gevonden"
    assert portret      is not None, "'portret_1.jpg' niet gevonden"

    assert foto_archief.parent_id is None, (
        f"'Foto-archief' heeft parent_id={foto_archief.parent_id}, verwacht NULL"
    )
    assert personen.parent_id == foto_archief.id, (
        f"'Personen' heeft parent_id={personen.parent_id}, "
        f"maar verwacht parent_id={foto_archief.id} (id van 'Foto-archief')"
    )
    assert portret.parent_id == personen.id, (
        f"'portret_1.jpg' heeft parent_id={portret.parent_id}, "
        f"maar verwacht parent_id={personen.id} (id van 'Personen')"
    )


@pytest.mark.asyncio
async def test_05_tika_stap_breekt_parent_id_niet(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Na een Tika-stap op een bestand in een submap moet parent_id ongewijzigd blijven.

    PerformTikaAnalysis schrijft alleen naar tika_analyses, niet naar files.
    We roepen TikaRepository.persist() direct aan om te verifiëren dat de files-tabel
    onaangetast blijft — zonder echte Tika-server.
    """
    from app.perform_tika_analysis.tika_repository import TikaRepository

    _build_tree(tmp_path, {
        "files": [],
        "folders": {"Foto-archief": {"files": ["foto1.jpg"], "folders": {}}},
    })
    archive = await _make_archive(async_db_session, "test-tika-parent-id", str(tmp_path))
    entries = _build_entries(archive.id, tmp_path, tmp_path)
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


@pytest.mark.asyncio
async def test_06_windows_backslash_paden_in_persist_all(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Hardcoded Windows-stijl entries (backslashes) rechtstreeks aan persist_all.

    Op Mac/Linux geeft os.path.dirname("Foto-archief\\foto1.jpg") een lege string
    terug in plaats van "Foto-archief" — waardoor path_to_id nooit matcht en
    parent_id NULL blijft. Deze test maakt dat zichtbaar zonder Windows nodig.
    """
    archive = await _make_archive(async_db_session, "test-windows-paden", str(tmp_path))
    now = datetime.now(timezone.utc)

    entries = [
        {
            "archive_id": archive.id,
            "_parent_path": None,
            "name": "Foto-archief",
            "full_path": "Foto-archief",
            "relative_path": "Foto-archief",
            "is_directory": True,
            "extension": None, "size_bytes": None, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
        {
            "archive_id": archive.id,
            "_parent_path": "Foto-archief",
            "name": "foto1.jpg",
            "full_path": "Foto-archief\\foto1.jpg",    # \\ = Windows-separator
            "relative_path": "Foto-archief\\foto1.jpg",
            "is_directory": False,
            "extension": "jpg", "size_bytes": 0, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
    ]

    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    rows = result.fetchall()

    assert len(rows) == 2, f"Verwacht 2 records, maar {len(rows)} gevonden"

    folder = next((r for r in rows if r.name == "Foto-archief"), None)
    foto   = next((r for r in rows if r.name == "foto1.jpg"), None)

    assert folder is not None, "'Foto-archief' niet gevonden"
    assert foto   is not None, "'foto1.jpg' niet gevonden"

    assert folder.parent_id is None, (
        f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL"
    )
    assert foto.parent_id == folder.id, (
        f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
        f"maar verwacht parent_id={folder.id}\n"
        f"  _parent_path = {repr('Foto-archief')}\n"
        f"  full_path map = {folder.full_path!r}"
    )


@pytest.mark.asyncio
async def test_07_agent_backslash_paden_worden_genormaliseerd(
    async_db_session: AsyncSession, tmp_path: Path
):
    """Simuleert agent-output op Windows: absolute paden met backslashes.

    De agent op Windows stuurt paden zoals 'C:\\archief\\Foto-archief\\foto1.jpg'.
    folder_analysis.py normaliseert die naar forward slashes via normalize_path
    voordat de entries aan persist_all worden doorgegeven. Deze test verifieert
    dat path_to_id correct matcht na die normalisatie.
    """
    from app.shared.path_utils import normalize_path as _normalize

    archive = await _make_archive(async_db_session, "test-agent-backslash", str(tmp_path))
    now = datetime.now(timezone.utc)

    agent_map_path     = "C:\\archief\\Foto-archief"
    agent_bestand_path = "C:\\archief\\Foto-archief\\foto1.jpg"

    map_full   = _normalize(agent_map_path)        # "C:/archief/Foto-archief"
    map_parent = map_full.rsplit("/", 1)[0]         # "C:/archief"
    foto_full  = _normalize(agent_bestand_path)    # "C:/archief/Foto-archief/foto1.jpg"
    foto_parent = foto_full.rsplit("/", 1)[0]       # "C:/archief/Foto-archief"

    entries = [
        {
            "archive_id": archive.id,
            "_parent_path": map_parent,   # niet in path_to_id → parent_id NULL
            "name": "Foto-archief",
            "full_path": map_full,
            "relative_path": "Foto-archief",
            "is_directory": True,
            "extension": None, "size_bytes": None, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
        {
            "archive_id": archive.id,
            "_parent_path": foto_parent,  # moet exact matchen met map_full
            "name": "foto1.jpg",
            "full_path": foto_full,
            "relative_path": "Foto-archief/foto1.jpg",
            "is_directory": False,
            "extension": "jpg", "size_bytes": 0, "sha256_hash": None,
            "created_at": None, "modified_at": now, "discovered_at": now,
        },
    ]

    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
        {"aid": str(archive.id)},
    )
    rows = result.fetchall()

    assert len(rows) == 2, f"Verwacht 2 records, maar {len(rows)} gevonden"

    folder = next((r for r in rows if r.name == "Foto-archief"), None)
    foto   = next((r for r in rows if r.name == "foto1.jpg"), None)

    assert folder is not None, "'Foto-archief' niet gevonden"
    assert foto   is not None, "'foto1.jpg' niet gevonden"

    assert folder.parent_id is None, (
        f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL\n"
        f"  full_path = {folder.full_path!r}"
    )
    assert foto.parent_id == folder.id, (
        f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
        f"maar verwacht parent_id={folder.id}\n"
        f"  foto_parent (= _parent_path) = {foto_parent!r}\n"
        f"  map_full    (= full_path map) = {map_full!r}\n"
        f"  matchen? {foto_parent == map_full}"
    )
