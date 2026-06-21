"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.01 — exotische bestandsnamen worden exact bewaard.

Story: "Worden bestandsnamen met accenten, spaties, haakjes, ampersands,
unicode en andere bijzondere tekens  correct opgeslagen
in de database? (dus geen autocorrecties)"
"""

import uuid  # genereert unieke IDs (UUID4) voor archive en root_path zodat parallelle testruns elkaar niet bijten
from unittest.mock import (
    AsyncMock,   # vervangt een async functie/methode door een nepaanroep (httpx client.get)
    MagicMock,   # vervangt een synchroon object door een nep (httpx response + raise_for_status)
    patch,       # swaps tijdelijk een naam in een module (httpx.AsyncClient) door een mock
)

import pytest
from sqlalchemy import text

from app.create_new_archive.file_repository import FileRepository
from app.create_new_archive.folder_analysis import FolderAnalysis


EXOTIC_NAMES = [
    "café résumé été.pdf",            # accenten
    "rapport (versie 2) & bijlage.docx",  # haakjes en ampersand
    "Müller & Söhne GmbH.xlsx",       # umlauts en ampersand
    "factuur [2024] #1.txt",          # blokhaken en hekje
    "bestand met spaties in naam.pdf",
    "日本語ファイル.pdf",               # Japanse tekens
    "ملف عربي.docx",                  # Arabisch
    "файл_на_русском.txt",            # Cyrillisch
    "∑∆π formules.xlsx",              # wiskundige symbolen
    "emoji 🎉 bestand.pdf",           # emoji in naam (bewaard als-is)
]


def _agent_response(root_path: str, names: list[str]) -> dict:
    return {
        "root": root_path,
        "total_files": len(names),
        "files": [
            {
                "name": name,
                "relative_path": name,
                "absolute_path": f"{root_path}/{name}",
                "parent_folder": ".",
                "is_directory": False,
                "size_bytes": 100,
                "modified": 1700000000.0,
            }
            for name in names
        ],
    }


@pytest.mark.asyncio
async def test_exotische_bestandsnamen_worden_exact_bewaard(async_db_session):
    """Stuurt EXOTIC_NAMES via de mock-agent door FolderAnalysis en FileRepository
    (echte INSERT) en controleert dat elke naam ongewijzigd in de DB staat.
    Bewaakt dat PostgreSQL + SQLAlchemy Unicode ergens aanpassen.
    """
    #genereer unieke archiefnaam
    archive_id = uuid.uuid4()
    root_path = f"/tmp/test-archief-{archive_id}"

    # maak een nieuw archief aan in postgres
    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": "exotische-namen-test", "root_path": root_path},
    )
    await async_db_session.flush()

    # FolderAnalysis doet intern: (wij willen een mockclient draaien en overschrijven dus een aantal
    # fucnties in de HTTP-laag, onze mock objecten geven vastgelegde data terug)
    #   async with httpx.AsyncClient() as client: 
    #       resp = await client.get(agent_url/files)

    # mock_response  — het nep HTTP-antwoord dat de agent zou sturen.
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = _agent_response(root_path, EXOTIC_NAMES)

    # mock_client  — de nep HTTP-client. client.get() geeft mock_response terug.
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    # patch  — vervangt httpx.AsyncClient tijdelijk in de folder_analysis module.
    with patch("app.create_new_archive.folder_analysis.httpx.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
        entries = await FolderAnalysis().analyze(archive_id, root_path)

    await FileRepository(async_db_session).persist_all(entries)

    # haal alle opgeslagen bestandsnamen op uit de DB voor dit archief
    result = await async_db_session.execute(
        text("SELECT name FROM files WHERE archive_id = :archive_id AND is_directory = false"),
        {"archive_id": str(archive_id)},
    )
    stored_names = {row.name for row in result}

    # controleer dat elke exotische naam exact (byte-voor-byte) teruggevonden wordt
    for name in EXOTIC_NAMES:
        assert name in stored_names, f"Naam niet exact bewaard: {name!r}"
