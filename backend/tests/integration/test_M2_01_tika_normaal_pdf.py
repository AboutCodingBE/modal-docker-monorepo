"""M2 — perform_tika_analysis: het extraheren van tekst en metadata uit bestanden
via de Apache Tika-server en het opslaan van de resultaten in de database
(app/perform_tika_analysis/).

M2.01 — Tika-analyse op een normaal, leesbaar PDF-document.

Story: "Extraheert Tika tekst en metadata correct uit een gewone PDF?"

Vereisten om deze test te draaien:
  - PostgreSQL bereikbaar op DATABASE_URL_SYNC (zie backend/.env)
  - Apache Tika-server bereikbaar op TIKA_URL (zie backend/.env, standaard http://localhost:7777)
  - De mock-agent geeft de fixture-PDF terug, zodat geen echte agent-server nodig is.

Wat we testen:
  Het systeem stuurt een echte leesbare PDF naar de Tika-server en slaat de geëxtraheerde
  velden correct op in de tabel tika_analyses:

  ┌─────────────────────┬──────────────────────────────────────────────────────┐
  │ Veld                │ Verwachte waarde                                     │
  ├─────────────────────┼──────────────────────────────────────────────────────┤
  │ mime_type           │ "application/pdf"                                    │
  │ content             │ bevat "testdocument" en "gemeentearchief"            │
  │ tika_parser         │ bevat "PDFParser"                                    │
  │ language            │ niet None (langdetect herkent de taal)               │
  │ word_count          │ > 0                                                  │
  │ author              │ "J. Janssen"  (uit /Author-veld in PDF)              │
  │ content_created_at  │ niet None  (uit /CreationDate-veld in PDF)           │
  └─────────────────────┴──────────────────────────────────────────────────────┘

Teststrategie:
  - ECHT:  Tika-aanroep gaat naar de echte Tika Docker container (via TIKA_URL).
  - MOCK:  De HTTP-aanroep naar de agent (bestandsbytes ophalen) is gemocked —
           we geven de fixture-bytes direct terug als response.content.
  - ECHT:  DB-INSERT via TikaRepository (echte PostgreSQL-transactie).
  - session.commit() is als no-op gemocked zodat de async_db_session-fixture
    aan het einde via rollback alle testdata schoonmaakt.

Fixture-PDF (backend/tests/fixtures/normaal_document.pdf):
  - Minimale geldige PDF 1.4 met Nederlandstalige tekst in de content stream.
  - /Author-veld: "J. Janssen"
  - /CreationDate-veld: "D:20230315103000Z"
  - Aangemaakt via backend/tests/fixtures/make_fixtures.py.
"""

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import text

from app.perform_tika_analysis.perform_tika_analysis import PerformTikaAnalysis


# Fixture-PDF: een minimaal geldig PDF-bestand met bekende tekst en metadata.
# Tika extraheert hieruit de velden die we in de assert-sectie controleren.
FIXTURE_PDF = Path(__file__).parent.parent / "testdata" / "data_M2" / "normaal_document.pdf"


@pytest.mark.asyncio
async def test_tika_extraheert_tekst_en_metadata_uit_normale_pdf(async_db_session, requires_tika):
    """Stuurt een echte leesbare PDF naar de Tika Docker container via
    PerformTikaAnalysis en controleert dat alle geëxtraheerde velden correct
    worden opgeslagen in de tabel tika_analyses.

    De HTTP-aanroep naar de agent (ophalen van bestandsbytes) is gemocked:
    we geven de fixture-PDF-bytes terug zonder een echte agent-server.
    De Tika-aanroep zelf gaat naar de echte Tika-server (TIKA_URL).
    """
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    task_id = uuid.uuid4()
    root_path = f"/tmp/test-archief-{archive_id}"
    file_path = f"{root_path}/rapport.pdf"

    # Laad de fixture-PDF-bytes — dit zijn de bytes die de mock-agent teruggeeft,
    # zodat Tika een echte PDF te verwerken krijgt zonder dat de agent draait.
    pdf_bytes = FIXTURE_PDF.read_bytes()

    # --- DB-prerequisites: archief, bestand en analyse-taak ---
    # PerformTikaAnalysis.execute() verwacht drie aanwezige rijen:
    #   - archives: nodig voor FK-integriteit van files en analysis_tasks
    #   - files: FileRepository.get_by_archive() levert hieruit de bestandslijst
    #   - analysis_tasks: task_tracker.start_task() en update_progress() updaten deze rij
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "tika-normaal-pdf-test", "root_path": root_path},
    )
    await async_db_session.execute(
        text("""
            INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
            VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
        """),
        {
            "id": str(file_id),
            "archive_id": str(archive_id),
            "name": "rapport.pdf",
            "full_path": file_path,
            "relative_path": "rapport.pdf",
        },
    )
    await async_db_session.execute(
        text("""
            INSERT INTO analysis_tasks (id, archive_id, status, task_type, total_files, processed, failed_count)
            VALUES (:id, :archive_id, 'pending', 'tika', 0, 0, 0)
        """),
        {"id": str(task_id), "archive_id": str(archive_id)},
    )
    await async_db_session.flush()

    # mock_response — het nep HTTP-antwoord van de agent.
    #   response.content bevat de fixture-PDF-bytes die naar Tika worden doorgestuurd.
    #   raise_for_status() is een no-op (gesimuleerde 200 OK).
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.content = pdf_bytes

    # mock_client — de nep httpx.AsyncClient waarmee de agent wordt aangeroepen.
    #   client.get(...) geeft mock_response terug in plaats van een echte HTTP-aanroep.
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with (
        # patch: vervangt httpx.AsyncClient in de perform_tika_analysis-module
        #        door onze mock — zo gaat het bestandsophalen via mock_client.
        patch("app.perform_tika_analysis.perform_tika_analysis.httpx.AsyncClient") as MockAsyncClient,
        # patch: session.commit() als no-op zodat de testdata flushed (zichtbaar
        #        binnen de transactie) maar nooit gecommit wordt — de rollback in
        #        async_db_session verwijdert alles schoon na de test.
        patch.object(async_db_session, "commit", new_callable=AsyncMock),
    ):
        MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)

        # Voer de volledige Tika-analysepipeline uit:
        #   1. task_tracker.start_task()          — zet status op 'running'
        #   2. FileRepository.get_by_archive()    — haalt de bestandslijst op uit de DB
        #   3. httpx.AsyncClient().get(agent_url) — GEMOCKED: geeft fixture-bytes terug
        #   4. TIKA_text_extract(pdf_bytes)       — ECHT: stuurt bytes naar Tika-server
        #   5. normalize_newlines() / get_word_count() — tekstverwerking
        #   6. TikaRepository.persist()           — slaat resultaten op in tika_analyses
        #   7. task_tracker.complete_task()       — zet status op 'completed'
        await PerformTikaAnalysis(async_db_session).execute(archive_id, task_id)

    # --- Verificatie: haal de opgeslagen Tika-analyse op ---
    result = await async_db_session.execute(
        text("SELECT * FROM tika_analyses WHERE file_id = :file_id"),
        {"file_id": str(file_id)},
    )
    row = result.mappings().one()

    # mime_type: Tika herkent het bestand correct als PDF
    assert row["mime_type"] == "application/pdf", (
        f"mime_type: verwacht 'application/pdf', kreeg {row['mime_type']!r}"
    )

    # content: de bekende Nederlandstalige tekst uit de fixture is geëxtraheerd
    assert row["content"] is not None, (
        "content mag niet None zijn voor een leesbaar PDF-document"
    )
    assert "testdocument" in row["content"], (
        f"content bevat niet de verwachte tekst 'testdocument': {row['content']!r}"
    )
    assert "gemeentearchief" in row["content"], (
        f"content bevat niet de verwachte tekst 'gemeentearchief': {row['content']!r}"
    )

    # tika_parser: Tika rapporteert de gebruikte parser — voor een PDF is dat PDFParser
    assert row["tika_parser"] is not None, "tika_parser mag niet None zijn"
    assert "PDFParser" in row["tika_parser"], (
        f"tika_parser bevat geen 'PDFParser': {row['tika_parser']!r}"
    )

    # word_count: het aantal woorden is berekend op basis van de geëxtraheerde tekst
    assert row["word_count"] > 0, (
        f"word_count moet > 0 zijn voor een document met tekst, kreeg {row['word_count']}"
    )

    # language: langdetect heeft een taalcode ingevuld (korte tekst → niet perse 'nl',
    #           maar er moet wel iets zijn)
    assert row["language"] is not None, (
        "language mag niet None zijn voor een document met voldoende tekst"
    )

    # author: het /Author-veld uit de PDF-info-dictionary is opgeslagen als dc:creator
    assert row["author"] == "J. Janssen", (
        f"author: verwacht 'J. Janssen' (uit PDF /Author), kreeg {row['author']!r}"
    )

    # content_created_at: de /CreationDate (D:20230315103000Z) is geparsed en opgeslagen
    assert row["content_created_at"] is not None, (
        "content_created_at mag niet None zijn — de fixture-PDF bevat /CreationDate"
    )
