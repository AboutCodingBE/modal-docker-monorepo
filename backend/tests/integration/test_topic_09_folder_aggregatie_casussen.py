"""Topics — create_topic_detection_for_archive: folder-aggregatie van topics
(app/create_topic_detection_for_archive/).

test_topic_09 — Folder-aggregatie: drie opzetcasussen met voorgedefinieerde topics.

Story: "Worden topics correct geaggregeerd ongeacht of een map bestanden,
submappen, of een mix van beide bevat?"

Verschil met NER: topics komen van Ollama (externe service). We gebruiken
hier repo.persist() met voorgedefinieerde topiclijsten — we testen de
aggregatielogica, niet de Ollama-kwaliteit.

De drie casussen:

  Casus 1 — map met alleen bestanden:

    map/
    ├── bestand_a   → topics: ["archief", "correspondentie"]
    ├── bestand_b   → topics: ["archief", "overdracht"]
    └── bestand_c   → topics: ["correspondentie", "Gent"]

    Verwacht: archief=2, correspondentie=2, overdracht=1, Gent=1

  Casus 2 — map met alleen submappen (geen directe bestanden):

    root/
    ├── sub_a/
    │   ├── bestand_a   → topics: ["archief", "correspondentie"]
    │   └── bestand_b   → topics: ["archief", "overdracht"]
    └── sub_b/
        ├── bestand_c   → topics: ["correspondentie", "Gent"]
        └── bestand_d   → topics: ["overdracht", "Brussel"]

    Verwacht: root = som van sub_a-counts + sub_b-counts

  Casus 3 — map met zowel bestanden als submappen:

    root/
    ├── bestand_a   → topics: ["archief"]
    └── sub/
        ├── bestand_b   → topics: ["archief", "correspondentie"]
        └── bestand_c   → topics: ["correspondentie", "Gent"]

    Verwacht: root = bestand_a (count=1 per topic) + sub-counts

Assertiestrategie:
  - Verwachte counts berekend als Counter over de ingevoerde topiclijsten.
  - Geaggregeerde JSONB-output vergeleken met verwachte counts.
  - Volgorde: meest frequente topic staat vooraan.

Teststrategie:
  - ECHT: TopicDetectionRepository op echte PostgreSQL.
  - Geen Ollama nodig.
  - Cleanup via committing_db_session.
"""

import uuid
from collections import Counter

import pytest
from sqlalchemy import text

from app.create_topic_detection_for_archive.topic_detection_repository import TopicDetectionRepository


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
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/topic-agg/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'TOPIC_DETECTION', 'gemma2:2b', 'STARTED')
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
            "name": naam, "fp": f"/tmp/topic-agg/{archive_id}/{naam}", "rp": naam,
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
            "fp": f"/tmp/topic-agg/{archive_id}/{naam}", "rp": naam,
        },
    )
    return file_id


def _verwachte_counts(topics_per_bestand: list[list[str]]) -> Counter:
    """Berekent verwachte topic-counts als som over meerdere bestandslijsten.

    Elke topic draagt count=1 bij per bestand — consistent met persist().
    """
    totaal = Counter()
    for topics in topics_per_bestand:
        for topic in topics:
            totaal[topic] += 1
    return totaal


def _assert_aggregatie_klopt(geaggregeerd: list[dict], verwacht: Counter, label: str):
    """Verifieert dat de geaggregeerde JSONB-lijst overeenkomt met verwachte counts."""
    geaggregeerd_dict = {item["topic"]: item["count"] for item in geaggregeerd}
    for topic, count in verwacht.items():
        assert topic in geaggregeerd_dict, (
            f"[{label}] '{topic}' ontbreekt in aggregatie: {geaggregeerd_dict}"
        )
        assert geaggregeerd_dict[topic] == count, (
            f"[{label}] '{topic}': verwacht count={count}, "
            f"maar aggregatie geeft {geaggregeerd_dict[topic]}"
        )


# ---------------------------------------------------------------------------
# Casus 1 — map met alleen bestanden
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_alleen_bestanden(committing_db_session):
    """Aggregatie over 3 bestanden in één map — topics die in meerdere
    bestanden voorkomen krijgen een hogere count."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "topic-agg-casus1")
    cleanup_ids.append(archive_id)

    map_id = await _insert_folder(session, archive_id, naam="map")
    fid_a = await _insert_bestand(session, archive_id, map_id, "bestand_a.txt")
    fid_b = await _insert_bestand(session, archive_id, map_id, "bestand_b.txt")
    fid_c = await _insert_bestand(session, archive_id, map_id, "bestand_c.txt")
    await session.commit()

    topics_a = ["archief", "correspondentie"]
    topics_b = ["archief", "overdracht"]
    topics_c = ["correspondentie", "Gent"]

    repo = TopicDetectionRepository(session)
    await repo.persist(analysis_id, archive_id, map_id, fid_a, topics_a)
    await repo.persist(analysis_id, archive_id, map_id, fid_b, topics_b)
    await repo.persist(analysis_id, archive_id, map_id, fid_c, topics_c)
    await session.commit()

    geaggregeerd = await repo.get_topics_for_folder(analysis_id, map_id)

    print(f"\n[topic_09/C1] Aggregatie: {geaggregeerd}")

    verwacht = _verwachte_counts([topics_a, topics_b, topics_c])
    _assert_aggregatie_klopt(geaggregeerd, verwacht, "topics")

    if len(geaggregeerd) > 1:
        assert geaggregeerd[0]["count"] >= geaggregeerd[1]["count"], (
            "Topics niet gesorteerd op afnemende frequentie."
        )


# ---------------------------------------------------------------------------
# Casus 2 — map met alleen submappen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_alleen_submappen(committing_db_session):
    """Aggregatie over twee submappen — root-counts = som van sub_a + sub_b counts."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "topic-agg-casus2")
    cleanup_ids.append(archive_id)

    root_id  = await _insert_folder(session, archive_id, naam="root")
    sub_a_id = await _insert_folder(session, archive_id, root_id, naam="sub_a")
    sub_b_id = await _insert_folder(session, archive_id, root_id, naam="sub_b")
    fid_a = await _insert_bestand(session, archive_id, sub_a_id, "bestand_a.txt")
    fid_b = await _insert_bestand(session, archive_id, sub_a_id, "bestand_b.txt")
    fid_c = await _insert_bestand(session, archive_id, sub_b_id, "bestand_c.txt")
    fid_d = await _insert_bestand(session, archive_id, sub_b_id, "bestand_d.txt")
    await session.commit()

    topics_a = ["archief", "correspondentie"]
    topics_b = ["archief", "overdracht"]
    topics_c = ["correspondentie", "Gent"]
    topics_d = ["overdracht", "Brussel"]

    repo = TopicDetectionRepository(session)
    await repo.persist(analysis_id, archive_id, sub_a_id, fid_a, topics_a)
    await repo.persist(analysis_id, archive_id, sub_a_id, fid_b, topics_b)
    await repo.persist(analysis_id, archive_id, sub_b_id, fid_c, topics_c)
    await repo.persist(analysis_id, archive_id, sub_b_id, fid_d, topics_d)
    await session.commit()

    # Bottom-up: eerst submappen aggregeren
    ent_a = await repo.get_topics_for_folder(analysis_id, sub_a_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_a_id, ent_a)
    ent_b = await repo.get_topics_for_folder(analysis_id, sub_b_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_b_id, ent_b)
    await session.commit()

    ent_root = await repo.get_topics_for_folder(analysis_id, root_id)

    print(f"\n[topic_09/C2] sub_a={ent_a}")
    print(f"              sub_b={ent_b}")
    print(f"              root ={ent_root}")

    verwacht = Counter(
        {item["topic"]: item["count"] for item in ent_a}
    ) + Counter(
        {item["topic"]: item["count"] for item in ent_b}
    )

    _assert_aggregatie_klopt(ent_root, verwacht, "topics")

    if len(ent_root) > 1:
        assert ent_root[0]["count"] >= ent_root[1]["count"], (
            "Root topics niet gesorteerd op afnemende frequentie."
        )


# ---------------------------------------------------------------------------
# Casus 3 — map met bestanden én submappen
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_aggregatie_map_met_bestanden_en_submappen(committing_db_session):
    """Aggregatie over een direct bestand én een submap — root combineert
    bestandsbijdrage (count=1) met gecumuleerde subfolder-counts."""
    session, cleanup_ids = committing_db_session
    archive_id, analysis_id = await _insert_archief(session, "topic-agg-casus3")
    cleanup_ids.append(archive_id)

    root_id = await _insert_folder(session, archive_id, naam="root")
    sub_id  = await _insert_folder(session, archive_id, root_id, naam="sub")
    fid_direct = await _insert_bestand(session, archive_id, root_id, "bestand_a.txt")
    fid_sub_b  = await _insert_bestand(session, archive_id, sub_id, "bestand_b.txt")
    fid_sub_c  = await _insert_bestand(session, archive_id, sub_id, "bestand_c.txt")
    await session.commit()

    topics_direct = ["archief"]
    topics_sub_b  = ["archief", "correspondentie"]
    topics_sub_c  = ["correspondentie", "Gent"]

    repo = TopicDetectionRepository(session)
    await repo.persist(analysis_id, archive_id, root_id, fid_direct, topics_direct)
    await repo.persist(analysis_id, archive_id, sub_id,  fid_sub_b,  topics_sub_b)
    await repo.persist(analysis_id, archive_id, sub_id,  fid_sub_c,  topics_sub_c)
    await session.commit()

    # Bottom-up: submap eerst
    ent_sub = await repo.get_topics_for_folder(analysis_id, sub_id)
    await repo.persist_folder(analysis_id, archive_id, root_id, sub_id, ent_sub)
    await session.commit()

    ent_root = await repo.get_topics_for_folder(analysis_id, root_id)

    print(f"\n[topic_09/C3] direct={topics_direct}")
    print(f"              sub   ={ent_sub}")
    print(f"              root  ={ent_root}")

    verwacht = Counter(
        {t: 1 for t in topics_direct}
    ) + Counter(
        {item["topic"]: item["count"] for item in ent_sub}
    )

    _assert_aggregatie_klopt(ent_root, verwacht, "topics")

    if len(ent_root) > 1:
        assert ent_root[0]["count"] >= ent_root[1]["count"], (
            "Root topics niet gesorteerd op afnemende frequentie."
        )
