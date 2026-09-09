"""M6.06 — SearchArchive: use-case die een tekstuele zoekvraag embed en de
best passende chunks binnen één archief teruggeeft (app/search_archive/).

Story: "Als een gebruiker een zoekvraag in gewone taal intikt, vindt
SearchArchive.execute() dan de chunk die er semantisch het dichtst bij ligt —
en blijft die zoekopdracht, net als EmbeddingRepository.search() zelf, binnen
het opgegeven archief?"

Teststrategie: ECHT, geen mocks. SearchArchive roept intern embed() (echte
Ollama-aanroep) en EmbeddingRepository.search() (echte cosine distance in
Postgres) aan. De volgorde/top_n/archief-isolatie-logica van search() zelf is
al uitgebreid getest met vaste dummy-vectoren in test_M6_05 — deze test toetst
enkel de nieuwe laag: dat een écht ingetikte zoekvraag via een écht embedding-
model uitkomt bij de semantisch juiste chunk, en dat de archief-scoping ook
via dit pad standhoudt.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Ollama bereikbaar met settings.embedding_model gepulled
    (`ollama pull qwen3-embedding:0.6b`)
"""

import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
from app.search_archive.search_archive import SearchArchive
from app.shared.ollama_client import embed


async def _maak_archief_aan(session, archive_id: uuid.UUID, naam: str) -> None:
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/search-archive-test/{archive_id}"},
    )
    await session.flush()


async def _maak_bestand_met_echte_embedding_aan(
    session, archive_id: uuid.UUID, naam: str, chunk_text: str
) -> None:
    file_id = uuid.uuid4()
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :fp, :rp, false)
        """),
        {
            "id": str(file_id), "archive_id": str(archive_id), "name": naam,
            "fp": f"/tmp/search-archive-test/{archive_id}/{naam}", "rp": naam,
        },
    )
    await session.flush()
    vector = await embed(settings.embedding_model, chunk_text)
    await EmbeddingRepository(session).persist(file_id, [(0, chunk_text, vector)])


@pytest.mark.asyncio
async def test_execute_vindt_semantisch_dichtstbijzijnde_chunk_binnen_archief(
    async_db_session, requires_ollama
):
    """Een zoekvraag over katten moet uitkomen bij de opgeslagen chunk over een kat,
    niet bij de chunk over de aandelenmarkt — én een objectief betere match in een
    ander archief mag niet meekomen."""
    archive_id = uuid.uuid4()
    ander_archief_id = uuid.uuid4()
    await _maak_archief_aan(async_db_session, archive_id, "search-archive-use-case-test")
    await _maak_archief_aan(async_db_session, ander_archief_id, "search-archive-ander-archief")

    await _maak_bestand_met_echte_embedding_aan(
        async_db_session, archive_id, "kat.txt", "De kat zit op de mat in de woonkamer."
    )
    await _maak_bestand_met_echte_embedding_aan(
        async_db_session, archive_id, "aandelen.txt", "De aandelenkoers steeg met tien procent vandaag."
    )
    # Exacte woordelijke match met de zoekvraag, maar in een ANDER archief — mag nooit meekomen.
    await _maak_bestand_met_echte_embedding_aan(
        async_db_session, ander_archief_id, "poes.txt", "Een poes ligt op het tapijt in de living."
    )

    resultaten = await SearchArchive(async_db_session).execute(
        archive_id=archive_id, query="Een poes ligt op het tapijt in de living.", top_n=5
    )

    assert len(resultaten) == 2, f"beide bestanden uit archive_id moeten meekomen, kreeg {len(resultaten)}"
    assert resultaten[0]["chunk_text"] == "De kat zit op de mat in de woonkamer.", (
        f"verwachtte de kat-chunk als beste match, kreeg: {resultaten[0]['chunk_text']}"
    )
    assert resultaten[0]["distance"] < resultaten[1]["distance"]
