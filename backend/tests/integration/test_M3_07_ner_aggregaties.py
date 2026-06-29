"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.07 — NER aggregaties per map.

Story: "Hoe worden NER-resultaten op hogere niveaus geaggregeerd: per map,
per bovenliggende map, etc.?"

Wat we testen:
  Een map bevat meerdere bestanden met eigen NER-resultaten. Wanneer een
  gebruiker entiteiten opvraagt voor die map, verwachten we een geaggregeerd
  overzicht van de meest voorkomende entiteiten over alle bestanden heen.

  Opzet:
    map_correspondentie/
      brief_jan.txt  → persons: [Jan Hendrickx, Marie Claes]
      brief_feb.txt  → persons: [Jan Hendrickx, Piet Janssen]
      brief_mar.txt  → persons: [Jan Hendrickx]

  Verwachte aggregatie (persons, gesorteerd op frequentie):
    Jan Hendrickx   3×   ← meest frequent
    Marie Claes     1×
    Piet Janssen    1×

  Er zijn twee aparte tests:

  Test 1 — DB-laag (SQL UNNEST + GROUP BY):
    Bewijst dat de ner-tabel en PostgreSQL de aggregatie ondersteunen.
    Verwacht: GROEN.

  Test 2 — Applicatielaag (NerRepository.get_folder_entities()):
    Roept de methode aan die in de applicatiecode zou moeten bestaan.
    Verwacht: ROOD — de methode bestaat nog niet. Dit test definieert
    de interface die geïmplementeerd moet worden.

Teststrategie:
  - ECHT: NerRepository.persist() + echte PostgreSQL.
  - Geen run_ner() nodig — we testen aggregatielogica, niet detectie.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository


FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M3"


def _ner(persons: list[str]) -> dict:
    """Hulpfunctie: maakt een minimaal NER-resultaat met opgegeven personen."""
    return {
        "persons": persons, "persons_count": len(persons),
        "locations": [], "locations_count": 0,
        "organisations": [], "organisations_count": 0,
        "misc": [], "misc_count": 0,
    }


async def _setup_map_met_drie_bestanden(session, cleanup_ids):
    """Maakt een archief met één map en drie bestanden aan, geeft de IDs terug."""
    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_ids = [uuid.uuid4(), uuid.uuid4(), uuid.uuid4()]
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-aggregatie", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'correspondentie', :fp, 'correspondentie', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/ner-test/{archive_id}/correspondentie"},
    )
    for i, fid in enumerate(file_ids):
        naam = f"brief_{i+1}.txt"
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid),
                "archive_id": str(archive_id),
                "parent_id": str(folder_id),
                "name": naam,
                "fp": f"/tmp/ner-test/{archive_id}/correspondentie/{naam}",
                "rp": f"correspondentie/{naam}",
            },
        )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    repo = NerRepository(session)
    await repo.persist(analysis_id, archive_id, folder_id, file_ids[0], _ner(["Jan Hendrickx", "Marie Claes"]))
    await repo.persist(analysis_id, archive_id, folder_id, file_ids[1], _ner(["Jan Hendrickx", "Piet Janssen"]))
    await repo.persist(analysis_id, archive_id, folder_id, file_ids[2], _ner(["Jan Hendrickx"]))
    await session.commit()

    return folder_id, analysis_id


@pytest.mark.asyncio
async def test_db_aggregeert_entities_per_map_op_frequentie(committing_db_session):
    """DB-laag: UNNEST + GROUP BY geeft personen gesorteerd op frequentie per map.

    Jan Hendrickx staat in alle 3 brieven en moet bovenaan staan."""
    session, cleanup_ids = committing_db_session
    folder_id, analysis_id = await _setup_map_met_drie_bestanden(session, cleanup_ids)

    rijen = await session.execute(
        text("""
            SELECT UNNEST(persons) AS entity, COUNT(*) AS frequency
            FROM ner
            WHERE parent_folder_id = :folder_id
              AND analysis_id = :analysis_id
            GROUP BY entity
            ORDER BY frequency DESC
        """),
        {"folder_id": str(folder_id), "analysis_id": str(analysis_id)},
    )
    resultaat = [{"entity": r.entity, "frequency": r.frequency} for r in rijen.all()]

    print(f"\n[M3.07] Geaggregeerde personen voor map (gesorteerd op frequentie):")
    for r in resultaat:
        print(f"        {r['entity']:<25} {r['frequency']}x")

    entiteitsnamen = [r["entity"] for r in resultaat]
    assert "Jan Hendrickx" in entiteitsnamen, (
        "Jan Hendrickx komt voor in alle 3 bestanden maar staat niet in de aggregatie."
    )
    assert "Marie Claes" in entiteitsnamen
    assert "Piet Janssen" in entiteitsnamen

    meest_frequent = resultaat[0]
    assert meest_frequent["entity"] == "Jan Hendrickx", (
        f"Verwacht 'Jan Hendrickx' als meest frequente entiteit (3x), "
        f"maar kreeg '{meest_frequent['entity']}' ({meest_frequent['frequency']}x)."
    )
    assert meest_frequent["frequency"] == 3, (
        f"Jan Hendrickx staat in 3 bestanden maar frequency = {meest_frequent['frequency']}."
    )


@pytest.mark.asyncio
async def test_applicatielaag_heeft_methode_voor_folder_entity_aggregatie(committing_db_session):
    """Applicatielaag: NerRepository.get_folder_entities() moet bestaan.

    Deze test is ROOD zolang de methode niet geïmplementeerd is.
    Interface: get_folder_entities(analysis_id, folder_id) -> list[dict]
    Verwacht resultaat: [{"entity": str, "frequency": int}, ...]  gesorteerd op frequency DESC.
    """
    session, cleanup_ids = committing_db_session
    folder_id, analysis_id = await _setup_map_met_drie_bestanden(session, cleanup_ids)

    # NerRepository.get_folder_entities() bestaat nog niet — test faalt hier.
    resultaat = await NerRepository(session).get_folder_entities(
        analysis_id=analysis_id,
        folder_id=folder_id,
        category="persons",
    )

    assert resultaat[0]["entity"] == "Jan Hendrickx"
    assert resultaat[0]["frequency"] == 3


@pytest.mark.asyncio
async def test_ner_run_vult_db_zodat_folderniveau_entities_opvraagbaar_zijn(
    committing_db_session,
):
    """Na een echte NER-run op twee bestanden in dezelfde map staan er in de DB
    ner-rijen met parent_folder_id ingevuld, zodat folderniveau-queries werken
    zonder een aparte aggregatiefunctie.

    We gebruiken twee verschillende fixture-teksten zodat de entiteiten per bestand
    ook echt verschillen — Nederlandstalig vs. Franstalig."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_id_nl = uuid.uuid4()
    file_id_fr = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-folder-vul", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'map1', :fp, 'map1', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/ner-test/{archive_id}/map1"},
    )
    for fid, naam in [(file_id_nl, "normaal_document.txt"), (file_id_fr, "correspondance_francophone.txt")]:
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid),
                "archive_id": str(archive_id),
                "parent_id": str(folder_id),
                "name": naam,
                "fp": str(FIXTURE_DIR / naam),
                "rp": f"map1/{naam}",
            },
        )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    # Voer echte NER uit op beide bestanden en persisteer met parent_folder_id
    repo = NerRepository(session)
    for fid, naam in [(file_id_nl, "normaal_document.txt"), (file_id_fr, "correspondance_francophone.txt")]:
        tekst = (FIXTURE_DIR / naam).read_text(encoding="utf-8")
        ner_resultaat = run_ner(tekst)
        await repo.persist(analysis_id, archive_id, folder_id, fid, ner_resultaat)
    await session.commit()

    # Query op mapniveau — geen speciale functie, gewoon WHERE parent_folder_id
    rijen = await session.execute(
        text("""
            SELECT file_id, persons_count, locations_count, organisations_count
            FROM ner
            WHERE parent_folder_id = :folder_id AND analysis_id = :analysis_id
            ORDER BY persons_count DESC
        """),
        {"folder_id": str(folder_id), "analysis_id": str(analysis_id)},
    )
    ner_per_bestand = rijen.mappings().all()

    print(f"\n[M3.07] NER-rijen op mapniveau na echte run:")
    for r in ner_per_bestand:
        print(f"        file_id={r['file_id']}  persons={r['persons_count']}  "
              f"locations={r['locations_count']}  orgs={r['organisations_count']}")

    assert len(ner_per_bestand) == 2, (
        f"Verwacht 2 ner-rijen (één per bestand in de map), "
        f"maar er zijn er {len(ner_per_bestand)}. "
        "Controleer of parent_folder_id correct wordt meegegeven aan persist()."
    )
    totaal_persons = sum(r["persons_count"] for r in ner_per_bestand)
    assert totaal_persons > 0, (
        "Geen enkele persoon gevonden over beide bestanden heen — "
        "NER heeft niets gedetecteerd of parent_folder_id werd niet ingesteld."
    )
