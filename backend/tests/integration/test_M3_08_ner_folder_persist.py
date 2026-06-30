"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.08 — NerRepository.persist_folder(): opslag van folder-niveau aggregaties.

Story: "Wordt een folder-NER-rij correct aangemaakt met namen, counts en
frequency-dicts, en sluit top_n de juiste entiteiten in?"

Wat we testen:
  1. Folder met entiteiten in meerdere categorieën: persons + locations worden
     correct opgesplitst in namen (ARRAY), counts (integer) en frequencies (JSONB).
  2. Folder zonder NER-data (geen bestandsrijen): lege arrays worden opgeslagen,
     geen NULLs.
  3. top_n truncatie: van 5 personen worden enkel de top 2 opgeslagen, in
     afdalende frequentievolgorde.

Teststrategie:
  - ECHT: NerRepository.persist() + persist_folder() + get_entities_for_folder()
    op echte PostgreSQL.
  - Geen mocks van private methodes.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_repository import NerRepository


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ner(
    persons: list[str] = (),
    locations: list[str] = (),
    organisations: list[str] = (),
    misc: list[str] = (),
) -> dict:
    persons = list(persons)
    locations = list(locations)
    organisations = list(organisations)
    misc = list(misc)
    return {
        "persons": persons, "persons_count": len(persons),
        "locations": locations, "locations_count": len(locations),
        "organisations": organisations, "organisations_count": len(organisations),
        "misc": misc, "misc_count": len(misc),
    }


async def _setup_archief(session, cleanup_ids, naam: str, n_bestanden: int = 1):
    """Maakt een archief met één map en n bestanden aan. Geeft IDs terug."""
    archive_id = uuid.uuid4()
    folder_id = uuid.uuid4()
    file_ids = [uuid.uuid4() for _ in range(n_bestanden)]
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'map', :fp, 'map', true)
        """),
        {"id": str(folder_id), "archive_id": str(archive_id), "fp": f"/tmp/ner-test/{archive_id}/map"},
    )
    for i, fid in enumerate(file_ids):
        naam_bestand = f"brief_{i + 1}.txt"
        await session.execute(
            text("""
                INSERT INTO files (id, archive_id, parent_id, name, full_path, relative_path, is_directory)
                VALUES (:id, :archive_id, :parent_id, :name, :fp, :rp, false)
            """),
            {
                "id": str(fid),
                "archive_id": str(archive_id),
                "parent_id": str(folder_id),
                "name": naam_bestand,
                "fp": f"/tmp/ner-test/{archive_id}/map/{naam_bestand}",
                "rp": f"map/{naam_bestand}",
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

    return archive_id, folder_id, file_ids, analysis_id


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_persist_folder_slaat_namen_counts_en_frequencies_op(committing_db_session):
    """persist_folder() slaat persons + locations correct op in alle drie kolom-types:
    ARRAY met namen, integer count, en JSONB frequency-lijst."""
    session, cleanup_ids = committing_db_session
    archive_id, folder_id, file_ids, analysis_id = await _setup_archief(
        session, cleanup_ids, "ner-test-folder-persist-multi", n_bestanden=2
    )

    repo = NerRepository(session)
    await repo.persist(
        analysis_id, archive_id, folder_id, file_ids[0],
        _ner(persons=["Jan Hendrickx", "Marie Claes"], locations=["Gent"]),
    )
    await repo.persist(
        analysis_id, archive_id, folder_id, file_ids[1],
        _ner(persons=["Jan Hendrickx"], locations=["Gent", "Brussel"]),
    )
    await session.commit()

    entities = await repo.get_entities_for_folder(analysis_id, folder_id)
    await repo.persist_folder(analysis_id, archive_id, None, folder_id, entities)
    await session.commit()

    rij = (await session.execute(
        text("SELECT * FROM ner WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(folder_id), "aid": str(analysis_id)},
    )).mappings().one()

    print(f"\n[M3.08] Folder NER-rij: persons={rij['persons']}  "
          f"persons_count={rij['persons_count']}  persons_frequencies={rij['persons_frequencies']}")
    print(f"        locations={rij['locations']}  locations_count={rij['locations_count']}")

    # file_id == folder_id is de folder-conventie
    assert str(rij["file_id"]) == str(folder_id)

    # Persons: Jan 2x, Marie 1x (gesorteerd)
    assert rij["persons"] == ["Jan Hendrickx", "Marie Claes"]
    assert rij["persons_count"] == 2
    assert rij["persons_frequencies"][0] == {"entity": "Jan Hendrickx", "count": 2}
    assert rij["persons_frequencies"][1] == {"entity": "Marie Claes", "count": 1}

    # Locations: Gent 2x, Brussel 1x
    assert rij["locations"] == ["Gent", "Brussel"]
    assert rij["locations_count"] == 2
    assert rij["locations_frequencies"][0] == {"entity": "Gent", "count": 2}
    assert rij["locations_frequencies"][1] == {"entity": "Brussel", "count": 1}

    # Lege categorieën: lege arrays, geen NULL
    assert rij["organisations"] == []
    assert rij["organisations_count"] == 0
    assert rij["organisations_frequencies"] == []


@pytest.mark.asyncio
async def test_persist_folder_zonder_ner_data_slaat_lege_arrays_op(committing_db_session):
    """Folder zonder bestandsniveau-NER-rijen: get_entities_for_folder geeft lege
    lijsten, persist_folder slaat lege arrays op (geen NULLs)."""
    session, cleanup_ids = committing_db_session
    archive_id, folder_id, _, analysis_id = await _setup_archief(
        session, cleanup_ids, "ner-test-folder-persist-leeg", n_bestanden=0
    )

    repo = NerRepository(session)
    entities = await repo.get_entities_for_folder(analysis_id, folder_id)
    await repo.persist_folder(analysis_id, archive_id, None, folder_id, entities)
    await session.commit()

    rij = (await session.execute(
        text("SELECT * FROM ner WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(folder_id), "aid": str(analysis_id)},
    )).mappings().one()

    print(f"\n[M3.08] Lege folder NER-rij: {dict(rij)}")

    assert rij["persons"] == [], "Verwacht lege array, niet NULL"
    assert rij["persons_count"] == 0
    assert rij["persons_frequencies"] == [], "Verwacht lege JSONB array, niet NULL"
    assert rij["locations"] == []
    assert rij["locations_count"] == 0
    assert rij["organisations"] == []
    assert rij["misc"] == []


@pytest.mark.asyncio
async def test_persist_folder_top_n_behoudt_enkel_meest_frequente_entiteiten(committing_db_session):
    """top_n truncatie: van 5 personen worden enkel de top 2 bewaard, in
    afdalende frequentievolgorde."""
    session, cleanup_ids = committing_db_session
    archive_id, folder_id, file_ids, analysis_id = await _setup_archief(
        session, cleanup_ids, "ner-test-folder-persist-topn", n_bestanden=5
    )

    # Frequenties na UNNEST+GROUP BY:
    #   Jan Hendrickx  5x  (staat in alle 5 bestanden)
    #   Marie Claes    4x
    #   Piet Janssen   3x
    #   Kaat De Smedt  2x
    #   Luc Vermeersch 1x
    ner_per_bestand = [
        ["Jan Hendrickx", "Marie Claes", "Piet Janssen", "Kaat De Smedt", "Luc Vermeersch"],
        ["Jan Hendrickx", "Marie Claes", "Piet Janssen", "Kaat De Smedt"],
        ["Jan Hendrickx", "Marie Claes", "Piet Janssen"],
        ["Jan Hendrickx", "Marie Claes"],
        ["Jan Hendrickx"],
    ]

    repo = NerRepository(session)
    for fid, persons in zip(file_ids, ner_per_bestand):
        await repo.persist(analysis_id, archive_id, folder_id, fid, _ner(persons=persons))
    await session.commit()

    entities = await repo.get_entities_for_folder(analysis_id, folder_id, top_n=2)
    await repo.persist_folder(analysis_id, archive_id, None, folder_id, entities)
    await session.commit()

    rij = (await session.execute(
        text("SELECT persons, persons_count, persons_frequencies FROM ner "
             "WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(folder_id), "aid": str(analysis_id)},
    )).mappings().one()

    print(f"\n[M3.08] top_n=2: persons={rij['persons']}  "
          f"frequencies={rij['persons_frequencies']}")

    assert len(rij["persons"]) == 2, (
        f"top_n=2 maar {len(rij['persons'])} personen opgeslagen: {rij['persons']}"
    )
    assert rij["persons"][0] == "Jan Hendrickx", "Meest frequente entiteit moet eerst staan"
    assert rij["persons"][1] == "Marie Claes"
    assert rij["persons_count"] == 2

    freqs = rij["persons_frequencies"]
    assert len(freqs) == 2
    assert freqs[0]["entity"] == "Jan Hendrickx"
    assert freqs[0]["count"] == 5
    assert freqs[1]["entity"] == "Marie Claes"
    assert freqs[1]["count"] == 4

    # Verify dat Piet Janssen (3x), Kaat (2x), Luc (1x) NIET opgeslagen zijn
    opgeslagen_namen = rij["persons"]
    assert "Piet Janssen" not in opgeslagen_namen
    assert "Kaat De Smedt" not in opgeslagen_namen
    assert "Luc Vermeersch" not in opgeslagen_namen
