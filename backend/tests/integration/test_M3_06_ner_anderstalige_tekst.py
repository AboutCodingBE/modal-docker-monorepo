"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.06 — NER op anderstalige tekst in een Nederlandstalig archief.

Story: "Hoe gedraagt NER zich bij Frans/Engelse tekst in een
Nederlandstalig archief?"

Wat we testen:
  Belgische archieven bevatten regelmatig Franstalige documenten. Het NER-model
  (nl_core_news_lg) is getraind op Nederlandstalige tekst maar wordt hier
  aangeboden met een Franstalige archiefsbrief.

  We testen drie dingen:
    1. De engine crasht niet op Franstalige invoer.
    2. De resultaatstructuur (8 sleutels, telconsistentie) blijft correct.
    3. Minstens enkele entiteiten worden herkend — bekende steden als Bruxelles
       en Liège komen voor in het spaCy-model ondanks de taalgrens.

  Als assertion 3 faalt, betekent dat dat het Nederlandse model Franstalige
  plaatsnamen niet herkent — nuttige informatie voor de beslissing om een
  meertalig model te gebruiken.

Teststrategie:
  - ECHT: run_ner() op een Franstalige archiefsbrief (fixture-bestand).
  - ECHT: NerRepository.persist() schrijft naar echte PostgreSQL.
  - Cleanup via committing_db_session.

Fixture-bestanden (backend/tests/testdata/data_M3/):
  - correspondance_francophone.txt — Franstalige archiefsbrief

Vereist:
  - PostgreSQL bereikbaar (DATABASE_URL_SYNC in .env)
  - spaCy nl_core_news_lg geïnstalleerd
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import text

from app.create_ner_for_archive.ner_engine import run_ner
from app.create_ner_for_archive.ner_repository import NerRepository


FIXTURE_DIR = Path(__file__).parent.parent / "testdata" / "data_M3"
FRANSTALIG_DOCUMENT = FIXTURE_DIR / "correspondance_francophone.txt"


@pytest.mark.asyncio
async def test_ner_crasht_niet_op_franstalige_tekst_en_bewaart_geldige_structuur(
    committing_db_session,
):
    """run_ner() op Franstalige tekst crasht niet en geeft een geldige structuur terug."""
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
        {"id": str(archive_id), "name": "ner-test-franstalig", "root_path": f"/tmp/ner-test/{archive_id}"},
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": FRANSTALIG_DOCUMENT.name,
            "full_path": str(FRANSTALIG_DOCUMENT),
            "relative_path": FRANSTALIG_DOCUMENT.name,
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

    tekst = FRANSTALIG_DOCUMENT.read_text(encoding="utf-8")
    ner_resultaat = run_ner(tekst)

    print(f"\n[M3.06] Franstalige tekst ({len(tekst.split())} woorden), nl_core_news_lg:")
    print(f"        persons       ({ner_resultaat['persons_count']}): {ner_resultaat['persons']}")
    print(f"        locations     ({ner_resultaat['locations_count']}): {ner_resultaat['locations']}")
    print(f"        organisations ({ner_resultaat['organisations_count']}): {ner_resultaat['organisations']}")
    print(f"        misc          ({ner_resultaat['misc_count']}): {ner_resultaat['misc']}")

    # Structuurcontrole — moet altijd kloppen ongeacht de taal
    assert set(ner_resultaat.keys()) == {
        "persons", "persons_count",
        "locations", "locations_count",
        "organisations", "organisations_count",
        "misc", "misc_count",
    }, f"Onverwachte sleutels in resultaat: {set(ner_resultaat.keys())}"

    for categorie in ("persons", "locations", "organisations", "misc"):
        lijst = ner_resultaat[categorie]
        count = ner_resultaat[f"{categorie}_count"]
        assert lijst is not None, f"'{categorie}' is None — structuurfout in run_ner()."
        assert count == len(lijst), (
            f"'{categorie}_count' ({count}) ≠ len({lijst!r}) ({len(lijst)}) — "
            "telconsistentie verbroken op anderstalige tekst."
        )

    # Bekende steden in de Franstalige tekst — het Nederlandse model zou ze
    # kunnen herkennen omdat het spaCy-woordenboek taalgrens-overschrijdend is.
    # Als dit faalt: het model herkent Franstalige locaties niet — overweeg
    # een meertalig model (bv. xx_ent_wiki_sm).
    alle_locations = " ".join(ner_resultaat["locations"])
    assert "Bruxelles" in alle_locations or "Liège" in alle_locations or "Namur" in alle_locations, (
        f"Geen enkele bekende Franstalige locatie gevonden in locations {ner_resultaat['locations']!r}. "
        "nl_core_news_lg herkent Franstalige plaatsnamen niet — "
        "overweeg een meertalig spaCy-model voor archieven met Franstalige documenten."
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
        text("SELECT persons, locations, organisations FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    db_rij = rij.mappings().one()
    print(f"[M3.06] DB counts: persons={len(db_rij['persons'])}, "
          f"locations={len(db_rij['locations'])}, organisations={len(db_rij['organisations'])}")
