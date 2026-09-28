"""M7 — create_tag_index_for_archive: tag_index-tabel vullen vanuit Ner/TopicDetection
(app/create_tag_index_for_archive/).

M7.05 — redo-cyclus: NER draaien, opnieuw draaien, tag_index moet correct herbouwd worden.

Story: "Als NER opnieuw gedraaid wordt voor een archief (redo), bevat tag_index dan
enkel de rijen van de nieuwe analysis_id — geen duplicaten en geen verweesde rijen
van de oude analysis_id?"

Simuleert de echte redo-flow:
  1. Eerste NER-run: archive_analysis (analysis_id_1) + ner-rij + tag_index vullen.
  2. Redo: archive_analysis-rij verwijderen (zoals ArchiveAnalysisRepository.delete_existing()
     doet) — CASCADE ruimt de ner- én tag_index-rijen van analysis_id_1 op
     (dat mechanisme is al apart bewezen in test_M7_02_tagindex_cascade_bij_redo.py).
  3. Tweede NER-run: nieuwe archive_analysis (analysis_id_2) + nieuwe ner-rij +
     tag_index opnieuw vullen.

Teststrategie:
  - ECHT: CreateTagIndexForArchive.execute() op echte PostgreSQL, geen spaCy nodig —
    we testen het redo-gedrag van de tag_index-laag, niet de NER-engine zelf
    (analoog aan test_M3_03_ner_dubbele_run.py, dat ook rechtstreeks persist() gebruikt).
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


async def _insert_archive_analysis(session, archive_id: uuid.UUID) -> uuid.UUID:
    analysis_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'COMPLETED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    return analysis_id


async def _insert_ner_row(session, archive_id: uuid.UUID, analysis_id: uuid.UUID, file_id: uuid.UUID) -> None:
    await session.execute(
        text("""
            INSERT INTO ner (id, archive_id, analysis_id, file_id, persons, locations, organisations, misc)
            VALUES (gen_random_uuid(), :archive_id, :analysis_id, :file_id,
                    :persons, '[]'::jsonb, '[]'::jsonb, '[]'::jsonb)
        """),
        {
            "archive_id": str(archive_id),
            "analysis_id": str(analysis_id),
            "file_id": str(file_id),
            "persons": '[{"entity": "Jan Janssens", "count": 1}]',
        },
    )


@pytest.mark.asyncio
async def test_redo_herbouwt_tag_index_zonder_duplicaten_of_wezen(committing_db_session):
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tagindex-redo-test", "root_path": f"/tmp/tagindex-redo/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief_1961.txt",
            "full_path": f"/tmp/tagindex-redo/{archive_id}/brief_1961.txt",
            "relative_path": "brief_1961.txt",
        },
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    engine = create_async_engine(_async_url(), echo=False)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        controller = CreateTagIndexForArchive(factory)

        # ── Eerste run ────────────────────────────────────────────────────────
        analysis_id_1 = await _insert_archive_analysis(session, archive_id)
        await _insert_ner_row(session, archive_id, analysis_id_1, file_id)
        await session.commit()

        await controller.execute(archive_id=archive_id, analysis_id=analysis_id_1, source="ner")

        rows_na_eerste_run = (await session.execute(
            text("SELECT COUNT(*) FROM tag_index WHERE archive_id = :aid"), {"aid": str(archive_id)}
        )).scalar()
        assert rows_na_eerste_run == 1, f"Verwacht 1 tag_index-rij na eerste run, gevonden {rows_na_eerste_run}"

        # ── Redo: archive_analysis-rij weg (CASCADE ruimt ner + tag_index op) ──
        await session.execute(
            text("DELETE FROM archive_analysis WHERE id = :id"), {"id": str(analysis_id_1)}
        )
        await session.commit()

        # ── Tweede run — nieuwe analysis_id, zelfde entiteit gevonden ──────────
        analysis_id_2 = await _insert_archive_analysis(session, archive_id)
        await _insert_ner_row(session, archive_id, analysis_id_2, file_id)
        await session.commit()

        await controller.execute(archive_id=archive_id, analysis_id=analysis_id_2, source="ner")
    finally:
        await engine.dispose()

    # ── Verify ─────────────────────────────────────────────────────────────────
    rows = (await session.execute(
        text("SELECT analysis_id, value FROM tag_index WHERE archive_id = :aid"),
        {"aid": str(archive_id)},
    )).mappings().all()

    print(f"\n[M7.05] tag_index-rijen na redo: {[dict(r) for r in rows]}")

    verweesde_rijen = [r for r in rows if str(r["analysis_id"]) == str(analysis_id_1)]
    assert not verweesde_rijen, f"Verweesde tag_index-rijen van de oude analysis_id_1 gevonden: {verweesde_rijen}"

    assert len(rows) == 1, f"Verwacht 1 tag_index-rij na redo (geen duplicaten), gevonden {len(rows)}"
    assert str(rows[0]["analysis_id"]) == str(analysis_id_2)
    assert rows[0]["value"] == "Jan Janssens"
