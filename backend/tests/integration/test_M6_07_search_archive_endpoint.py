"""M6.07 — GET /api/archives/{archive_id}/search: het HTTP-endpoint rond
SearchArchive (app/search_archive/router.py).

Story: "Geeft het endpoint de semantisch juiste resultaten terug voor een
zoekvraag in de querystring, en antwoordt het met 404 voor een archief dat
niet bestaat — in plaats van een lege lijst, wat een echte 'niet gevonden'
zou verdoezelen als een archief zonder resultaten?"

Teststrategie: ECHT, geen mocks. Roept het endpoint aan via FastAPI's
TestClient (dus ook routing/query-param-validatie loopt echt mee), tegen de
echte PostgreSQL- en Ollama-diensten — dezelfde services als de rest van de
M6-reeks.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - Ollama bereikbaar met settings.embedding_model gepulled
    (`ollama pull qwen3-embedding:0.6b`)
"""

import asyncio
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
from app.main import app
from app.shared import database
from app.shared.ollama_client import embed

client = TestClient(app)


@pytest.fixture(autouse=True)
def _dispose_app_db_engine_na_test():
    """TestClient draait elke aanroep in zijn eigen event loop, maar app.shared.database.engine
    is één globale connection pool over alle tests heen — een pooled asyncpg-connectie die aan
    de loop van test N hangt, breekt in test N+1's andere loop ("attached to a different loop").
    Dispose na elke test zodat de volgende met verse connecties in zijn eigen loop begint."""
    yield
    asyncio.run(database.engine.dispose())


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
            "fp": f"/tmp/search-endpoint-test/{archive_id}/{naam}", "rp": naam,
        },
    )
    vector = await embed(settings.embedding_model, chunk_text)
    await EmbeddingRepository(session).persist(file_id, [(0, chunk_text, vector)])


@pytest.mark.asyncio
async def test_get_search_geeft_semantisch_beste_match_terug(committing_db_session, requires_ollama):
    """Een GET met ?q=... moet de opgeslagen chunk teruggeven die er semantisch het
    dichtst bij ligt, inclusief metadata en distance, met HTTP 200."""
    session, cleanup_ids = committing_db_session
    archive_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "search-endpoint-test", "root_path": f"/tmp/search-endpoint-test/{archive_id}"},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    await _maak_bestand_met_echte_embedding_aan(
        session, archive_id, "kat.txt", "De kat zit op de mat in de woonkamer."
    )
    await _maak_bestand_met_echte_embedding_aan(
        session, archive_id, "aandelen.txt", "De aandelenkoers steeg met tien procent vandaag."
    )
    await session.commit()

    response = client.get(
        f"/api/archives/{archive_id}/search",
        params={"q": "Een poes ligt op het tapijt in de living.", "top_n": 5},
    )

    assert response.status_code == 200, response.text
    resultaten = response.json()
    assert len(resultaten) == 2, f"beide bestanden moeten meekomen, kreeg {len(resultaten)}"
    assert resultaten[0]["chunk_text"] == "De kat zit op de mat in de woonkamer.", (
        f"verwachtte de kat-chunk als beste match, kreeg: {resultaten[0]['chunk_text']}"
    )
    assert resultaten[0]["distance"] < resultaten[1]["distance"]


def test_get_search_geeft_404_voor_onbestaand_archief():
    """Een archive_id dat niet bestaat moet 404 geven, geen lege lijst — anders is
    'archief bestaat niet' niet te onderscheiden van 'archief bestaat, geen match'."""
    onbestaand_archief_id = uuid.uuid4()

    response = client.get(
        f"/api/archives/{onbestaand_archief_id}/search",
        params={"q": "irrelevante zoekvraag"},
    )

    assert response.status_code == 404
