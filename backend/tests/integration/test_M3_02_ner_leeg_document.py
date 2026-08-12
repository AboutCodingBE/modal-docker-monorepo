"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.02 — NER op een leeg document.

Story: "Wat doet NER als er geen tekst is — geen crash, lege entiteitenlijst?"

Wat we testen:
  Een document zonder tekstinhoud wordt aangeboden aan de NER-engine. We
  controleren dat run_ner() niet crasht en lege lijsten teruggeeft, en dat
  NerRepository.persist() die lege lijsten als [] (niet als NULL) opslaat.

  Dit test ook het asyncpg-gedrag: asyncpg kan een lege Python-lijst []
  omzetten naar NULL bij het schrijven naar een PostgreSQL ARRAY-kolom.
  Als dat zo is, staan alle velden op NULL voor elk document zonder entiteiten
  — een stille bug die downstream code breekt. Deze test legt dat bloot.

Teststrategie:
  - ECHT: run_ner("") op lege string — geen mock.
  - ECHT: NerRepository.persist() schrijft naar echte PostgreSQL.
  - Assertions controleren zowel de engine-output als de DB-waarden.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - spaCy nl_core_news_lg geïnstalleerd
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository


@pytest.mark.asyncio
async def test_ner_geeft_lege_entiteitenlijst_zonder_crash_bij_leeg_document(
    committing_db_session,
):
    """run_ner() op lege tekst crasht niet en geeft lege lijsten terug;
    NerRepository slaat die lege lijsten op als [] (niet NULL) in de database."""
    session, cleanup_ids = committing_db_session

    # ── Setup: minimale DB-rijen aanmaken ─────────────────────────────────────
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-leeg-document", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "leeg_document.txt",
            "full_path": f"/tmp/ner-test/{archive_id}/leeg_document.txt",
            "relative_path": "leeg_document.txt",
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

    # ── NER op lege string ────────────────────────────────────────────────────
    # run_ner("") mag niet crashen. Als spaCy de lege input niet aankan,
    # zou hier een exception worden gegooid en faalt de test — wat correct is.
    ner_resultaat = run_ner("")

    print(f"\n[M3.02] Engine-output op lege tekst:")
    print(f"        persons       ({ner_resultaat['persons_count']}): {ner_resultaat['persons']}")
    print(f"        locations     ({ner_resultaat['locations_count']}): {ner_resultaat['locations']}")
    print(f"        organisations ({ner_resultaat['organisations_count']}): {ner_resultaat['organisations']}")
    print(f"        misc          ({ner_resultaat['misc_count']}): {ner_resultaat['misc']}")

    # Engine moet lege lijsten teruggeven, niet None
    for categorie in ("persons", "locations", "organisations", "misc"):
        assert ner_resultaat[categorie] == [], (
            f"run_ner('') moet [] teruggeven voor '{categorie}', "
            f"maar gaf {ner_resultaat[categorie]!r}."
        )
        assert ner_resultaat[f"{categorie}_count"] == 0, (
            f"run_ner('') moet 0 teruggeven voor '{categorie}_count', "
            f"maar gaf {ner_resultaat[f'{categorie}_count']}."
        )

    # ── Persisteer en lees terug ──────────────────────────────────────────────
    await NerRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        ner_result=ner_resultaat,
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT * FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_rij = rij.mappings().one()

    print(f"[M3.02] DB-rij na persist:")
    print(f"        persons       ({len(db_rij['persons'])}): {db_rij['persons']}")
    print(f"        locations     ({len(db_rij['locations'])}): {db_rij['locations']}")
    print(f"        organisations ({len(db_rij['organisations'])}): {db_rij['organisations']}")
    print(f"        misc          ({len(db_rij['misc'])}): {db_rij['misc']}")

    # Lege lijsten mogen niet als NULL worden opgeslagen — [] is niet hetzelfde
    # als NULL. NULL betekent "onbekend"; [] betekent "geanalyseerd, niets gevonden".
    for categorie in ("persons", "locations", "organisations", "misc"):
        db_waarde = db_rij[categorie]
        assert db_waarde is not None, (
            f"'{categorie}' is NULL in de DB maar de engine gaf [] terug."
        )
        assert db_waarde == [], (
            f"'{categorie}' in DB is {db_waarde!r} maar verwacht []."
        )
