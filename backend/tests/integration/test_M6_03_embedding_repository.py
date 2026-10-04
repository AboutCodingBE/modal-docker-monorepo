"""M6.03 — EmbeddingRepository: het wegschrijven en terugvinden van chunk-embeddings
(app/create_embeddings_for_archive/embedding_repository.py).

Story: "Slaat persist() alle chunks van een bestand correct op, en herkent exists()
achteraf dat een bestand al embed is (resumability-check)?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)

Teststrategie: geen Ollama nodig — we gebruiken een vaste dummy-vector i.p.v. een
echte embedding-aanroep. Deze test gaat over de repository-laag (DB-persistence),
niet over de kwaliteit van de embeddings zelf (dat testen we al in test_M6_02
tegen de echte Ollama-service).
"""

import uuid

import pytest
from sqlalchemy import text

from app.config import settings
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository

# Vaste nep-vector, correcte dimensie zodat de kolomconstraint niet in de weg zit —
# de inhoud van de getallen is voor deze test irrelevant.
DUMMY_VECTOR = [0.1] * settings.embedding_dimension


async def _maak_bestand_aan(async_db_session, archive_id: uuid.UUID, file_id: uuid.UUID) -> None:
    """DB-prerequisites: EmbeddingRepository.persist() verwacht een bestaand files-record
    (FK-integriteit van embeddings.file_id)."""
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "embedding-repository-test", "root_path": f"/tmp/test/{archive_id}"},
    )
    await async_db_session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief_1923.txt",
            "full_path": f"/tmp/test/{archive_id}/brief_1923.txt",
            "relative_path": "brief_1923.txt",
        },
    )
    await async_db_session.flush()


@pytest.mark.asyncio
async def test_exists_geeft_false_als_er_nog_geen_embeddings_zijn(async_db_session):
    """Een vers bestand zonder embeddings moet exists() False laten teruggeven —
    anders zou de flow-controller dit bestand onterecht overslaan."""
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await _maak_bestand_aan(async_db_session, archive_id, file_id)

    bestaat = await EmbeddingRepository(async_db_session).exists(file_id)

    assert bestaat is False


@pytest.mark.asyncio
async def test_persist_slaat_alle_chunks_correct_op(async_db_session):
    """Na persist() met meerdere chunks moeten alle rijen terug te vinden zijn in de
    juiste volgorde, met de juiste tekst en vector — dit is wat de flow-controller
    straks per bestand aanroept."""
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await _maak_bestand_aan(async_db_session, archive_id, file_id)

    chunks = [
        (0, "eerste fragment", DUMMY_VECTOR),
        (1, "tweede fragment", DUMMY_VECTOR),
    ]

    await EmbeddingRepository(async_db_session).persist(file_id, chunks)

    result = await async_db_session.execute(
        text("SELECT chunk_index, chunk_text FROM embeddings WHERE file_id = :file_id ORDER BY chunk_index"),
        {"file_id": str(file_id)},
    )
    rows = result.mappings().all()

    assert [r["chunk_index"] for r in rows] == [0, 1]
    assert [r["chunk_text"] for r in rows] == ["eerste fragment", "tweede fragment"]


@pytest.mark.asyncio
async def test_exists_geeft_true_na_persist(async_db_session):
    """Na een persist() moet exists() True teruggeven — dit is de resumability-check
    die de flow-controller gebruikt om al-verwerkte bestanden over te slaan."""
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    await _maak_bestand_aan(async_db_session, archive_id, file_id)

    await EmbeddingRepository(async_db_session).persist(file_id, [(0, "fragment", DUMMY_VECTOR)])

    bestaat = await EmbeddingRepository(async_db_session).exists(file_id)

    assert bestaat is True
