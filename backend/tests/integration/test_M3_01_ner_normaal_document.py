"""M3 — create_ner_for_archive: NER-analyse van bestanden in een archief via spaCy
(app/create_ner_for_archive/).

M3.01 — NER op een normaal Nederlandstalig document.

Story: "Vindt NER personen, organisaties en locaties in een normaal
Nederlandstalig document?"

Wat we testen:
  Een bekende Nederlandstalige tekst met expliciete personen, organisaties en
  locaties wordt aangeboden aan de NER-engine. We controleren dat de gevonden
  entiteiten correct gecategoriseerd zijn en dat ze weggeschreven worden naar
  de ner-tabel in de database.

  Aandachtspunt: nl_core_news_lg (getraind op SoNaR/CoNLL) labelt personen
  als 'PER', niet als 'PERSON'. De _LABEL_MAP in ner_engine.py gebruikt echter
  'PERSON'. Als dit mismatch bestaat, belanden personen in de 'misc'-bucket en
  faalt de assertion persons_count > 0 — wat het juiste gedrag is: de test
  legt de fout bloot in plaats van ze te verbergen.

Teststrategie:
  - ECHT: run_ner() gebruikt het geïnstalleerde nl_core_news_lg spaCy-model.
  - ECHT: NerRepository.persist() schrijft naar echte PostgreSQL.
  - Fixture-tekst met bekende entiteiten maakt concrete assertions mogelijk.
  - Cleanup via committing_db_session; archive_analysis wordt via CASCADE
    meegenomen wanneer archives wordt verwijderd.

Fixture-bestanden (backend/tests/testdata/data_M3/):
  - normaal_document.txt — Nederlandstalige archiefsbrief met bekende entiteiten

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
NORMAAL_DOCUMENT = FIXTURE_DIR / "normaal_document.txt"


@pytest.mark.asyncio
async def test_ner_vindt_personen_organisaties_en_locaties_in_normaal_document(
    committing_db_session,
):
    """NER op een Nederlandstalige archiefsbrief detecteert en categoriseert
    personen, organisaties en locaties correct en slaat ze op in de database."""
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
        {
            "id": str(archive_id),
            "name": "ner-test-normaal-document",
            # root_path heeft een UNIQUE constraint — gebruik archive_id om botsingen
            # met parallelle testruns te vermijden.
            "root_path": f"/tmp/ner-test/{archive_id}",
        },
    )
    await session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": NORMAAL_DOCUMENT.name,
            "full_path": str(NORMAAL_DOCUMENT),
            "relative_path": NORMAAL_DOCUMENT.name,
        },
    )
    # archive_analysis is vereist door de FK ner.analysis_id → archive_analysis.id.
    # Bij cleanup wordt deze rij automatisch verwijderd via CASCADE vanuit archives.
    await session.execute(
        text("""
            INSERT INTO archive_analysis (id, archive_id, type, model, status)
            VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
        """),
        {"id": str(analysis_id), "archive_id": str(archive_id)},
    )
    await session.commit()
    cleanup_ids.append(archive_id)

    # ── NER: voer spaCy uit op de fixture-tekst ───────────────────────────────
    tekst = NORMAAL_DOCUMENT.read_text(encoding="utf-8")
    print(f"\n[M3.01] Fixture: {NORMAAL_DOCUMENT.name} ({len(tekst.split())} woorden)")
    ner_resultaat = run_ner(tekst)
    print(f"[M3.01] Engine-output:")
    print(f"        persons       ({ner_resultaat['persons_count']}): {ner_resultaat['persons']}")
    print(f"        locations     ({ner_resultaat['locations_count']}): {ner_resultaat['locations']}")
    print(f"        organisations ({ner_resultaat['organisations_count']}): {ner_resultaat['organisations']}")
    print(f"        misc          ({ner_resultaat['misc_count']}): {ner_resultaat['misc']}")

    # ── Persisteer het resultaat ──────────────────────────────────────────────
    await NerRepository(session).persist(
        analysis_id=analysis_id,
        archive_id=archive_id,
        parent_folder_id=None,
        file_id=file_id,
        ner_result=ner_resultaat,
    )
    # NerRepository.persist() roept enkel flush() aan; commit() maakt het
    # zichtbaar voor de query hieronder en voor de cleanup-fixture achteraf.
    await session.commit()

    # ── Lees de ner-rij terug en verifieer de entiteiten ──────────────────────
    rij = await session.execute(
        text("SELECT * FROM ner WHERE file_id = :fid"),
        {"fid": str(file_id)},
    )
    ner_rij = rij.mappings().one()
    print(f"[M3.01] DB-rij na persist:")
    print(f"        persons       ({ner_rij['persons_count']}): {ner_rij['persons']}")
    print(f"        locations     ({ner_rij['locations_count']}): {ner_rij['locations']}")
    print(f"        organisations ({ner_rij['organisations_count']}): {ner_rij['organisations']}")
    print(f"        misc          ({ner_rij['misc_count']}): {ner_rij['misc']}")

    assert ner_rij["persons_count"] > 0, (
        f"Verwacht minstens één persoon (Marie Claes, Pieter Janssens, Karel Vermeersch…) "
        f"maar persons_count = {ner_rij['persons_count']}. "
        f"misc-bucket bevat: {ner_rij['misc']!r}. "
        "Mogelijke oorzaak: _LABEL_MAP gebruikt 'PERSON' maar nl_core_news_lg "
        "labelt personen als 'PER' — controleer ner_engine.py:_LABEL_MAP."
    )

    gent_gevonden = any("Gent" in loc for loc in (ner_rij["locations"] or []))
    assert gent_gevonden, (
        f"Verwacht 'Gent' in locations (Gent staat expliciet in de tekst), "
        f"maar locations = {ner_rij['locations']!r}. "
        f"misc-bucket bevat: {ner_rij['misc']!r}. "
        "Controleer of nl_core_news_lg 'Gent' als LOC of GPE labelt "
        "en of _LABEL_MAP die labels correct afbeeldt."
    )

    assert ner_rij["organisations_count"] > 0, (
        f"Verwacht minstens één organisatie (Amsab-ISG, Gemeentearchief Gent…) "
        f"maar organisations_count = {ner_rij['organisations_count']}. "
        f"organisations = {ner_rij['organisations']!r}, misc = {ner_rij['misc']!r}."
    )

    # Tellersvelden moeten overeenkomen met de werkelijke lijstlengtes.
    # Als dit faalt is er een bug in run_ner() zelf.
    assert ner_rij["persons_count"] == len(ner_rij["persons"] or []), (
        "persons_count stemt niet overeen met de lengte van de persons-lijst — "
        f"count={ner_rij['persons_count']}, lijst={ner_rij['persons']!r}."
    )
    assert ner_rij["locations_count"] == len(ner_rij["locations"] or []), (
        "locations_count stemt niet overeen met de lengte van de locations-lijst — "
        f"count={ner_rij['locations_count']}, lijst={ner_rij['locations']!r}."
    )
