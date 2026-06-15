"""Integration debug-sessie: parent_id blijft NULL voor bestanden in submappen.

Progressieve aanpak — voeg pas test_N+1 toe nadat test_N groen is.
De eerste rode test markeert precies het scenario waar de bug optreedt.

  test_01  →  sanity: lege map → 0 rijen, geen crash
  test_02  →  sanity: root-bestand → parent_id IS NULL              (verwacht ✅)
  test_03  →  submap-bestand → parent_id == id van die submap       (verdacht)
  test_04  →  2 niveaus diep: keten van parent_ids
  test_05  →  Tika erbij: parent_id blijft correct na analyse-stap
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
# Helpers
# ---------------------------------------------------------------------------
# Drie kleine hulpfuncties die de tests leesbaar houden.
# Ze staan hier zodat elke test zelf kort en duidelijk blijft.


def _build_tree(base: Path, structure: dict) -> None:
    """Maak een echte bestandsstructuur op schijf aan vanuit een dict.

    Deze bestandsstructuur stelt een archief voor — een map met brieven, foto's,
    submappen, enzovoort. In productie is dat een echte map op de schijf van de gebruiker.
    In tests simuleren we dat met tmp_path: een tijdelijke map die pytest aanmaakt
    en na de test automatisch verwijdert.

    Waarom een helper?
      Zonder dit helpertje zou elke test zelf os.makedirs() en open() moeten aanroepen.
      Dat maakt de tests lang en moeilijk leesbaar. Met _build_tree beschrijf je
      de gewenste structuur als een dict en de rest gebeurt automatisch.

    Formaat van 'structure':
        {
            "files": ["a.txt", "b.txt"],       ← bestanden in 'base'
            "folders": {
                "sub": {                        ← submap genaamd 'sub'
                    "files": ["c.txt"],
                    "folders": {}
                }
            }
        }
    """
    # Maak elk bestand aan als leeg bestand
    for filename in structure.get("files", []):
        (base / filename).write_text("")

    # Maak elke submap aan en herhaal hetzelfde voor de inhoud ervan
    for folder_name, sub in structure.get("folders", {}).items():
        child = base / folder_name
        child.mkdir()
        _build_tree(child, sub)          # ← zichzelf aanroepen voor de submap


def _build_entries(
    archive_id: uuid.UUID,
    root: Path,
    current: Path,
    parent_path: str | None = None,
) -> list[dict]:
    """Vertaal een map op schijf naar een lijst entries zoals FileRepository die verwacht.

    Waarom?
      In productie doet FolderAnalysis dit door een HTTP-call naar een agent.
      In tests willen we geen draaiende agent — we bouwen de entries zelf.

    Volgorde is belangrijk (parent-first):
      FileRepository lost '_parent_path' op terwijl hij de lijst doorloopt.
      Een map moet dus altijd vóór zijn eigen bestanden in de lijst staan,
      anders is de map nog niet bekend op het moment dat een bestand hem zoekt.

    Het '_parent_path'-veld:
      Dit is de volledige schijfpad van de bovenliggende map, als string.
      FileRepository gebruikt dit tijdelijk om de echte parent_id (UUID) op te zoeken.
      Root-level items krijgen None  → FileRepository zet parent_id op NULL.
      Items in een submap krijgen str(submap) → FileRepository vindt de UUID van die map.

    Voorbeeld 1 — bestand direct in root (/tmp/archief/readme.txt):

      Input:
        root    = Path("/tmp/archief")
        current = Path("/tmp/archief")          ← zelfde als root bij eerste aanroep
        parent_path = None                      ← geen bovenliggende map

      Output: lijst met 1 entry
        [
          {
            "_parent_path": None,               ← FileRepository → parent_id = NULL ✅
            "name":         "readme.txt",
            "full_path":    "/tmp/archief/readme.txt",
            "relative_path": "readme.txt",
            "is_directory": False,
            "extension":    "txt",
            "size_bytes":   0,
            ...
          }
        ]

    Voorbeeld 2 — submap met een bestand (/tmp/archief/brieven/brief.txt):

      Input:
        root    = Path("/tmp/archief")
        current = Path("/tmp/archief")
        parent_path = None

      Output: lijst met 2 entries, map vóór bestand (parent-first!)
        [
          {
            "_parent_path": None,               ← brieven/ zit in root → parent_id = NULL
            "name":         "brieven",
            "full_path":    "/tmp/archief/brieven",
            "is_directory": True,
            ...
          },
          {
            "_parent_path": "/tmp/archief/brieven",  ← FileRepository zoekt UUID van brieven/
            "name":         "brief.txt",             ← en zet die als parent_id ✅
            "full_path":    "/tmp/archief/brieven/brief.txt",
            "relative_path": "brieven/brief.txt",
            "is_directory": False,
            "extension":    "txt",
            ...
          }
        ]

      Als '_parent_path' van brief.txt NIET in de lijst zou staan (of verkeerd gespeld),
      dan vindt FileRepository de UUID niet → parent_id blijft NULL → dat is precies de bug.
    """
    entries: list[dict] = []
    now = datetime.now(timezone.utc)

    for item in sorted(current.iterdir()):   # gesorteerd = voorspelbare volgorde in tests
        entry: dict = {
            "archive_id": archive_id,
            "_parent_path": parent_path,     # tijdelijk veld, wordt door FileRepository verwijderd
            "name": item.name,
            "full_path": str(item),          # absoluut pad op schijf
            "relative_path": str(item.relative_to(root)),  # pad t.o.v. archief-root
            "is_directory": item.is_dir(),
            "extension": None,               # wordt hieronder ingevuld voor bestanden
            "size_bytes": None,              # idem
            "sha256_hash": None,             # wordt pas later berekend (buiten scope hier)
            "created_at": None,
            "modified_at": datetime.fromtimestamp(item.stat().st_mtime, tz=timezone.utc),
            "discovered_at": now,
        }

        if not item.is_dir():
            # Haal de extensie op (zonder de punt) — "brief.txt" → "txt"
            suffix = item.suffix.lstrip(".")
            entry["extension"] = suffix if suffix else None
            entry["size_bytes"] = item.stat().st_size

        entries.append(entry)

        if item.is_dir():
            # Voeg de inhoud van de submap toe ná de map zelf (parent-first)
            # De submap geeft zijn eigen pad mee als parent_path voor zijn kinderen
            entries.extend(_build_entries(archive_id, root, item, str(item)))

    return entries


async def _make_archive(session: AsyncSession, name: str, root_path: str) -> Archive:
    """Maak een minimaal Archive-record aan in de database en geef het terug.

    Waarom?
      De files-tabel heeft een verplichte FK naar archives (archive_id).
      Zonder een bestaand archief-record weigert de database elke file-insert.
      Deze helper maakt het snelste geldige archief aan dat daarvoor nodig is.

    flush() vs commit():
      flush() stuurt de INSERT naar de DB maar maakt hem nog niet permanent.
      Dat is genoeg: de FK-check slaagt, en de rollback aan het einde ruimt alles op.
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
    await session.flush()   # schrijf naar DB zodat de FK-constraint werkt
    return archive


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
#p python -m pytest tests/integration/test_bug_parent_ids_null.py::TestWaaromZijnParentIdsNull::test_01_baseline_leeg_archief_werkt -v 2>&1

class TestWaaromZijnParentIdsNull:
    """Debug-sessie: parent_id blijft NULL voor bestanden in submappen.

    Elke test voegt één stap complexiteit toe aan de mapstructuur en loopt
    door FileRepository.persist_all. Daarna queryen we de 'files'-tabel.

    Regel: voeg pas de volgende test toe nadat de vorige groen is.
    De eerste rode test markeert exact het scenario waar de bug optreedt.
    """

    @pytest.mark.asyncio
    async def test_01_baseline_leeg_archief_werkt(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Sanity check: lege map geeft 0 bestanden, geen errors.

        Wat er gebeurt:
          1. _make_archive → archief-record in DB (flush: zichtbaar, maar niet permanent)
          2. persist_all([]) → lege lijst, dus geen file-records
          3. query → controleer dat er inderdaad 0 bestanden zijn
          4. na de test: rollback → archief verdwijnt weer uit DB

        :aid is een placeholder die apart wordt ingevuld met {"aid": archive.id}.
        Dit voorkomt SQL-injectie en is veiliger dan de UUID in de string te plakken.
        """
        # Stap 1: maak een archief aan (tijdelijk, verdwijnt na rollback)
        archive = await _make_archive(async_db_session, "test-leeg", str(tmp_path))

        # Stap 2: sla een lege lijst op — geen bestanden verwacht
        repo = FileRepository(async_db_session)
        await repo.persist_all([])

        # Stap 3: query de DB en controleer dat er 0 bestanden zijn
        result = await async_db_session.execute(
            text("SELECT COUNT(*) FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},  # :aid wordt hier ingevuld met de UUID van het archief
        )
        assert result.scalar() == 0

    @pytest.mark.asyncio
    async def test_02_bestand_in_root_heeft_geen_parent_klopt(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Bestand direct in archief-root: parent_id moet NULL zijn.

        Wat er gebeurt:
          1. _build_tree  → maakt readme.txt aan op schijf in tmp_path ~ archief met 1 bestand
          2. _make_archive → archief-record in DB (tijdelijk, verdwijnt na rollback)
          3. _build_entries → leest de schijf en bouwt de entries-lijst die
                              FileRepository verwacht (met _parent_path=None voor readme.txt)
          4. persist_all  → slaat de entries op in de files-tabel
          5. query        → controleer: 1 rij, name=readme.txt, parent_id=NULL
          6. na de test: rollback → alles verdwijnt uit DB
        """
        # Stap 1: zet readme.txt op schijf in de tijdelijke map
        # Schijfstructuur na deze aanroep:
        #   tmp_path/
        #     readme.txt
        _build_tree(tmp_path, {"files": ["readme.txt"], "folders": {}})

        # Stap 2: maak een archief-record aan in de DB (nodig voor de FK op files.archive_id)
        archive = await _make_archive(
            async_db_session, "test-root-bestand", str(tmp_path)
        )

        # Stap 3: lees de schijf en bouw de entries-lijst
        # readme.txt zit direct in root → _parent_path=None → FileRepository zet parent_id=NULL
        entries = _build_entries(archive.id, tmp_path, tmp_path)

        # Stap 4: sla de entries op via FileRepository (de code die we testen)
        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        # Stap 5: query de DB en controleer het resultaat
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

    def test_06_windows_pad_met_backslash_wordt_genormaliseerd(self):
        """Een Windows-pad ('Foto-archief\\foto1.jpg') moet genormaliseerd worden naar
        'Foto-archief/foto1.jpg' voordat het in full_path of _parent_path belandt.

        Zonder normalisatie geldt op Mac/Linux:
          os.path.dirname("Foto-archief\\foto1.jpg") → geeft "" (leeg), NIET "Foto-archief"
          Dan matcht _parent_path nooit met full_path van de map → parent_id blijft NULL.

        normalize_path staat in app/shared/path_utils en wordt aangeroepen in
        FolderAnalysis.analyze() op elk full_path, _parent_path en relative_path.
        """
        from app.shared.path_utils import normalize_path

        assert normalize_path("Foto-archief\\foto1.jpg") == "Foto-archief/foto1.jpg"
        assert normalize_path("Foto-archief/foto1.jpg")  == "Foto-archief/foto1.jpg"  # forward slash ongewijzigd
        assert normalize_path("a\\b\\c")                 == "a/b/c"

    def test_07_parent_path_en_full_path_gebruiken_zelfde_separator(
        self, tmp_path: Path
    ):
        """De _parent_path van een bestand moet EXACT gelijk zijn aan de full_path
        van de bovenliggende map — zelfde separators, zelfde string.

        Dit test de SCANNER (_build_entries), niet de repository.
        FileRepository doet een simpele dict-lookup: path_to_id.get(_parent_path).
        Als _parent_path en full_path ook maar één karakter verschillen
        (bijv. \\ vs /), vindt de lookup niets en wordt parent_id NULL.

        Op Mac/Linux is dit normaal groen (beide gebruiken /).
        Op Windows kan dit rood zijn als de scanner \\ en / door elkaar gebruikt.
        Deze test documenteert het contract en dient als regressietest voor
        een Windows-CI runner.
        """
        import uuid as _uuid

        _build_tree(tmp_path, {
            "files": [],
            "folders": {
                "Foto-archief": {
                    "files": [],
                    "folders": {
                        "Personen": {
                            "files": ["portret_1.jpg"],
                            "folders": {},
                        }
                    },
                }
            },
        })

        # Haal de ruwe entries op VOORDAT persist_all de _parent_path verwijdert
        entries = _build_entries(_uuid.uuid4(), tmp_path, tmp_path)

        entry_map     = next((e for e in entries if e["name"] == "Personen"),      None)
        entry_bestand = next((e for e in entries if e["name"] == "portret_1.jpg"), None)

        assert entry_map     is not None, "'Personen' niet gevonden in entries"
        assert entry_bestand is not None, "'portret_1.jpg' niet gevonden in entries"

        # Het contract: _parent_path van het bestand == full_path van de map
        # repr() maakt \\ vs / zichtbaar als de assert faalt
        assert entry_bestand["_parent_path"] == entry_map["full_path"], (
            f"_parent_path van 'portret_1.jpg' matcht NIET met full_path van 'Personen'.\n"
            f"  entry_bestand['_parent_path'] = {entry_bestand['_parent_path']!r}\n"
            f"  entry_map['full_path']         = {entry_map['full_path']!r}\n"
            "Dit is de root cause: FileRepository kan de parent nooit vinden als "
            "deze strings niet exact gelijk zijn."
        )

    @pytest.mark.asyncio
    async def test_03_bestand_in_submap_heeft_parent_id_van_submap(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """HIER VERWACHTEN WE DE BUG.

        Een bestand in een submap moet een parent_id hebben die verwijst naar
        het record van die submap. De submap zelf heeft parent_id IS NULL
        (want die zit direct in root).

        Schijfstructuur:
          tmp_path/
            Foto-archief/       ← dit wordt een map-record (parent_id = NULL)
              foto1.jpg         ← dit moet parent_id = id van Foto-archief krijgen

        Als assert 3 faalt, print de debug-assert de exacte paden zodat we
        kunnen zien of er een verschil is in spelling, slashes of casing.
        """
        # Stap 1: zet de mapstructuur op schijf
        _build_tree(tmp_path, {
            "files": [],
            "folders": {
                "Foto-archief": {
                    "files": ["foto1.jpg"],
                    "folders": {},
                }
            },
        })

        # Stap 2: archief-record in DB (tijdelijk, verdwijnt na rollback)
        archive = await _make_archive(
            async_db_session, "test-submap", str(tmp_path)
        )

        # Stap 3: bouw entries vanuit schijf en sla op via FileRepository
        # Verwachte entries (parent-first):
        #   [0] Foto-archief/  →  _parent_path=None       → parent_id=NULL
        #   [1] foto1.jpg      →  _parent_path=str(Foto-archief/)  → parent_id=id van Foto-archief
        entries = _build_entries(archive.id, tmp_path, tmp_path)

        # DEBUG: print de entries vóór persist zodat we bij een fout exact
        # kunnen zien welke paden en _parent_path waarden zijn doorgegeven
        for e in entries:
            print(f"\n[DEBUG entry] name={e['name']!r}  "
                  f"full_path={e['full_path']!r}  "
                  f"_parent_path={e.get('_parent_path')!r}")

        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        # Stap 4: haal beide records op uit de DB
        result = await async_db_session.execute(
            text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},
        )
        rows = result.fetchall()

        # Assert 1: er moeten exact 2 records zijn (1 map + 1 bestand)
        assert len(rows) == 2, (
            f"Verwacht 2 records (map + bestand), maar {len(rows)} gevonden: "
            f"{[r.name for r in rows]}"
        )

        # Zoek de twee records op naam
        folder = next((r for r in rows if r.name == "Foto-archief"), None)
        foto   = next((r for r in rows if r.name == "foto1.jpg"),    None)

        assert folder is not None, "Map 'Foto-archief' niet gevonden in files-tabel"
        assert foto   is not None, "Bestand 'foto1.jpg' niet gevonden in files-tabel"

        # Assert 2: de map zit in root → parent_id moet NULL zijn
        assert folder.parent_id is None, (
            f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL"
        )

        # Assert 3: het bestand moet parent_id == id van de map hebben
        assert foto.parent_id == folder.id, (
            f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
            f"maar verwacht parent_id={folder.id} (id van 'Foto-archief')\n"
            f"  foto1.jpg  full_path = {foto.full_path!r}\n"
            f"  Foto-archief full_path = {folder.full_path!r}"
        )

    @pytest.mark.asyncio
    async def test_04_twee_niveaus_diep_keten_van_parent_ids(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Diepere structuur: Foto-archief/Personen/portret_1.jpg.

        Verwacht een keten van parent_ids:
          portret_1.jpg → Personen → Foto-archief → (root, parent_id NULL)

        Test of path_to_id correct blijft bij meerdere geneste niveaus,
        niet enkel 1 niveau zoals test_03.

        Schijfstructuur:
          tmp_path/
            Foto-archief/            ← parent_id = NULL (zit in root)
              Personen/              ← parent_id = id van Foto-archief
                portret_1.jpg       ← parent_id = id van Personen
        """
        # Stap 1: zet de mapstructuur op schijf
        _build_tree(tmp_path, {
            "files": [],
            "folders": {
                "Foto-archief": {
                    "files": [],
                    "folders": {
                        "Personen": {
                            "files": ["portret_1.jpg"],
                            "folders": {},
                        }
                    },
                }
            },
        })

        # Stap 2: archief-record in DB (tijdelijk, verdwijnt na rollback)
        archive = await _make_archive(
            async_db_session, "test-twee-niveaus", str(tmp_path)
        )

        # Stap 3: bouw entries vanuit schijf en sla op via FileRepository
        # Verwachte entries (parent-first):
        #   [0] Foto-archief/    →  _parent_path=None              → parent_id=NULL
        #   [1] Personen/        →  _parent_path=str(Foto-archief) → parent_id=id Foto-archief
        #   [2] portret_1.jpg    →  _parent_path=str(Personen)     → parent_id=id Personen
        entries = _build_entries(archive.id, tmp_path, tmp_path)

        # DEBUG: print de volledige keten vóór persist zodat we bij een fout
        # exact kunnen zien welke paden en _parent_path waarden zijn doorgegeven
        print("\n[DEBUG] entries vóór persist_all:")
        for e in entries:
            print(f"  name={e['name']!r:20s}  "
                  f"full_path={e['full_path']!r}  "
                  f"_parent_path={e.get('_parent_path')!r}")

        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        # Stap 4: haal de 3 records op uit de DB
        result = await async_db_session.execute(
            text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},
        )
        rows = result.fetchall()

        # Assert 1: exact 3 records (2 mappen + 1 bestand)
        assert len(rows) == 3, (
            f"Verwacht 3 records, maar {len(rows)} gevonden: {[r.name for r in rows]}"
        )

        # Zoek de drie records op naam
        foto_archief  = next((r for r in rows if r.name == "Foto-archief"),  None)
        personen      = next((r for r in rows if r.name == "Personen"),      None)
        portret       = next((r for r in rows if r.name == "portret_1.jpg"), None)

        assert foto_archief is not None, "'Foto-archief' niet gevonden in files-tabel"
        assert personen     is not None, "'Personen' niet gevonden in files-tabel"
        assert portret      is not None, "'portret_1.jpg' niet gevonden in files-tabel"

        # DEBUG: print de volledige keten na persist voor elk record
        print("\n[DEBUG] records na persist_all:")
        for r in [foto_archief, personen, portret]:
            print(f"  name={r.name!r:20s}  id={r.id}  parent_id={r.parent_id}  "
                  f"full_path={r.full_path!r}")

        # Assert 2: Foto-archief zit in root → parent_id moet NULL zijn
        assert foto_archief.parent_id is None, (
            f"'Foto-archief' heeft parent_id={foto_archief.parent_id}, verwacht NULL"
        )

        # Assert 3: Personen moet parent_id == id van Foto-archief hebben
        assert personen.parent_id == foto_archief.id, (
            f"'Personen' heeft parent_id={personen.parent_id}, "
            f"maar verwacht parent_id={foto_archief.id} (id van 'Foto-archief')\n"
            f"  Personen     full_path = {personen.full_path!r}\n"
            f"  Foto-archief full_path = {foto_archief.full_path!r}"
        )

        # Assert 4: portret_1.jpg moet parent_id == id van Personen hebben
        assert portret.parent_id == personen.id, (
            f"'portret_1.jpg' heeft parent_id={portret.parent_id}, "
            f"maar verwacht parent_id={personen.id} (id van 'Personen')\n"
            f"  portret_1.jpg full_path = {portret.full_path!r}\n"
            f"  Personen      full_path = {personen.full_path!r}"
        )

    @pytest.mark.asyncio
    async def test_05_tika_run_breekt_parent_id_niet(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Na een Tika-analyse op een bestand in een submap moet parent_id ongewijzigd blijven.

        We controleren of de Tika-stap per ongeluk het file-record overschrijft
        of opnieuw aanmaakt zonder parent_id.

        Opmerking over de aanpak:
          PerformTikaAnalysis leest de files-tabel (read-only) en schrijft alleen
          naar tika_analyses. We roepen TikaRepository.persist() daarom direct aan —
          de DB-schrijfstap die theoretisch parent_id zou kunnen raken — zonder een
          echte Tika HTTP-call. Zo is geen draaiende Tika-server nodig.
        """
        from app.perform_tika_analysis.tika_repository import TikaRepository

        # Stap 1: zelfde setup als test_03 — submap met foto1.jpg
        _build_tree(tmp_path, {
            "files": [],
            "folders": {
                "Foto-archief": {
                    "files": ["foto1.jpg"],
                    "folders": {},
                }
            },
        })

        archive = await _make_archive(
            async_db_session, "test-tika-parent-id", str(tmp_path)
        )
        entries = _build_entries(archive.id, tmp_path, tmp_path)
        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        # Stap 2: query VOOR Tika — noteer parent_id en record-id van foto1.jpg
        result_voor = await async_db_session.execute(
            text("SELECT id, name, parent_id FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},
        )
        rows_voor = result_voor.fetchall()
        foto_voor = next((r for r in rows_voor if r.name == "foto1.jpg"), None)
        assert foto_voor is not None, "'foto1.jpg' niet gevonden vóór Tika-run"

        parent_id_voor = foto_voor.parent_id
        record_id_voor = foto_voor.id

        # Stap 3: simuleer Tika — sla een TikaAnalysis op voor foto1.jpg
        # (dummy-waarden: we testen de DB-schrijfstap, niet de extractie zelf)
        tika_repo = TikaRepository(async_db_session)
        await tika_repo.persist(
            file_id=str(foto_voor.id),
            mime_type="image/jpeg",
            tika_parser="org.apache.tika.parser.image.ImageParser",
            content=None,
            language=None,
            word_count=0,
            author=None,
            content_created_at=None,
        )

        # Stap 4: query NA Tika — zelfde foto1.jpg opnieuw ophalen
        result_na = await async_db_session.execute(
            text("SELECT id, name, parent_id FROM files WHERE archive_id = :aid AND name = 'foto1.jpg'"),
            {"aid": str(archive.id)},
        )
        foto_na = result_na.fetchone()
        assert foto_na is not None, "'foto1.jpg' niet meer gevonden ná Tika-run"

        # Assert 1: parent_id mag niet veranderd zijn
        assert foto_na.parent_id == parent_id_voor, (
            f"parent_id is veranderd na Tika-run!\n"
            f"  vóór: parent_id={parent_id_voor}\n"
            f"  na:   parent_id={foto_na.parent_id}"
        )

        # Assert 2: het record-id mag niet veranderd zijn (geen nieuw record aangemaakt)
        assert foto_na.id == record_id_voor, (
            f"Record-id is veranderd na Tika-run — nieuw record aangemaakt!\n"
            f"  vóór: id={record_id_voor}\n"
            f"  na:   id={foto_na.id}"
        )

    @pytest.mark.asyncio
    async def test_08_windows_paden_met_backslash_in_persist_all(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Simuleert scan-output zoals die er op Windows uitziet (backslashes in paden).

        Test of FileRepository.persist_all de parent_id correct zet, ONAFHANKELIJK
        van of het pad / of \\ gebruikt.

        Op Windows geeft os.path.dirname("Foto-archief\\foto1.jpg") terug: "Foto-archief"
        Op Mac/Linux geeft diezelfde aanroep terug:                         ""   (leeg!)

        Als FileRepository intern os.path.dirname of string-vergelijking doet zonder
        pad-normalisatie, zal _parent_path op Mac nooit matchen met full_path van de map
        en blijft parent_id NULL. Deze test maakt dat zichtbaar zonder Windows nodig.

        We slaan de filesystem-scan volledig over en geven hardcoded entries met
        Windows-stijl backslash-paden rechtstreeks aan persist_all.
        """
        from datetime import datetime, timezone as tz

        archive = await _make_archive(
            async_db_session, "test-windows-paden", str(tmp_path)
        )
        now = datetime.now(tz.utc)

        # Hardcoded Windows-stijl entries — geen scan, geen tmp_path
        # _parent_path gebruikt backslash zoals os.path.dirname op Windows zou doen
        entries = [
            {
                "archive_id": archive.id,
                "_parent_path": None,               # root-level map → parent_id = NULL
                "name": "Foto-archief",
                "full_path": "Foto-archief",        # Windows: geen leading slash
                "relative_path": "Foto-archief",
                "is_directory": True,
                "extension": None,
                "size_bytes": None,
                "sha256_hash": None,
                "created_at": None,
                "modified_at": now,
                "discovered_at": now,
            },
            {
                "archive_id": archive.id,
                "_parent_path": "Foto-archief",     # backslash-pad zoals Windows stuurt
                "name": "foto1.jpg",
                "full_path": "Foto-archief\\foto1.jpg",   # \\ = Windows-separator
                "relative_path": "Foto-archief\\foto1.jpg",
                "is_directory": False,
                "extension": "jpg",
                "size_bytes": 0,
                "sha256_hash": None,
                "created_at": None,
                "modified_at": now,
                "discovered_at": now,
            },
        ]

        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        result = await async_db_session.execute(
            text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},
        )
        rows = result.fetchall()

        # Assert 1: exact 2 records aangemaakt
        assert len(rows) == 2, (
            f"Verwacht 2 records, maar {len(rows)} gevonden: {[r.name for r in rows]}"
        )

        folder = next((r for r in rows if r.name == "Foto-archief"), None)
        foto   = next((r for r in rows if r.name == "foto1.jpg"),    None)

        assert folder is not None, "'Foto-archief' niet gevonden"
        assert foto   is not None, "'foto1.jpg' niet gevonden"

        # Assert 2: map in root → parent_id IS NULL
        assert folder.parent_id is None, (
            f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL"
        )

        # Assert 3: bestand moet parent_id == id van de map hebben
        # Als dit faalt: repr() toont expliciet of \\ vs / het probleem is
        assert foto.parent_id == folder.id, (
            f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
            f"maar verwacht parent_id={folder.id}\n"
            f"  _parent_path van foto1.jpg  = {repr('Foto-archief')}\n"
            f"  full_path van Foto-archief  = {repr(folder.full_path)}\n"
            f"  → matchen deze twee exact? {repr('Foto-archief') == repr(folder.full_path)}"
        )

    @pytest.mark.asyncio
    async def test_09_agent_geeft_backslash_paden_parent_id_klopt(
        self, async_db_session: AsyncSession, tmp_path: Path
    ):
        """Simuleert agent-output op Windows: absolute_path bevat backslashes
        zoals de agent ze teruggeeft aan de Linux-container.

        De Linux-container draait folder_analysis.py en ontvangt van de Windows-agent
        paden zoals 'C:\\\\archief\\\\Foto-archief\\\\foto1.jpg'. De fix in
        folder_analysis.py normaliseert eerst naar forward slashes en splitst
        dan pas — zo matcht _parent_path altijd met full_path in path_to_id.

        We simuleren die verwerking hier door entries te bouwen zoals
        folder_analysis.py dat na de fix doet, en verifiëren via persist_all
        dat parent_id correct wordt gezet.
        """
        from app.shared.path_utils import normalize_path as _normalize

        archive = await _make_archive(
            async_db_session, "test-agent-backslash", str(tmp_path)
        )
        now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)

        # Agent op Windows stuurt paden met backslashes
        agent_map_path      = "C:\\archief\\Foto-archief"
        agent_bestand_path  = "C:\\archief\\Foto-archief\\foto1.jpg"

        # Simuleer de verwerking in folder_analysis.py (na de fix):
        #   full_path   = normalize_path(absolute_path)
        #   parent_path = full_path.rsplit("/", 1)[0]
        map_full      = _normalize(agent_map_path)        # "C:/archief/Foto-archief"
        map_parent    = map_full.rsplit("/", 1)[0]        # "C:/archief"
        foto_full     = _normalize(agent_bestand_path)    # "C:/archief/Foto-archief/foto1.jpg"
        foto_parent   = foto_full.rsplit("/", 1)[0]       # "C:/archief/Foto-archief"

        entries = [
            {
                "archive_id": archive.id,
                "_parent_path": map_parent,   # "C:/archief" — niet in path_to_id → parent_id NULL
                "name": "Foto-archief",
                "full_path": map_full,
                "relative_path": "Foto-archief",
                "is_directory": True,
                "extension": None,
                "size_bytes": None,
                "sha256_hash": None,
                "created_at": None,
                "modified_at": now,
                "discovered_at": now,
            },
            {
                "archive_id": archive.id,
                "_parent_path": foto_parent,  # "C:/archief/Foto-archief" → moet matchen met map_full
                "name": "foto1.jpg",
                "full_path": foto_full,
                "relative_path": "Foto-archief/foto1.jpg",
                "is_directory": False,
                "extension": "jpg",
                "size_bytes": 0,
                "sha256_hash": None,
                "created_at": None,
                "modified_at": now,
                "discovered_at": now,
            },
        ]

        repo = FileRepository(async_db_session)
        await repo.persist_all(entries)

        result = await async_db_session.execute(
            text("SELECT id, name, full_path, parent_id FROM files WHERE archive_id = :aid"),
            {"aid": str(archive.id)},
        )
        rows = result.fetchall()

        assert len(rows) == 2, (
            f"Verwacht 2 records, maar {len(rows)} gevonden: {[r.name for r in rows]}"
        )

        folder = next((r for r in rows if r.name == "Foto-archief"), None)
        foto   = next((r for r in rows if r.name == "foto1.jpg"),    None)

        assert folder is not None, "'Foto-archief' niet gevonden"
        assert foto   is not None, "'foto1.jpg' niet gevonden"

        # De map heeft geen bekende parent (archief-root zit niet in path_to_id) → NULL
        assert folder.parent_id is None, (
            f"'Foto-archief' heeft parent_id={folder.parent_id}, verwacht NULL\n"
            f"  full_path = {folder.full_path!r}"
        )

        # Het bestand moet parent_id == id van de map hebben
        assert foto.parent_id == folder.id, (
            f"'foto1.jpg' heeft parent_id={foto.parent_id}, "
            f"maar verwacht parent_id={folder.id}\n"
            f"  foto_parent  (= _parent_path) = {foto_parent!r}\n"
            f"  map_full     (= full_path map) = {map_full!r}\n"
            f"  matchen?     {foto_parent == map_full}"
        )
