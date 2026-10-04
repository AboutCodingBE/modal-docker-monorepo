"""M6.01 — schema-validatie van de `embeddings`-tabel (migraties 0016/0017).

Test welke garanties de database zelf afdwingt voor `embeddings`, de tabel die
tekstfragmenten (chunks) en hun vector-embeddings opslaat voor semantic search:
- de vector-kolom accepteert en bewaart een geldige 1024-dimensionale vector correct
- de vector-kolom weigert een vector met een andere dimensie (data-integriteit:
  settings.embedding_dimension moet overeenkomen met de kolomdefinitie)
- de unique-constraint (file_id, chunk_index) voorkomt dubbele chunks per bestand
- ON DELETE CASCADE ruimt embeddings automatisch op wanneer het bronbestand verdwijnt

Vereiste services: enkel de PostgreSQL-database (`docker compose up db`).
"""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DataError, IntegrityError


@pytest.fixture()
def file_prerequisite(db_conn):
    """Legt een minimaal archive + file record aan, zodat embeddings.file_id een geldige FK heeft.

    Gebruikt dezelfde SAVEPOINT-aanpak als `ner_prerequisites` in conftest.py: de rijen
    worden na de test teruggedraaid tot dit punt, zodat de database leeg blijft.
    """
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()

    db_conn.execute(text("""
        INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
        VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
    """), {"id": str(archive_id), "name": "test-archief", "root_path": f"/tmp/test/{archive_id}"})

    db_conn.execute(text("""
        INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
        VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
    """), {
        "id": str(file_id),
        "archive_id": str(archive_id),
        "name": "brief_1923.txt",
        "full_path": f"/tmp/test/{archive_id}/brief_1923.txt",
        "relative_path": "brief_1923.txt",
    })

    db_conn.execute(text("SAVEPOINT prereqs"))
    yield file_id
    db_conn.execute(text("ROLLBACK TO SAVEPOINT prereqs"))


def _vector_literal(value: float, dimension: int) -> str:
    """Bouwt een pgvector-literal, bv. '[0.1,0.1,...]' met exact `dimension` waarden."""
    return "[" + ",".join([str(value)] * dimension) + "]"


def test_embeddings_tabel_accepteert_en_bewaart_geldige_rij(db_conn, file_prerequisite):
    """Een insert met een 1024-dimensionale vector moet slagen en exact zo terug te lezen zijn."""
    file_id = file_prerequisite
    vector = _vector_literal(0.5, 1024)

    db_conn.execute(text("""
        INSERT INTO embeddings (id, file_id, chunk_index, chunk_text, token_count, embedding)
        VALUES (:id, :file_id, 0, 'testfragment', 3, :embedding)
    """), {"id": str(uuid.uuid4()), "file_id": str(file_id), "embedding": vector})

    result = db_conn.execute(text(
        "SELECT chunk_text, token_count, embedding FROM embeddings WHERE file_id = :file_id"
    ), {"file_id": str(file_id)}).fetchone()

    assert result is not None, "de insert had een rij moeten opleveren"
    assert result.chunk_text == "testfragment"
    assert result.token_count == 3
    # pgvector geeft de kolom terug als string "[0.5,0.5,...]" — vergelijk met wat werd opgeslagen.
    assert result.embedding == vector, "de teruggelezen vector wijkt af van wat werd opgeslagen"


def test_embeddings_tabel_weigert_verkeerde_vector_dimensie(db_conn, file_prerequisite):
    """De vector-kolom ligt vast op 1024 dimensies (zie settings.embedding_dimension in
    app/config.py). Een vector met een andere lengte moet de database weigeren — anders
    zou een modelwissel met afwijkende dimensie stilzwijgend corrupte data opleveren."""
    file_id = file_prerequisite
    verkeerde_vector = _vector_literal(0.5, 512)

    with pytest.raises(DataError):
        db_conn.execute(text("""
            INSERT INTO embeddings (id, file_id, chunk_index, chunk_text, embedding)
            VALUES (:id, :file_id, 0, 'testfragment', :embedding)
        """), {"id": str(uuid.uuid4()), "file_id": str(file_id), "embedding": verkeerde_vector})


def test_embeddings_tabel_weigert_duplicate_chunk_index_per_bestand(db_conn, file_prerequisite):
    """De unique-constraint uq_embeddings_file_id_chunk_index moet een tweede chunk met
    dezelfde index voor hetzelfde bestand weigeren — anders kan een fragment per ongeluk
    dubbel embed worden (bv. bij een herhaalde/parallelle embed-run)."""
    file_id = file_prerequisite
    vector = _vector_literal(0.1, 1024)

    db_conn.execute(text("""
        INSERT INTO embeddings (id, file_id, chunk_index, chunk_text, embedding)
        VALUES (:id, :file_id, 0, 'eerste fragment', :embedding)
    """), {"id": str(uuid.uuid4()), "file_id": str(file_id), "embedding": vector})

    with pytest.raises(IntegrityError):
        db_conn.execute(text("""
            INSERT INTO embeddings (id, file_id, chunk_index, chunk_text, embedding)
            VALUES (:id, :file_id, 0, 'tweede fragment met dezelfde index', :embedding)
        """), {"id": str(uuid.uuid4()), "file_id": str(file_id), "embedding": vector})


def test_embeddings_worden_cascaded_verwijderd_met_bronbestand(db_conn, file_prerequisite):
    """ON DELETE CASCADE op file_id moet embeddings automatisch opruimen wanneer het
    bronbestand verwijderd wordt — anders blijven wees-embeddings achter die bij een
    latere zoekopdracht naar een niet-bestaand bestand zouden verwijzen."""
    file_id = file_prerequisite
    vector = _vector_literal(0.1, 1024)

    db_conn.execute(text("""
        INSERT INTO embeddings (id, file_id, chunk_index, chunk_text, embedding)
        VALUES (:id, :file_id, 0, 'fragment', :embedding)
    """), {"id": str(uuid.uuid4()), "file_id": str(file_id), "embedding": vector})

    db_conn.execute(text("DELETE FROM files WHERE id = :file_id"), {"file_id": str(file_id)})

    resterend = db_conn.execute(text(
        "SELECT COUNT(*) FROM embeddings WHERE file_id = :file_id"
    ), {"file_id": str(file_id)}).scalar()

    assert resterend == 0, "embeddings van een verwijderd bestand hadden mee verwijderd moeten worden"
