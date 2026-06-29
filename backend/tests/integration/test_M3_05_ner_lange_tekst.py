"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.05 — NER op een zeer lange tekst.

Story: "Verwerkt NER een zeer lange tekst correct — truncatie of chunking?"

Wat we testen:
  run_ner() splitst lange teksten in chunks van 100.000 tekens (_CHUNK_SIZE)
  en verwerkt ze via nlp.pipe(). De resultaten van alle chunks worden
  samengevoegd en ontdubbeld.

  De test verifieert dat entiteiten uit ZOWEL de eerste als de laatste chunk
  terugkomen in het resultaat. Als de engine na de eerste chunk stopt (truncatie
  in plaats van chunking), ontbreken de entiteiten uit de tweede chunk en
  faalt de test.

  Opbouw van de testtekst (> 100.000 tekens):
    - Chunk 1 (0–99.999): beginzin met "Jan Hendrickx" en "Gent"
    - Chunk 2 (100.000+): eindzin met "Marie Claes" en "Brussel"

Teststrategie:
  - ECHT: run_ner() op inline gegenereerde lange tekst — geen fixture-bestand
    omdat een tekstbestand van 100KB+ onpraktisch is om te committen.
  - ECHT: NerRepository.persist() schrijft naar echte PostgreSQL.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - spaCy nl_core_news_lg geïnstalleerd
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import _CHUNK_SIZE, run_ner
from app.create_ner_for_archive.ner_repository import NerRepository


def _bouw_lange_tekst() -> str:
    """Bouwt een tekst op die groter is dan _CHUNK_SIZE zodat er twee chunks ontstaan.

    Entiteiten in chunk 1: Jan Hendrickx, Gent
    Entiteiten in chunk 2: Marie Claes, Brussel
    """
    # 82 tekens per herhaling × 1250 = 102.500 tekens vulling — meer dan één chunk
    padding = (
        "De archieven bevatten honderden documenten uit de negentiende en twintigste eeuw. "
        * 1250
    )
    assert len(padding) > _CHUNK_SIZE, "padding moet groter zijn dan één chunk"

    return (
        "Jan Hendrickx bezocht Gent in april 1952. "
        + padding
        + " Marie Claes werkte bij Amsab-ISG in Brussel."
    )


@pytest.mark.asyncio
async def test_ner_verwerkt_zeer_lange_tekst_via_chunking_zonder_truncatie(
    committing_db_session,
):
    """Entiteiten uit de eerste én de laatste chunk worden gevonden — geen truncatie."""
    session, cleanup_ids = committing_db_session

    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-lange-tekst", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "lang_document.txt",
            "full_path": f"/tmp/ner-test/{archive_id}/lang_document.txt",
            "relative_path": "lang_document.txt",
        },
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    lange_tekst = _bouw_lange_tekst()
    aantal_chunks = -(-len(lange_tekst) // _CHUNK_SIZE)  # ceiling division
    ner_resultaat = run_ner(lange_tekst)

    print(f"\n[M3.05] Tekstlengte: {len(lange_tekst):,} tekens -> {aantal_chunks} chunks")
    print(f"[M3.05] persons       ({ner_resultaat['persons_count']}): {ner_resultaat['persons']}")
    print(f"[M3.05] locations     ({ner_resultaat['locations_count']}): {ner_resultaat['locations']}")
    print(f"[M3.05] organisations ({ner_resultaat['organisations_count']}): {ner_resultaat['organisations']}")

    # Entiteiten uit chunk 1 (begin van de tekst)
    assert any("Gent" in loc for loc in ner_resultaat["locations"]), (
        f"'Gent' niet gevonden in locations {ner_resultaat['locations']!r}. "
        "Entiteiten uit chunk 1 gaan verloren — mogelijke truncatie."
    )

    # Entiteiten uit chunk 2 (na 100.000 tekens)
    assert any("Brussel" in loc for loc in ner_resultaat["locations"]), (
        f"'Brussel' niet gevonden in locations {ner_resultaat['locations']!r}. "
        "Entiteiten uit chunk 2 gaan verloren — de engine trunceert in plaats van te chunken."
    )

    # Telconsistentie voor alle categorieën — zonder 'or []' masking
    for categorie in ("persons", "locations", "organisations", "misc"):
        lijst = ner_resultaat[categorie]
        count = ner_resultaat[f"{categorie}_count"]
        assert lijst is not None, f"'{categorie}' is None na run_ner() op lange tekst."
        assert count == len(lijst), (
            f"'{categorie}_count' ({count}) ≠ len({lijst!r}) ({len(lijst)})."
        )

    await NerRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        ner_result=ner_resultaat,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT locations FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_locations = rij.scalar()
    print(f"[M3.05] DB locations: {db_locations}")

    assert db_locations is not None and "Gent" in str(db_locations), (
        f"'Gent' niet terug in DB na persist: {db_locations!r}."
    )
    assert "Brussel" in str(db_locations), (
        f"'Brussel' niet terug in DB na persist: {db_locations!r}."
    )
