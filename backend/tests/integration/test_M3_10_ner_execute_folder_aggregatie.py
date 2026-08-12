"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.10 — execute() end-to-end: NER-flow met folder-aggregatie.

Story: "Produceert CreateNerForArchive.execute() na een volledige run zowel
bestand-NER-rijen als folder-aggregatierijen met correcte gecumuleerde counts?"

Structuur van het testarchief:

  root/
  ├── brief_jan_1.txt   (Jan Hendrickx, Gent)
  └── sub/
      ├── brief_jan_2.txt   (Jan Hendrickx, Marie Claes, Gent)
      └── brief_marie.txt   (Marie Claes, Brussel)

Na execute():
  - 3 NER-rijen voor bestanden (file_id = bestand-id)
  - 1 NER-rij voor sub/  (file_id = sub_id,  parent_folder_id = root_id)
  - 1 NER-rij voor root/ (file_id = root_id, parent_folder_id = None)

Assertiestrategie:
  - NER-output per fixture berekend dynamisch via run_ner() — geen hardcoded namen.
  - sub/-counts = som van brief_jan_2 + brief_marie.
  - root/-counts = brief_jan_1 (count=1 per entiteit) + sub/-counts.

Teststrategie:
  - ECHT: CreateNerForArchive.execute() op echte PostgreSQL + spaCy.
  - Aparte session_factory (zoals de echte applicatie) zodat de volledige
    kortlevende-sessie-logica doorgaat.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - spaCy nl_core_news_lg geladen
"""

import os
import uuid
from collections import Counter
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.create_ner_for_archive.create_ner_for_archive import CreateNerForArchive
from app.create_ner_for_archive.ner_engine import run_ner

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
async def test_execute_maakt_bestand_en_folder_ner_rijen(committing_db_session):
    """Na execute() staan er NER-rijen voor elk bestand én voor elke map,
    met counts die correct bottom-up geaggregeerd zijn."""
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
        {"id": str(archive_id), "name": "ner-execute-test",
         "root_path": f"/tmp/ner-exec/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )

    # ── Setup: folderstructuur ────────────────────────────────────────────────
    root_id  = uuid.uuid4()
    sub_id   = uuid.uuid4()
    fid_jan1 = uuid.uuid4()
    fid_jan2 = uuid.uuid4()
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
                "fp": f"/tmp/ner-exec/{archive_id}/{rp}", "rp": rp,
            },
        )

    for fid, parent_id, naam, rp, fixture in [
        (fid_jan1,  root_id, "brief_jan_1.txt", "root/brief_jan_1.txt",       BRIEF_JAN_1),
        (fid_jan2,  sub_id,  "brief_jan_2.txt", "root/sub/brief_jan_2.txt",   BRIEF_JAN_2),
        (fid_marie, sub_id,  "brief_marie.txt", "root/sub/brief_marie.txt",   BRIEF_MARIE),
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
                "fp": f"/tmp/ner-exec/{archive_id}/{rp}", "rp": rp,
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
        await CreateNerForArchive(factory).execute(
            archive_id=archive_id,
            archive_analysis_id=analysis_id,
            task_id=task_id,
            model="nl_core_news_lg",
        )
    finally:
        await engine.dispose()

    # ── Verify: rijen ophalen ─────────────────────────────────────────────────
    rows = (await session.execute(
        text("""
            SELECT file_id, parent_folder_id, persons, locations
            FROM ner
            WHERE archive_id = :aid
        """),
        {"aid": str(archive_id)},
    )).mappings().all()

    file_rows   = [r for r in rows if r["file_id"] in {fid_jan1, fid_jan2, fid_marie}]
    folder_rows = [r for r in rows if r["file_id"] in {root_id, sub_id}]

    print(f"\n[M3.10] Totaal NER-rijen: {len(rows)}")
    print(f"  bestand-rijen : {len(file_rows)}")
    print(f"  folder-rijen  : {len(folder_rows)}")
    for r in folder_rows:
        label = "root" if r["file_id"] == root_id else "sub"
        print(f"  {label}/  persons={r['persons']}")

    assert len(file_rows)   == 3, f"Verwacht 3 bestand-rijen, gevonden {len(file_rows)}"
    assert len(folder_rows) == 2, f"Verwacht 2 folder-rijen (root + sub), gevonden {len(folder_rows)}"

    # ── Verify: sub/ — aggregatie van 2 bestanden ─────────────────────────────
    ner_jan2  = run_ner(BRIEF_JAN_2.read_text(encoding="utf-8"))
    ner_marie = run_ner(BRIEF_MARIE.read_text(encoding="utf-8"))

    sub_row     = next(r for r in folder_rows if r["file_id"] == sub_id)
    sub_persons = {item["entity"]: item["count"] for item in sub_row["persons"]}

    verwacht_sub = Counter()
    for ner in [ner_jan2, ner_marie]:
        for entity in ner["persons"]:
            verwacht_sub[entity] += 1

    for entity, count in verwacht_sub.items():
        assert sub_persons.get(entity) == count, (
            f"sub/ persons[{entity!r}]: verwacht {count}, gevonden {sub_persons.get(entity)}"
        )

    # ── Verify: root/ — bestand + subfolder gecombineerd ─────────────────────
    ner_jan1 = run_ner(BRIEF_JAN_1.read_text(encoding="utf-8"))

    root_row     = next(r for r in folder_rows if r["file_id"] == root_id)
    root_persons = {item["entity"]: item["count"] for item in root_row["persons"]}

    verwacht_root = Counter({e: 1 for e in ner_jan1["persons"]}) + Counter(sub_persons)

    for entity, count in verwacht_root.items():
        assert root_persons.get(entity) == count, (
            f"root/ persons[{entity!r}]: verwacht {count}, gevonden {root_persons.get(entity)}"
        )
