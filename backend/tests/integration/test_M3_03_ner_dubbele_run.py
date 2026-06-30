"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.03 — NER twee keer gedraaid op hetzelfde bestand.

Story: "Wat gebeurt er als NER twee keer gedraaid wordt op hetzelfde
archief — duplicaten of netjes overschreven?"

Wat we testen:
  CreateNerForArchive beschermt tegen dubbele verwerking via
  NerRepository.exists(): als er al een NER-rij bestaat voor een
  (analysis_id, file_id)-combinatie, wordt het bestand overgeslagen.

  Maar: er is geen UNIQUE constraint op (analysis_id, file_id) in de
  ner-tabel. Als NerRepository.persist() twee keer rechtstreeks wordt
  aangeroepen, ontstaan er stille duplicaten in de database. Deze test
  legt dat bloot door:

    1. Twee keer persist() aanroepen voor dezelfde combinatie.
    2. Het aantal rijen in de DB te tellen — verwacht 1, maar krijgt 2
       als de unique constraint ontbreekt.
    3. Te verifiëren dat exists() True teruggeeft na de eerste persist.

  De exists()-check in CreateNerForArchive werkt correct zolang de flow
  via de orchestrator loopt. Deze test toont dat de bescherming niet
  op DB-niveau zit.

Teststrategie:
  - ECHT: NerRepository.persist() en exists() op echte PostgreSQL.
  - Geen run_ner() nodig — we testen het repository-gedrag, niet de engine.
  - Cleanup via committing_db_session (CASCADE vanuit archives).

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_repository import NerRepository


# Een minimaal NER-resultaat — inhoud doet er niet toe, we testen
# het persist/exists-gedrag, niet de entiteitsdetectie.
_LEEG_NER_RESULTAAT = {
    "persons": [], "locations": [], "organisations": [], "misc": [],
}


@pytest.mark.asyncio
async def test_ner_exists_geeft_true_na_eerste_persist(committing_db_session):
    """exists() geeft True terug na een eerste persist — de basis van de
    dubbele-run-bescherming in CreateNerForArchive."""
    session, cleanup_ids = committing_db_session

    archive_id, file_id, analysis_id = await _setup(session, cleanup_ids)

    repo = NerRepository(session)
    await repo.persist(analysis_id, archive_id, None, file_id, _LEEG_NER_RESULTAAT)
    await session.commit()

    bestaat = await repo.exists(analysis_id, file_id)
    assert bestaat, (
        "exists() geeft False terug na persist — de dubbele-run-bescherming "
        "in CreateNerForArchive werkt dan niet."
    )


@pytest.mark.asyncio
async def test_ner_dubbele_persist_maakt_duplicaten_als_unique_constraint_ontbreekt(
    committing_db_session,
):
    """Twee keer persist() aanroepen voor dezelfde (analysis_id, file_id)
    maakt duplicaten als de ner-tabel geen UNIQUE constraint heeft."""
    session, cleanup_ids = committing_db_session

    archive_id, file_id, analysis_id = await _setup(session, cleanup_ids)

    repo = NerRepository(session)
    await repo.persist(analysis_id, archive_id, None, file_id, _LEEG_NER_RESULTAAT)
    await session.commit()

    # Tweede persist zonder exists()-check — simuleert een herstart of
    # een bug waarbij de orchestrator de check overslaat.
    await repo.persist(analysis_id, archive_id, None, file_id, _LEEG_NER_RESULTAAT)
    await session.commit()

    rij = await session.execute(
        text("SELECT COUNT(*) FROM ner WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(file_id), "aid": str(analysis_id)},
    )
    aantal = rij.scalar()
    print(f"\n[M3.03] Aantal ner-rijen na twee keer persist(): {aantal}")

    assert aantal == 1, (
        f"Twee keer persist() voor dezelfde (analysis_id, file_id) "
        f"heeft {aantal} rijen aangemaakt. De ner-tabel mist een "
        "UNIQUE constraint op (analysis_id, file_id) — duplicaten zijn mogelijk "
        "als de exists()-check in CreateNerForArchive wordt omzeild."
    )


async def _setup(session, cleanup_ids) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """Maakt minimale DB-rijen aan en geeft (archive_id, file_id, analysis_id) terug."""
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "ner-test-dubbele-run", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "brief_1952.txt",
            "full_path": f"/tmp/ner-test/{archive_id}/brief_1952.txt",
            "relative_path": "brief_1952.txt",
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

    return archive_id, file_id, analysis_id
