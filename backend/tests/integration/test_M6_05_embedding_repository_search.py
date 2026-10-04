"""M6.05 — EmbeddingRepository.search(): semantic search via cosine distance
(app/create_embeddings_for_archive/embedding_repository.py).

Story: "Geeft search() de dichtstbijzijnde chunks terug in de juiste volgorde,
respecteert het de top_n-limiet, en sluit het chunks uit andere archieven uit —
zelfs als die objectief een betere match zouden zijn?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)

Teststrategie: geen Ollama nodig — net als test_M6_03 gebruiken we vaste
dummy-vectoren met wiskundig gekende cosine distance t.o.v. de query-vector,
zodat de verwachte volgorde exact vaststaat i.p.v. te moeten gokken:
  - identiek aan de query        → distance 0
  - loodrecht (orthogonaal)      → distance 1
  - exact tegenovergesteld       → distance 2
"""

import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository

DIMENSION = settings.embedding_dimension


def _query_vector() -> list[float]:
    return [1.0] * DIMENSION


def _identical_vector() -> list[float]:
    """Zelfde richting als de query-vector — cosine distance 0."""
    return [1.0] * DIMENSION


def _orthogonal_vector() -> list[float]:
    """Loodrecht op de query-vector (dot product = 0) — cosine distance 1.

    De eerste helft +1, de tweede helft -1: dot product met [1]*DIMENSION is
    (DIMENSION/2 * 1) + (DIMENSION/2 * -1) = 0.
    """
    helft = DIMENSION // 2
    return [1.0] * helft + [-1.0] * (DIMENSION - helft)


def _opposite_vector() -> list[float]:
    """Exact tegenovergesteld aan de query-vector — cosine distance 2 (het maximum)."""
    return [-1.0] * DIMENSION


async def _maak_archief_aan(session, archive_id: uuid.UUID, naam: str) -> None:
    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/search-test/{archive_id}"},
    )
    await session.flush()


async def _maak_bestand_met_embedding_aan(
    session, archive_id: uuid.UUID, file_id: uuid.UUID, naam: str, chunk_text: str, vector: list[float]
) -> None:
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :fp, :rp, false)
        """),
        {
            "id": str(file_id), "archive_id": str(archive_id), "name": naam,
            "fp": f"/tmp/search-test/{archive_id}/{naam}", "rp": naam,
        },
    )
    await session.flush()
    await EmbeddingRepository(session).persist(file_id, [(0, chunk_text, vector)])


@pytest.mark.asyncio
async def test_search_geeft_dichtstbijzijnde_chunks_in_juiste_volgorde(async_db_session):
    """De drie chunks worden in willekeurige volgorde geïnsert, maar search() moet ze
    teruggeven van dichtstbij naar veraf: identiek, dan loodrecht, dan tegenovergesteld."""
    archive_id = uuid.uuid4()
    await _maak_archief_aan(async_db_session, archive_id, "search-volgorde-test")

    # Bewust in een "verkeerde" volgorde geïnsert, om te bewijzen dat search() écht
    # op afstand sorteert en niet toevallig de insert-volgorde teruggeeft.
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "tegenovergesteld.txt", "tegenovergesteld", _opposite_vector()
    )
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "identiek.txt", "identiek", _identical_vector()
    )
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "loodrecht.txt", "loodrecht", _orthogonal_vector()
    )

    resultaten = await EmbeddingRepository(async_db_session).search(
        query_vector=_query_vector(), top_n=3, archive_id=archive_id
    )

    gevonden_volgorde = [r["chunk_text"] for r in resultaten]
    assert gevonden_volgorde == ["identiek", "loodrecht", "tegenovergesteld"], (
        f"verwachte volgorde van dichtstbij naar veraf, kreeg: {gevonden_volgorde}"
    )

    gevonden_afstanden = [r["distance"] for r in resultaten]
    assert gevonden_afstanden == pytest.approx([0.0, 1.0, 2.0], abs=1e-6), (
        f"verwachte cosine distances [0, 1, 2], kreeg: {gevonden_afstanden}"
    )


@pytest.mark.asyncio
async def test_search_respecteert_top_n_limiet(async_db_session):
    """Ook al zijn er 3 kandidaten beschikbaar, met top_n=1 mag er maar 1 resultaat
    terugkomen — en dat moet de best passende zijn."""
    archive_id = uuid.uuid4()
    await _maak_archief_aan(async_db_session, archive_id, "search-top-n-test")

    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "identiek.txt", "identiek", _identical_vector()
    )
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "loodrecht.txt", "loodrecht", _orthogonal_vector()
    )
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_id, uuid.uuid4(), "tegenovergesteld.txt", "tegenovergesteld", _opposite_vector()
    )

    resultaten = await EmbeddingRepository(async_db_session).search(
        query_vector=_query_vector(), top_n=1, archive_id=archive_id
    )

    assert len(resultaten) == 1, f"top_n=1 moet exact 1 resultaat geven, kreeg {len(resultaten)}"
    assert resultaten[0]["chunk_text"] == "identiek"


@pytest.mark.asyncio
async def test_search_filtert_op_archive_id(async_db_session):
    """Een objectief betere match in een ANDER archief mag nooit meekomen — search()
    moet strikt binnen het opgegeven archief blijven, ook als dat een slechtere match
    teruggeeft dan wat er elders beschikbaar zou zijn."""
    archive_a = uuid.uuid4()
    archive_b = uuid.uuid4()
    await _maak_archief_aan(async_db_session, archive_a, "search-archief-a")
    await _maak_archief_aan(async_db_session, archive_b, "search-archief-b")

    # Archief A heeft enkel een matige match (loodrecht, distance 1).
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_a, uuid.uuid4(), "matig.txt", "matige match uit archief A", _orthogonal_vector()
    )
    # Archief B heeft de objectief beste match (identiek, distance 0) — mag niet meekomen.
    await _maak_bestand_met_embedding_aan(
        async_db_session, archive_b, uuid.uuid4(), "beste.txt", "beste match uit archief B", _identical_vector()
    )

    resultaten = await EmbeddingRepository(async_db_session).search(
        query_vector=_query_vector(), top_n=5, archive_id=archive_a
    )

    assert len(resultaten) == 1, f"enkel archief A heeft 1 chunk, kreeg {len(resultaten)} resultaten"
    assert resultaten[0]["chunk_text"] == "matige match uit archief A", (
        "search() heeft een chunk uit het verkeerde archief teruggegeven"
    )
