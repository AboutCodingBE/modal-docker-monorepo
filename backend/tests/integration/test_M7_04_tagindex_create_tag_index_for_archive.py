"""M7 — create_tag_index_for_archive: tag_index-tabel vullen vanuit Ner/TopicDetection
(app/create_tag_index_for_archive/).

M7.04 — CreateTagIndexForArchive.execute() end-to-end, voor beide sources.

Story: "Zet CreateTagIndexForArchive.execute() de bestaande Ner- en TopicDetection-rij
van één bestand correct om naar tag_index-rijen, voor zowel source='ner' als
source='topic_detection'?"

Structuur van het testarchief: 1 archief, 1 bestand, met:
  - 1 Ner-rij (eigen analysis_id, type NER) met persons + locations
  - 1 TopicDetection-rij (eigen analysis_id, type TOPIC_DETECTION) met topics

execute() wordt twee keer aangeroepen — eenmaal per source, met de eigen analysis_id
van die analyse (zoals in de echte flow: CreateNerForArchive en
CreateTopicDetectionForArchive roepen dit elk apart aan met hun eigen archive_analysis_id).

Teststrategie:
  - ECHT: CreateTagIndexForArchive.execute() op echte PostgreSQL.
  - Aparte session_factory (zoals de echte applicatie), analoog aan
    test_M3_10_ner_execute_folder_aggregatie.py.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import os
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.create_tag_index_for_archive.create_tag_index_for_archive import CreateTagIndexForArchive


def _async_url() -> str:
    return os.environ.get("DATABASE_URL") or (
        os.environ["DATABASE_URL_SYNC"]
        .replace("postgresql+psycopg://", "postgresql+asyncpg://")
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    )


@pytest.mark.asyncio
async def test_execute_maakt_tag_index_rijen_voor_ner_en_topics(committing_db_session):
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    ner_analysis_id = uuid.uuid4()
    topic_analysis_id = uuid.uuid4()

    # ── Setup: archief + bestand ─────────────────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tagindex-execute-test", "root_path": f"/tmp/tagindex-exec/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief_1958.txt",
            "full_path": f"/tmp/tagindex-exec/{archive_id}/brief_1958.txt",
            "relative_path": "brief_1958.txt",
        },
    )

    # ── Setup: eigen archive_analysis-rij per source ─────────────────────────
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'COMPLETED')
        """),
        {"id": str(ner_analysis_id), "archive_id": str(archive_id)},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'TOPIC_DETECTION', 'gemma3', 'COMPLETED')
        """),
        {"id": str(topic_analysis_id), "archive_id": str(archive_id)},
    )

    # ── Setup: bestaande Ner-rij ──────────────────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO ner (id, archive_id, analysis_id, file_id, persons, locations, organisations, misc)
            VALUES (gen_random_uuid(), :archive_id, :analysis_id, :file_id,
                    :persons, :locations, '[]'::jsonb, '[]'::jsonb)
        """),
        {
            "archive_id": str(archive_id),
            "analysis_id": str(ner_analysis_id),
            "file_id": str(file_id),
            "persons": '[{"entity": "Jan Janssens", "count": 1}]',
            "locations": '[{"entity": "Gent", "count": 1}]',
        },
    )

    # ── Setup: bestaande TopicDetection-rij ──────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO topic_detection (id, archive_id, analysis_id, file_id, topics)
            VALUES (gen_random_uuid(), :archive_id, :analysis_id, :file_id, :topics)
        """),
        {
            "archive_id": str(archive_id),
            "analysis_id": str(topic_analysis_id),
            "file_id": str(file_id),
            "topics": '[{"topic": "belastingen", "count": 1}]',
        },
    )

    await session.commit()
    cleanup_ids.append(archive_id)

    # ── Run: execute() apart voor beide sources, zoals de echte flow ─────────
    engine = create_async_engine(_async_url(), echo=False)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        controller = CreateTagIndexForArchive(factory)
        await controller.execute(archive_id=archive_id, analysis_id=ner_analysis_id, source="ner")
        await controller.execute(archive_id=archive_id, analysis_id=topic_analysis_id, source="topic_detection")
    finally:
        await engine.dispose()

    # ── Verify: tag_index-rijen ───────────────────────────────────────────────
    rows = (await session.execute(
        text("""
            SELECT source, category, value, count
            FROM tag_index
            WHERE archive_id = :aid AND file_id = :fid
            ORDER BY source, category, value
        """),
        {"aid": str(archive_id), "fid": str(file_id)},
    )).mappings().all()

    print(f"\n[M7.04] tag_index-rijen: {[dict(r) for r in rows]}")

    assert len(rows) == 3, f"Verwacht 3 tag_index-rijen (2 ner + 1 topic), gevonden {len(rows)}"

    verwacht = {
        ("ner", "locations", "Gent", 1),
        ("ner", "persons", "Jan Janssens", 1),
        ("topic_detection", None, "belastingen", 1),
    }
    gevonden = {(r["source"], r["category"], r["value"], r["count"]) for r in rows}
    assert gevonden == verwacht
