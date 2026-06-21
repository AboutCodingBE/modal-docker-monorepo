"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.02 — Paden worden correct genormaliseerd en opgeslagen.

Story: "Worden full_path en relative_path correct opgeslagen?
Backslashes naar forward slashes, spaties en accenten in mapnamen, diepe nesting?"

Context:
  De agent draait op de host (Windows) en geeft absolute paden terug met
  backslashes (C:\\Users\\...). FolderAnalysis normaliseert die via normalize_path
  naar forward slashes. Deze integratietest verifieert het eindresultaat in de DB.

  De pure string-logica van normalize_path is al uitvoerig gedekt als unit test:
  tests/unit/test_path_normalization.py

Wat we testen:
  Binnen één archief met meerdere mappen controleren we:
  - full_path bevat geen backslashes (Windows-normalisatie werkt end-to-end)
  - relative_path is correct per submap-niveau
  - mapnamen met spaties worden ongewijzigd bewaard
  - mapnamen met accenten worden ongewijzigd bewaard
  - diep geneste bestanden hebben het juiste relative_path

Teststrategie:
  ECHT: de agent scant een tijdelijke map met echte directory-structuren op schijf.
  ECHT: FileRepository slaat de genormaliseerde entries op in PostgreSQL.

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


@pytest.mark.asyncio
async def test_paden_worden_correct_genormaliseerd_en_opgeslagen(
    async_db_session,
    requires_agent,   # faalt de test als de agent niet bereikbaar is; geeft agent-URL terug
    tmp_path,         # pytest-fixture: tijdelijke map die automatisch wordt opgeruimd
):
    """Scant een tijdelijke map met mappen die spaties, accenten en diepe nesting
    bevatten. Controleert dat full_path en relative_path correct in de DB staan.
    """
    agent_url = requires_agent  # bevestigt dat de agent bereikbaar is op dit adres
    # Bouw drie directory-structuren op in tmp_path:
    #   1. Map met spaties in de naam
    #   2. Map met accenten in de naam
    #   3. Diep geneste structuur (4 niveaus)
    # mkdir() maakt de map aan; touch() maakt een leeg bestand met die naam.
    (tmp_path / "mijn documenten").mkdir()
    (tmp_path / "mijn documenten" / "brief.pdf").touch()

    (tmp_path / "café résumé").mkdir()
    (tmp_path / "café résumé" / "verslag.docx").touch()

    (tmp_path / "archief" / "jaar" / "maand" / "dag").mkdir(parents=True)
    (tmp_path / "archief" / "jaar" / "maand" / "dag" / "nota.txt").touch()

    archive_id = uuid.uuid4()

    # flush() schrijft de rij naar de DB binnen de huidige transactie zonder
    # te committen — de rollback aan het einde van async_db_session ruimt alles op.
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "pad-normalisatie-test", "root_path": str(tmp_path)},
    )
    await async_db_session.flush()

    entries = await FolderAnalysis().analyze(archive_id, str(tmp_path))
    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("""
            SELECT name, full_path, relative_path FROM files
            WHERE archive_id = :archive_id AND is_directory = false
        """),
        {"archive_id": str(archive_id)},
    )
    # Zet resultaten om naar een dict op naam zodat we per bestand kunnen asserteren.
    rows = {row.name: dict(row._mapping) for row in result}

    # Geen enkele full_path mag een backslash bevatten —
    # de Windows → forward-slash normalisatie moet end-to-end werken.
    for name, row in rows.items():
        assert "\\" not in row["full_path"], (
            f"Backslash gevonden in full_path van '{name}': {row['full_path']!r}"
        )

    # Spaties in mapnaam: relative_path bevat de mapnaam met spaties intact.
    assert rows["brief.pdf"]["relative_path"] == "mijn documenten/brief.pdf", (
        f"relative_path: verwacht 'mijn documenten/brief.pdf', "
        f"kreeg {rows['brief.pdf']['relative_path']!r}"
    )

    # Accenten in mapnaam: relative_path bewaard ongewijzigd.
    assert rows["verslag.docx"]["relative_path"] == "café résumé/verslag.docx", (
        f"relative_path: verwacht 'café résumé/verslag.docx', "
        f"kreeg {rows['verslag.docx']['relative_path']!r}"
    )

    # Diep genest pad: relative_path reflecteert alle tussenliggende mappen.
    assert rows["nota.txt"]["relative_path"] == "archief/jaar/maand/dag/nota.txt", (
        f"relative_path: verwacht 'archief/jaar/maand/dag/nota.txt', "
        f"kreeg {rows['nota.txt']['relative_path']!r}"
    )
