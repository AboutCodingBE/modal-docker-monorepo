"""Topics — create_topic_detection_for_archive: volledige execute()-flow met
folder-aggregatie (app/create_topic_detection_for_archive/).

test_topic_10 — execute() end-to-end: topic-flow met folder-aggregatie.

Story: "Produceert CreateTopicDetectionForArchive.execute() na een volledige
run zowel bestand-topic-rijen als folder-aggregatierijen?"

Structuur van het testarchief:

  root/
  ├── brief_jan_1.txt   (over archiefoverdracht, Gent)
  └── sub/
      ├── brief_jan_2.txt   (over collectie Amsab-ISG, Gent)
      └── brief_marie.txt   (over Socialistische Partij, Brussel)

Na execute():
  - 3 topic_detection-rijen voor bestanden (file_id = bestand-id)
  - 1 topic_detection-rij voor sub/  (file_id = sub_id)
  - 1 topic_detection-rij voor root/ (file_id = root_id)

Assertiestrategie:
  - Exacte topics zijn Ollama-afhankelijk — geen hardcoded topic-namen.
  - Structureel: juiste aantallen rijen op bestand- en mapniveau.
  - Inhoudelijk: elke topic uit sub/ moet in root/ voorkomen (root accumuleert
    sub via persist_folder).
  - Volgorde: meest frequente topic staat vooraan in elke map.

Teststrategie:
  - ECHT: CreateTopicDetectionForArchive.execute() op echte PostgreSQL + Ollama.
  - Aparte session_factory (zoals de echte applicatie).
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Ollama bereikbaar (OLLAMA_URL in .env)
"""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.create_topic_detection_for_archive.create_topic_detection_for_archive import (
    CreateTopicDetectionForArchive,
)

FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M3"
BRIEF_JAN_1 = FIXTURE_DIR / "brief_jan_1.txt"
BRIEF_JAN_2 = FIXTURE_DIR / "brief_jan_2.txt"
BRIEF_MARIE  = FIXTURE_DIR / "brief_marie.txt"


def _async_url() -> str:
    return os.environ.get("DATABASE_URL") or (
        os.environ["DATABASE_URL_SYNC"]
        .replace("postgresql+psycopg://", "postgresql+asyncpg://")
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    )


@pytest.mark.asyncio
async def test_execute_maakt_bestand_en_folder_topic_rijen(
    committing_db_session, requires_ollama
):
    """Na execute() staan er topic_detection-rijen voor elk bestand én voor
    elke map, en bevatten folder-rijen topics die bottom-up geaggregeerd zijn."""
    session, cleanup_ids = committing_db_session

    archive_id  = uuid.uuid4()
    analysis_id = uuid.uuid4()
    task_id     = uuid.uuid4()

    # ── Setup: archief ────────────────────────────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "topic-execute-test",
         "root_path": f"/tmp/topic-exec/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'TOPIC_DETECTION', 'gemma2:2b', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )

    # ── Setup: folderstructuur ────────────────────────────────────────────────
    root_id   = uuid.uuid4()
    sub_id    = uuid.uuid4()
    fid_jan1  = uuid.uuid4()
    fid_jan2  = uuid.uuid4()
    fid_marie = uuid.uuid4()

    for folder_id, parent_id, naam, rp in [
        (root_id, None,    "root", "root"),
        (sub_id,  root_id, "sub",  "root/sub"),
    ]:
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name,
                                   full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, true)
            """),
            {
                "id": str(folder_id), "archive_id": str(archive_id),
                "parent_id": str(parent_id) if parent_id else None,
                "name": naam,
                "fp": f"/tmp/topic-exec/{archive_id}/{rp}", "rp": rp,
            },
        )

    for fid, parent_id, naam, rp, fixture in [
        (fid_jan1,  root_id, "brief_jan_1.txt", "root/brief_jan_1.txt",     BRIEF_JAN_1),
        (fid_jan2,  sub_id,  "brief_jan_2.txt", "root/sub/brief_jan_2.txt", BRIEF_JAN_2),
        (fid_marie, sub_id,  "brief_marie.txt", "root/sub/brief_marie.txt", BRIEF_MARIE),
    ]:
        content = fixture.read_text(encoding="utf-8")
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name,
                                   full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid), "archive_id": str(archive_id),
                "parent_id": str(parent_id), "name": naam,
                "fp": f"/tmp/topic-exec/{archive_id}/{rp}", "rp": rp,
            },
        )
        # word_count=30 zodat get_files_with_tika_content() de drempel haalt
        await session.execute(
            text("""
                INSERT INTO tika_analyses (id, file_id, content, word_count)
                VALUES (gen_random_uuid(), :file_id, :content, 30)
            """),
            {"file_id": str(fid), "content": content},
        )

    await session.commit()
    cleanup_ids.append(archive_id)

    # ── Run: volledige execute()-flow ─────────────────────────────────────────
    engine = create_async_engine(_async_url(), echo=False)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await CreateTopicDetectionForArchive(factory).execute(
            archive_id=archive_id,
            archive_analysis_id=analysis_id,
            task_id=task_id,
            model="gemma2:2b",
        )
    finally:
        await engine.dispose()

    # ── Verify: rijen ophalen ─────────────────────────────────────────────────
    rows = (await session.execute(
        text("""
            SELECT file_id, parent_folder_id, topics
            FROM topic_detection
            WHERE archive_id = :aid
        """),
        {"aid": str(archive_id)},
    )).mappings().all()

    file_rows   = [r for r in rows if r["file_id"] in {fid_jan1, fid_jan2, fid_marie}]
    folder_rows = [r for r in rows if r["file_id"] in {root_id, sub_id}]

    print(f"\n[topic_10] Totaal topic_detection-rijen: {len(rows)}")
    print(f"  bestand-rijen : {len(file_rows)}")
    print(f"  folder-rijen  : {len(folder_rows)}")
    for r in folder_rows:
        label = "root" if r["file_id"] == root_id else "sub"
        print(f"  {label}/  topics={r['topics']}")

    # ── Verify: structuur ─────────────────────────────────────────────────────
    assert len(file_rows)   == 3, f"Verwacht 3 bestand-rijen, gevonden {len(file_rows)}"
    assert len(folder_rows) == 2, f"Verwacht 2 folder-rijen (root + sub), gevonden {len(folder_rows)}"

    sub_row  = next(r for r in folder_rows if r["file_id"] == sub_id)
    root_row = next(r for r in folder_rows if r["file_id"] == root_id)

    assert len(sub_row["topics"])  > 0, "sub/ heeft geen topics na aggregatie"
    assert len(root_row["topics"]) > 0, "root/ heeft geen topics na aggregatie"

    # ── Verify: root bevat alle topics van sub (bottom-up garantie) ───────────
    sub_topics  = {item["topic"] for item in sub_row["topics"]}
    root_topics = {item["topic"] for item in root_row["topics"]}

    assert sub_topics.issubset(root_topics), (
        f"root/ mist topics die in sub/ staan: {sub_topics - root_topics}. "
        "Dit duidt op een bottom-up aggregatiefout."
    )

    # ── Verify: volgorde aflopend op count ────────────────────────────────────
    if len(root_row["topics"]) > 1:
        assert root_row["topics"][0]["count"] >= root_row["topics"][1]["count"], (
            "root/ topics niet gesorteerd op afnemende frequentie."
        )
