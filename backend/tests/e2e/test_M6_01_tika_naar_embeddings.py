"""M6 — end-to-end: echte Tika-extractie gevolgd door de echte embedding-pijplijn,
in één doorlopende keten (app/perform_tika_analysis/ → app/create_embeddings_for_archive/).

Story: "Levert de volledige pijplijn (echte Tika-extractie → chunken → echte
Ollama-embedding → opslag) voor een archief met 2 bestanden correcte,
juist-geordende embeddings-rijen op, gebaseerd op écht door Tika geëxtraheerde tekst?"

Structuur van het testarchief: zelfde fixtures als de M6.04-integratietest
(tests/testdata/data_M6/), hier hergebruikt om ook de naad met de echte
Tika-extractie mee te testen — niet enkel al-geëxtraheerde tekst die we zelf invoegen.

  root/
  ├── brief_leopold.txt   (48 woorden)
  └── brief_maria.txt     (39 woorden)

Verschil met tests/integration/test_M6_04_embeddings_end_to_end.py: die test slaat
Tika-resultaten rechtstreeks op via TikaRepository.persist() — dus zonder een echte
Tika-aanroep. Deze e2e-test laat PerformTikaAnalysis zelf de echte Tika-server
aanroepen, zodat een breuk in die naad (bv. hoe content genormaliseerd wordt, of een
gewijzigde tika[]-tuple-vorm) hier zichtbaar zou worden — waar M6.04 dat niet dekt.

Teststrategie:
  - ECHT, niets gemocked: PerformTikaAnalysis.execute() haalt bestandsbytes op via de
    échte lokale agent (settings.agent_url) — full_path in de files-tabel wijst naar
    het echte fixture-bestand op schijf, zodat de agent het ook echt kan serveren.
    In tegenstelling tot test_M2_01_tika_normaal_pdf.py (dat de agent-call wél mockt)
    vereist deze test dus dat de agent lokaal bereikbaar is, zie requires_agent.
  - ECHT: PerformTikaAnalysis.execute() → echte Tika-server (TIKA_URL).
  - ECHT: CreateEmbeddingsForArchive.execute() → echte Ollama (settings.ollama_url).
  - Geen no-op op session.commit(): de embedding-fase gebruikt een eigen, aparte
    database-connectie (session_factory) en kan dus enkel zien wat de Tika-fase
    écht gecommit heeft, niet wat enkel geflushed is.
  - settings.embedding_chunk_size / embedding_max_chunks_per_file via monkeypatch
    aangepast — zelfde reden als M6.04: de (bewust korte) fixtures moeten toch
    meerdere chunks opleveren om de chunk_index-ordening te kunnen verifiëren.
  - Cleanup via committing_db_session (DELETE FROM files/archives cascadeert naar
    embeddings resp. archive_analysis dankzij ON DELETE CASCADE).

Vereist:
  - PostgreSQL, Tika en Ollama bereikbaar (docker compose up)
  - De lokale agent bereikbaar op settings.agent_url (losse desktop-component,
    niet onderdeel van docker-compose — moet apart lokaal draaien)
  - settings.embedding_model gepulled in Ollama (`ollama pull qwen3-embedding:0.6b`)
"""

import os
import uuid
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.create_embeddings_for_archive.create_embeddings_for_archive import CreateEmbeddingsForArchive
from app.create_embeddings_for_archive.embedding_engine import chunk_text
from app.create_new_archive.archive_repository import ArchiveRepository
from app.create_new_archive.file_repository import FileRepository as NewArchiveFileRepository
from app.perform_tika_analysis.perform_tika_analysis import PerformTikaAnalysis
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository

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
async def test_tika_naar_embeddings_volledige_keten(
    committing_db_session, requires_tika, requires_ollama, requires_agent, monkeypatch
):
    """Na echte Tika-extractie gevolgd door de embedding-flow moeten er embeddings-rijen
    bestaan met een correcte chunk_index-volgorde, gebaseerd op de écht geëxtraheerde tekst."""
    session, cleanup_ids = committing_db_session

    monkeypatch.setattr(settings, "embedding_chunk_size", 5)
    monkeypatch.setattr(settings, "embedding_max_chunks_per_file", None)

    tika_task_id = uuid.uuid4()
    embedding_task_id = uuid.uuid4()
    run_marker = uuid.uuid4()  # enkel voor een unieke, leesbare root_path — niet het archive_id zelf

    # ── Setup: archief + archive_analysis via de echte repositories i.p.v. ruwe SQL ──
    archive = await ArchiveRepository(session).persist(
        name="tika-naar-embeddings-e2e",
        root_path=f"/tmp/tika-naar-embeddings/{run_marker}",
    )
    archive_id = archive.id

    embedding_analysis = await ArchiveAnalysisRepository(session).create(
        archive_id=archive_id,
        analysis_type="EMBEDDING",
        model=settings.embedding_model,
    )
    embedding_analysis_id = embedding_analysis.id

    # ── Setup: bestand-rijen via de echte FileRepository — nog GEEN tika_analyses,
    # dat doet Tika zo dadelijk zelf. full_path wijst naar het ECHTE fixture-bestand op
    # schijf, zodat de echte lokale agent het straks ook echt kan opvragen (geen mock).
    # persist_all() geeft de gegenereerde id's niet terug, dus die lezen we na de
    # insert terug op (enige overblijvende SELECT in deze setup-fase).
    file_entries = [
        {
            "archive_id": archive_id,
            "name": naam,
            "full_path": str(fixture.resolve()),
            "relative_path": naam,
            "is_directory": False,
        }
        for naam, fixture in [
            ("brief_leopold.txt", BRIEF_LEOPOLD),
            ("brief_maria.txt", BRIEF_MARIA),
        ]
    ]

    await NewArchiveFileRepository(session).persist_all(file_entries)
    await session.commit()
    cleanup_ids.append(archive_id)

    file_rows = (await session.execute(
        text("SELECT id, name FROM files WHERE archive_id = :aid"), {"aid": str(archive_id)}
    )).mappings().all()
    fid_by_name = {row["name"]: row["id"] for row in file_rows}
    fid_leopold = fid_by_name["brief_leopold.txt"]
    fid_maria = fid_by_name["brief_maria.txt"]

    # ── Fase 1: echte Tika-extractie, via de echte lokale agent — niets gemocked ──
    # Geen patch op session.commit(): PerformTikaAnalysis commit hier echt, en
    # de embedding-fase hieronder heeft die echte commit nodig (aparte connectie).
    await PerformTikaAnalysis(session).execute(archive_id, tika_task_id)

    # Sanity check: Tika heeft voor beide bestanden echt bruikbare tekst geëxtraheerd,
    # vóór we verdergaan naar de embedding-fase.
    tika_content_leopold = (await session.execute(
        text("SELECT content, word_count FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(fid_leopold)},
    )).mappings().one()
    tika_content_maria = (await session.execute(
        text("SELECT content, word_count FROM tika_analyses WHERE file_id = :fid"),
        {"fid": str(fid_maria)},
    )).mappings().one()

    assert "Leopold" in tika_content_leopold["content"], (
        f"Tika-extractie voor brief_leopold.txt bevat niet de verwachte tekst: "
        f"{tika_content_leopold['content']!r}"
    )
    assert tika_content_leopold["word_count"] >= 30
    assert "Maria" in tika_content_maria["content"], (
        f"Tika-extractie voor brief_maria.txt bevat niet de verwachte tekst: "
        f"{tika_content_maria['content']!r}"
    )
    assert tika_content_maria["word_count"] >= 30

    # ── Fase 2: echte embedding-flow, met een eigen session_factory ─────────
    engine = create_async_engine(_async_url(), echo=False)
    try:
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        await CreateEmbeddingsForArchive(factory).execute(
            archive_id=archive_id,
            archive_analysis_id=embedding_analysis_id,
            task_id=embedding_task_id,
        )
    finally:
        await engine.dispose()

    # ── Verify: embeddings-rijen per bestand, gebaseerd op de ECHTE Tika-tekst ──
    for fid, tika_content in [
        (fid_leopold, tika_content_leopold["content"]),
        (fid_maria, tika_content_maria["content"]),
    ]:
        verwachte_chunks = chunk_text(tika_content, settings.embedding_chunk_size)
        assert len(verwachte_chunks) > 1, "testopzet moet meerdere chunks opleveren om ordening te testen"

        rows = (await session.execute(
            text("SELECT chunk_index, chunk_text FROM embeddings WHERE file_id = :fid ORDER BY chunk_index"),
            {"fid": str(fid)},
        )).mappings().all()

        gevonden_indices = [r["chunk_index"] for r in rows]
        assert gevonden_indices == list(range(len(verwachte_chunks))), (
            f"chunk_index-volgorde klopt niet voor bestand {fid}: {gevonden_indices}"
        )
        gevonden_teksten = [r["chunk_text"] for r in rows]
        assert gevonden_teksten == verwachte_chunks, (
            f"chunk_text komt niet overeen met chunk_text()-output op de echte Tika-tekst voor {fid}"
        )
