"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.09 — Folder-aggregatie: drie opzetcasussen met echte NER.

Story: "Worden entiteiten correct geaggregeerd ongeacht of een map bestanden,
submappen, of een mix van beide bevat?"

Fixture-bestanden (één à twee zinnen, Nederlandstalig):
  brief_jan_1.txt  → Jan Hendrickx + Gemeentearchief + Gent
  brief_jan_2.txt  → Jan Hendrickx + Marie Claes + Amsab-ISG + Gent
  brief_marie.txt  → Marie Claes + Gentse Socialistische Partij + Brussel
  brief_piet.txt   → Piet Janssen + Karel Vermeersch + Amsab-ISG + Gent

De drie casussen:

  Casus 1 — map met alleen bestanden:

    map/
    ├── brief_jan_1.txt   (Jan Hendrickx, Gent)
    ├── brief_jan_2.txt   (Jan Hendrickx, Marie Claes, Gent)
    └── brief_marie.txt   (Marie Claes, Brussel)

    Verwacht: entiteiten die in meerdere bestanden voorkomen hebben hogere count.

  Casus 2 — map met alleen submappen (geen directe bestanden):

    root/
    ├── sub_a/
    │   ├── brief_jan_1.txt   (Jan Hendrickx, Gent)
    │   └── brief_jan_2.txt   (Jan Hendrickx, Marie Claes, Gent)
    └── sub_b/
        ├── brief_marie.txt   (Marie Claes, Brussel)
        └── brief_piet.txt    (Piet Janssen, Karel Vermeersch, Gent)

    Verwacht: root-aggregatie = som van sub_a + sub_b counts.

  Casus 3 — map met zowel bestanden als submappen:

    root/
    ├── brief_jan_1.txt   (Jan Hendrickx, Gent)
    └── sub/
        ├── brief_jan_2.txt   (Jan Hendrickx, Marie Claes, Gent)
        └── brief_marie.txt   (Marie Claes, Brussel)

    Verwacht: root telt direct bestand + subfolder samen.

Assertiestrategie:
  - We meten NER-output per fixture dynamisch (geen hardcoded entiteitsnamen).
  - We verifiëren dat counts in de aggregatie exact overeenkomen met
    de som van de onderliggende NER-resultaten.
  - Waar Jan Hendrickx in meerdere bestanden voorkomt, testen we ook
    de frequentievolgorde (meest frequent = eerst).

Teststrategie:
  - ECHT: run_ner() op fixture-bestanden + echte PostgreSQL.
  - Geen mocks.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - spaCy nl_core_news_lg geladen
"""

from collections import Counter
from pathlib import Path

import pytest
import uuid
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository

FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M3"

BRIEF_JAN_1 = FIXTURE_DIR / "brief_jan_1.txt"
BRIEF_JAN_2 = FIXTURE_DIR / "brief_jan_2.txt"
BRIEF_MARIE = FIXTURE_DIR / "brief_marie.txt"
BRIEF_PIET  = FIXTURE_DIR / "brief_piet.txt"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _insert_archief(session, naam: str):
    archive_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/ner-agg/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    return archive_id, analysis_id


async def _insert_folder(session, archive_id, parent_id=None, naam="map"):
    folder_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, true)
        """),
        {
            "id": str(folder_id), "archive_id": str(archive_id),
            "parent_id": str(parent_id) if parent_id else None,
            "name": naam, "fp": f"/tmp/ner-agg/{archive_id}/{naam}", "rp": naam,
        },
    )
    return folder_id


async def _insert_bestand(session, archive_id, parent_id, naam):
    file_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
        """),
        {
            "id": str(file_id), "archive_id": str(archive_id),
            "parent_id": str(parent_id), "name": naam,
            "fp": f"/tmp/ner-agg/{archive_id}/{naam}", "rp": naam,
        },
    )
    return file_id


def _verwachte_counts(ner_results: list[dict], categorie: str) -> Counter:
    """Berekent verwachte entity-counts als som over meerdere NER-resultaten.

    Elke entiteit draagt count=1 bij per bestand — consistent met persist().
    """
    totaal = Counter()
    for result in ner_results:
        for entity in result[categorie]:
            totaal[entity] += 1
    return totaal


def _assert_aggregatie_klopt(
    geaggregeerd: list[dict],
    verwacht: Counter,
    label: str,
):
    """Verifieert dat de geaggregeerde JSONB-lijst overeenkomt met verwachte counts."""
    geaggregeerd_dict = {item["entity"]: item["count"] for item in geaggregeerd}
    for entity, count in verwacht.items():
        assert entity in geaggregeerd_dict, (
            f"[{label}] '{entity}' ontbreekt in aggregatie: {geaggregeerd_dict}"
        )
        assert geaggregeerd_dict[entity] == count, (
            f"[{label}] '{entity}': verwacht count={count}, "
            f"maar aggregatie geeft {geaggregeerd_dict[entity]}"
        )


# ---------------------------------------------------------------------------
# Casus 1 — map met alleen bestanden
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_alleen_bestanden_echte_ner(committing_db_session):
    """Echte NER op 3 bestanden in één map — aggregatie telt per entiteit
    hoeveel bestanden hem bevatten."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "ner-agg-casus1-echt")
    cleanup_ids.append(archive_id)

    map_id = await _insert_folder(session, archive_id, naam="map")
    fid_1 = await _insert_bestand(session, archive_id, map_id, "brief_jan_1.txt")
    fid_2 = await _insert_bestand(session, archive_id, map_id, "brief_jan_2.txt")
    fid_3 = await _insert_bestand(session, archive_id, map_id, "brief_marie.txt")
    await session.commit()

    repo = NerRepository(session)
    ner_1 = run_ner(BRIEF_JAN_1.read_text(encoding="utf-8"))
    ner_2 = run_ner(BRIEF_JAN_2.read_text(encoding="utf-8"))
    ner_3 = run_ner(BRIEF_MARIE.read_text(encoding="utf-8"))

    await repo.persist(analysis_id, archive_id, map_id, fid_1, ner_1)
    await repo.persist(analysis_id, archive_id, map_id, fid_2, ner_2)
    await repo.persist(analysis_id, archive_id, map_id, fid_3, ner_3)
    await session.commit()

    entities = await repo.get_entities_for_folder(analysis_id, map_id)

    print(f"\n[M3.09/C1] NER per bestand:")
    print(f"  brief_jan_1: persons={ner_1['persons']} locations={ner_1['locations']}")
    print(f"  brief_jan_2: persons={ner_2['persons']} locations={ner_2['locations']}")
    print(f"  brief_marie: persons={ner_3['persons']} locations={ner_3['locations']}")
    print(f"  Aggregatie:  persons={entities['persons']} locations={entities['locations']}")

    verwacht_persons   = _verwachte_counts([ner_1, ner_2, ner_3], "persons")
    verwacht_locations = _verwachte_counts([ner_1, ner_2, ner_3], "locations")

    _assert_aggregatie_klopt(entities["persons"],   verwacht_persons,   "persons")
    _assert_aggregatie_klopt(entities["locations"], verwacht_locations, "locations")

    # Volgorde: meest frequente entiteit staat vooraan
    if len(entities["persons"]) > 1:
        assert entities["persons"][0]["count"] >= entities["persons"][1]["count"], (
            "Persons niet gesorteerd op afnemende frequentie."
        )


# ---------------------------------------------------------------------------
# Casus 2 — map met alleen submappen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_alleen_submappen_echte_ner(committing_db_session):
    """Echte NER op bestanden in twee submappen — root-aggregatie telt de
    gecombineerde counts uit beide subfolder-rijen."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "ner-agg-casus2-echt")
    cleanup_ids.append(archive_id)

    root_id  = await _insert_folder(session, archive_id, naam="root")
    sub_a_id = await _insert_folder(session, archive_id, root_id, naam="sub_a")
    sub_b_id = await _insert_folder(session, archive_id, root_id, naam="sub_b")
    fid_a1 = await _insert_bestand(session, archive_id, sub_a_id, "brief_jan_1.txt")
    fid_a2 = await _insert_bestand(session, archive_id, sub_a_id, "brief_jan_2.txt")
    fid_b1 = await _insert_bestand(session, archive_id, sub_b_id, "brief_marie.txt")
    fid_b2 = await _insert_bestand(session, archive_id, sub_b_id, "brief_piet.txt")
    await session.commit()

    repo = NerRepository(session)
    ner_a1 = run_ner(BRIEF_JAN_1.read_text(encoding="utf-8"))
    ner_a2 = run_ner(BRIEF_JAN_2.read_text(encoding="utf-8"))
    ner_b1 = run_ner(BRIEF_MARIE.read_text(encoding="utf-8"))
    ner_b2 = run_ner(BRIEF_PIET.read_text(encoding="utf-8"))

    await repo.persist(analysis_id, archive_id, sub_a_id, fid_a1, ner_a1)
    await repo.persist(analysis_id, archive_id, sub_a_id, fid_a2, ner_a2)
    await repo.persist(analysis_id, archive_id, sub_b_id, fid_b1, ner_b1)
    await repo.persist(analysis_id, archive_id, sub_b_id, fid_b2, ner_b2)
    await session.commit()

    # Bottom-up: eerst submappen aggregeren
    ent_a = await repo.get_entities_for_folder(analysis_id, sub_a_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_a_id, ent_a)
    ent_b = await repo.get_entities_for_folder(analysis_id, sub_b_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_b_id, ent_b)
    await session.commit()

    # Root aggregeren over de twee subfolder-rijen
    ent_root = await repo.get_entities_for_folder(analysis_id, root_id)

    print(f"\n[M3.09/C2] sub_a persons={ent_a['persons']}")
    print(f"            sub_b persons={ent_b['persons']}")
    print(f"            root  persons={ent_root['persons']}")

    # Verwachte root-counts = som van sub_a en sub_b counts
    verwacht_persons = Counter(
        {item["entity"]: item["count"] for item in ent_a["persons"]}
    ) + Counter(
        {item["entity"]: item["count"] for item in ent_b["persons"]}
    )
    verwacht_locations = Counter(
        {item["entity"]: item["count"] for item in ent_a["locations"]}
    ) + Counter(
        {item["entity"]: item["count"] for item in ent_b["locations"]}
    )

    _assert_aggregatie_klopt(ent_root["persons"],   verwacht_persons,   "persons")
    _assert_aggregatie_klopt(ent_root["locations"], verwacht_locations, "locations")

    if len(ent_root["persons"]) > 1:
        assert ent_root["persons"][0]["count"] >= ent_root["persons"][1]["count"], (
            "Root persons niet gesorteerd op afnemende frequentie."
        )


# ---------------------------------------------------------------------------
# Casus 3 — map met bestanden én submappen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_bestanden_en_submappen_echte_ner(committing_db_session):
    """Echte NER op een map met een direct bestand én een submap — root combineert
    de bestandsbijdrage (count=1) met de gecumuleerde subfolder-counts."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "ner-agg-casus3-echt")
    cleanup_ids.append(archive_id)

    root_id = await _insert_folder(session, archive_id, naam="root")
    sub_id  = await _insert_folder(session, archive_id, root_id, naam="sub")
    fid_direct = await _insert_bestand(session, archive_id, root_id, "brief_jan_1.txt")
    fid_sub_1  = await _insert_bestand(session, archive_id, sub_id, "brief_jan_2.txt")
    fid_sub_2  = await _insert_bestand(session, archive_id, sub_id, "brief_marie.txt")
    await session.commit()

    repo = NerRepository(session)
    ner_direct = run_ner(BRIEF_JAN_1.read_text(encoding="utf-8"))
    ner_sub_1  = run_ner(BRIEF_JAN_2.read_text(encoding="utf-8"))
    ner_sub_2  = run_ner(BRIEF_MARIE.read_text(encoding="utf-8"))

    await repo.persist(analysis_id, archive_id, root_id, fid_direct, ner_direct)
    await repo.persist(analysis_id, archive_id, sub_id,  fid_sub_1,  ner_sub_1)
    await repo.persist(analysis_id, archive_id, sub_id,  fid_sub_2,  ner_sub_2)
    await session.commit()

    # Bottom-up: submap eerst
    ent_sub = await repo.get_entities_for_folder(analysis_id, sub_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_id, ent_sub)
    await session.commit()

    # Root aggregeert: 1 direct bestand + subfolder-rij
    ent_root = await repo.get_entities_for_folder(analysis_id, root_id)

    print(f"\n[M3.09/C3] direct bestand persons={ner_direct['persons']}")
    print(f"            sub           persons={ent_sub['persons']}")
    print(f"            root          persons={ent_root['persons']}")

    # Verwachte root-counts = bestand (count=1 per entiteit) + subfolder-counts
    verwacht_persons = Counter(
        {e: 1 for e in ner_direct["persons"]}
    ) + Counter(
        {item["entity"]: item["count"] for item in ent_sub["persons"]}
    )
    verwacht_locations = Counter(
        {e: 1 for e in ner_direct["locations"]}
    ) + Counter(
        {item["entity"]: item["count"] for item in ent_sub["locations"]}
    )

    _assert_aggregatie_klopt(ent_root["persons"],   verwacht_persons,   "persons")
    _assert_aggregatie_klopt(ent_root["locations"], verwacht_locations, "locations")

    if len(ent_root["persons"]) > 1:
        assert ent_root["persons"][0]["count"] >= ent_root["persons"][1]["count"], (
            "Root persons niet gesorteerd op afnemende frequentie."
        )
