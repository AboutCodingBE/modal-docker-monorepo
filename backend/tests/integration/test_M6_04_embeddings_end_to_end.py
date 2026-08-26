"""M6 — create_embeddings_for_archive: chunkt tekst uit tika_analyses en embed elke
chunk via Ollama, opgeslagen als vector-embeddings (app/create_embeddings_for_archive/).

M6.04 — execute() end-to-end: volledige embedding-flow voor een archief met 2 bestanden.

Story: "Produceert CreateEmbeddingsForArchive.execute() voor elk bestand embeddings-rijen
met een correcte, aaneensluitende chunk_index-volgorde (0, 1, 2, ...) en de juiste
chunk_text — zonder gaten, duplicaten of vermenging tussen bestanden?"

Structuur van het testarchief:

  root/
  ├── brief_leopold.txt   (48 woorden)
  └── brief_maria.txt     (39 woorden)

Teststrategie:
  - ECHT: CreateEmbeddingsForArchive.execute() op echte PostgreSQL + echte Ollama.
    Geen mocks — chunk_text(), embed() en EmbeddingRepository.persist() lopen allemaal
    ongewijzigd, exact zoals in productie.
  - Setup gebruikt TikaRepository(session).persist() i.p.v. een ruwe SQL-insert in
    tika_analyses — zo test deze test ook mee dat de echte Tika-persistence-code
    compatibel blijft met wat de embeddings-flow verwacht, zonder een handmatig
    samengestelde rij die onopgemerkt uit sync kan raken met het echte model. Wat hier
    NIET getest wordt: de echte Tika-extractie zelf (HTTP-call, PDF-parsing) — dat is
    al gedekt in de M2-testreeks. Een echte end-to-end-keten (create_archive → Tika →
    embeddings) zou een apart, trager scenario in tests/e2e/ zijn.
  - Aparte session_factory (zoals de echte applicatie), zodat de kortlevende-sessie-
    logica van de flow-controller effectief doorloopt.
  - settings.embedding_chunk_size en settings.embedding_max_chunks_per_file worden voor
    deze test via monkeypatch aangepast (klein chunk_size, geen cap) zodat de fixture-
    teksten — bewust kort gehouden om de test snel te laten lopen — toch meerdere chunks
    opleveren. Dit is een configuratiewaarde aanpassen, geen mock van de geteste code:
    chunk_text(), embed() en persist() blijven de echte implementaties.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Ollama bereikbaar met settings.embedding_model gepulled
    (`ollama pull qwen3-embedding:0.6b`)
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.create_embeddings_for_archive.create_embeddings_for_archive import CreateEmbeddingsForArchive
from app.create_embeddings_for_archive.embedding_engine import chunk_text
from app.perform_tika_analysis.tika_repository import TikaRepository

FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M6"
BRIEF_LEOPOLD = FIXTURE_DIR / "brief_leopold.txt"
BRIEF_MARIA = FIXTURE_DIR / "brief_maria.txt"


def _async_url() -> str:
    return os.environ.get("DATABASE_URL") or (
        os.environ["DATABASE_URL_SYNC"]
        .replace("postgresql+psycopg://", "postgresql+asyncpg://")
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    )


@pytest.mark.asyncio
async def test_execute_maakt_embeddings_met_correcte_chunk_index_volgorde(
    committing_db_session, requires_ollama, monkeypatch
):
    """Na execute() moet elk bestand embeddings-rijen hebben met chunk_index 0, 1, 2, ...
    (geen gaten/duplicaten), en moet chunk_text exact overeenkomen met chunk_text()'s
    eigen output op de brontekst — dus geen tekst verloren of verkeerd toegewezen."""
    session, cleanup_ids = committing_db_session

    # Klein chunk_size + geen cap: de fixture-teksten zijn bewust kort (voor testsnelheid),
    # maar moeten toch meerdere chunks opleveren om de volgorde-logica echt te testen.
    monkeypatch.setattr(settings, "embedding_chunk_size", 5)
    monkeypatch.setattr(settings, "embedding_max_chunks_per_file", None)

    archive_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    task_id = uuid.uuid4()

    # ── Setup: archief + archive_analysis ────────────────────────────────────
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "embeddings-execute-test",
         "root_path": f"/tmp/embeddings-exec/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'EMBEDDING', :model, 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id), "model": settings.embedding_model},
    )

    # ── Setup: 2 bestanden met echte tekstinhoud uit fixture-bestanden ───────
    fid_leopold = uuid.uuid4()
    fid_maria = uuid.uuid4()

    for fid, naam, fixture in [
        (fid_leopold, "brief_leopold.txt", BRIEF_LEOPOLD),
        (fid_maria, "brief_maria.txt", BRIEF_MARIA),
    ]:
        content = fixture.read_text(encoding="utf-8")
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid), "archive_id": str(archive_id), "name": naam,
                "fp": f"/tmp/embeddings-exec/{archive_id}/{naam}", "rp": naam,
            },
        )
        # Echte TikaRepository.persist() i.p.v. ruwe SQL-insert — zo test deze test ook
        # meteen mee dat de echte insert-code van de Tika-laag compatibel blijft met wat
        # de embeddings-flow verwacht (geen losstaande, handmatig samengestelde rij die
        # onopgemerkt uit sync kan raken met de echte TikaAnalysis-persistence).
        # word_count = echte telling, want get_files_with_tika_content() vereist >= 30.
        await TikaRepository(session).persist(
            file_id=str(fid),
            mime_type="text/plain",
            tika_parser="TXTParser",
            content=content,
            language="nl",
            word_count=len(content.split()),
            author="Onbekend",
            content_created_at=datetime.now(timezone.utc),
        )

    await session.commit()
    cleanup_ids.append(archive_id)

    # ── Run: volledige execute()-flow, met een eigen session_factory ────────
    engine = create_async_engine(_async_url(), echo=False)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await CreateEmbeddingsForArchive(factory).execute(
            archive_id=archive_id,
            archive_analysis_id=analysis_id,
            task_id=task_id,
        )
    finally:
        await engine.dispose()

    # ── Verify: embeddings-rijen per bestand, juiste volgorde en tekst ──────
    for fid, fixture in [(fid_leopold, BRIEF_LEOPOLD), (fid_maria, BRIEF_MARIA)]:
        content = fixture.read_text(encoding="utf-8")
        verwachte_chunks = chunk_text(content, settings.embedding_chunk_size)
        assert len(verwachte_chunks) > 1, "testopzet moet meerdere chunks opleveren om ordering te testen"

        rows = (await session.execute(
            text("""
                SELECT chunk_index, chunk_text
                FROM embeddings
                WHERE file_id = :fid
                ORDER BY chunk_index
            """),
            {"fid": str(fid)},
        )).mappings().all()

        gevonden_indices = [r["chunk_index"] for r in rows]
        assert gevonden_indices == list(range(len(verwachte_chunks))), (
            f"chunk_index-volgorde klopt niet voor bestand {fid}: {gevonden_indices}, "
            f"verwacht 0..{len(verwachte_chunks) - 1}"
        )

        gevonden_teksten = [r["chunk_text"] for r in rows]
        assert gevonden_teksten == verwachte_chunks, (
            f"chunk_text komt niet overeen met chunk_text()-output voor bestand {fid}"
        )
