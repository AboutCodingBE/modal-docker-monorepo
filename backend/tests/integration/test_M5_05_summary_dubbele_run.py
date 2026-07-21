"""M5 — create_summaries_for_archive: AI-samenvatting van archiefbestanden via Ollama
(app/create_summaries_for_archive/).

M5.05 — Dubbele persist: exists()-check en UNIQUE constraint.

Story: "Wat gebeurt er als samenvatting twee keer wordt gepersisteerd voor
hetzelfde bestand? Voorkomt exists() dat, en beschermt de DB-constraint ons?"

Wat we testen:
  Test 1 — exists() na eerste persist geeft True terug (hervatbaarheid).
  Test 2 — Twee persist()-aanroepen voor dezelfde (analysis_id, file_id)
            maken 2 rijen aan als er geen UNIQUE constraint is.
            Deze test is ROOD zolang de constraint ontbreekt.

Teststrategie:
  - ECHT: SummaryRepository.persist() / exists() op echte PostgreSQL.
  - Cleanup via committing_db_session.

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
"""

import uuid

import pytest
from sqlalchemy import text

from app.create_summaries_for_archive.summary_repository import SummaryRepository


async def _setup(session, cleanup_ids, naam: str):
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    await session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status,
                                  file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": naam, "root_path": f"/tmp/summary-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, 'brief.txt', :fp, 'brief.txt', false)
        """),
        {"id": str(file_id), "archive_id": str(archive_id), "fp": f"/tmp/summary-test/{archive_id}/brief.txt"},
    )
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'SUMMARY', 'llama3.2', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)
    return archive_id, file_id, analysis_id


@pytest.mark.asyncio
async def test_summary_exists_geeft_true_na_eerste_persist(committing_db_session):
    """exists() geeft True nadat persist() één keer werd aangeroepen.

    Hervatbaarheid: een pipeline die opnieuw wordt gestart slaat al-verwerkte
    bestanden over dankzij deze check."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, analysis_id = await _setup(
        session, cleanup_ids, "summary-test-exists"
    )

    repo = SummaryRepository(session)

    bestaat_voor = await repo.exists(analysis_id=analysis_id, file_id=file_id)
    assert not bestaat_voor, "exists() geeft True vóór persist() — onverwacht."

    await repo.persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        result="Testbrief over de overdracht van archiefstukken.",
    )
    await session.commit()

    bestaat_na = await repo.exists(analysis_id=analysis_id, file_id=file_id)

    print(f"\n[M5.05] exists() voor persist: {bestaat_voor}")
    print(f"[M5.05] exists() na persist:   {bestaat_na}")

    assert bestaat_na, (
        "exists() geeft False na persist() — SummaryRepository.exists() werkt niet correct."
    )


@pytest.mark.asyncio
async def test_summary_dubbele_persist_maakt_duplicaten_als_unique_constraint_ontbreekt(
    committing_db_session,
):
    """Twee persist()-aanroepen voor dezelfde (analysis_id, file_id) maken 2 rijen aan.

    VERWACHT ROOD zolang de summary-tabel geen UNIQUE constraint heeft op
    (analysis_id, file_id). Dit test documenteert de ontbrekende beveiliging.
    Zodra de constraint wordt toegevoegd gooit de tweede persist() een exception
    en moet deze test worden aangepast."""
    session, cleanup_ids = committing_db_session
    archive_id, file_id, analysis_id = await _setup(
        session, cleanup_ids, "summary-test-dubbel"
    )

    repo = SummaryRepository(session)

    await repo.persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        result="Eerste samenvatting.",
    )
    await session.commit()

    await repo.persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        result="Tweede samenvatting — dubbele run.",
    )
    await session.commit()

    rij = await session.execute(
        text("SELECT COUNT(*) FROM summary WHERE file_id = :fid AND analysis_id = :aid"),
        {"fid": str(file_id), "aid": str(analysis_id)},
    )
    aantal = rij.scalar()

    print(f"\n[M5.05] Aantal summary-rijen na dubbele persist: {aantal}")

    assert aantal == 1, (
        f"Twee keer persist() voor dezelfde (analysis_id, file_id) "
        f"heeft {aantal} rijen aangemaakt. De summary-tabel mist een "
        "UNIQUE constraint op (analysis_id, file_id). Zonder die constraint "
        "kan een herstart van de pipeline dubbele samenvattingen opslaan."
    )
