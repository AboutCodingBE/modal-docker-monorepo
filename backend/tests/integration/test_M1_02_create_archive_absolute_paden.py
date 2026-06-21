"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.02 — absolute paden in verschillende formaten.

Story: "Slaat het systeem full_path en relative_path correct op voor alle
gangbare padformaten — POSIX, Windows (backslash en forward slash), UNC,
diepe nesting, en mappen met spaties of accenten?"
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


# ---------------------------------------------------------------------------
# Testcases
# (beschrijving, root_path, agent_absolute_path, agent_relative_path,
#  verwacht_full_path, verwacht_relative_path)
# ---------------------------------------------------------------------------
PATH_CASES = [
    (
        "POSIX pad",
        "/archief/brieven",
        "/archief/brieven/brief.pdf",
        "brief.pdf",
        "/archief/brieven/brief.pdf",
        "brief.pdf",
    ),
    (
        "Windows pad — backslashes",
        "C:\\Users\\user\\archief",
        "C:\\Users\\user\\archief\\brief.pdf",
        "brief.pdf",
        "C:/Users/user/archief/brief.pdf",
        "brief.pdf",
    ),
    (
        "Windows pad — forward slashes",
        "C:/Users/user/archief",
        "C:/Users/user/archief/brief.pdf",
        "brief.pdf",
        "C:/Users/user/archief/brief.pdf",
        "brief.pdf",
    ),
    (
        "UNC pad",
        "\\\\server\\share",
        "\\\\server\\share\\brief.pdf",
        "brief.pdf",
        "//server/share/brief.pdf",
        "brief.pdf",
    ),
    (
        "spaties in mapnaam",
        "/mijn documenten/archief",
        "/mijn documenten/archief/brief.pdf",
        "brief.pdf",
        "/mijn documenten/archief/brief.pdf",
        "brief.pdf",
    ),
    (
        "accenten in mapnaam",
        "/archief/café résumé",
        "/archief/café résumé/brief.pdf",
        "brief.pdf",
        "/archief/café résumé/brief.pdf",
        "brief.pdf",
    ),
    (
        "diep genest pad",
        "/root",
        "/root/a/b/c/d/brief.pdf",
        "a/b/c/d/brief.pdf",
        "/root/a/b/c/d/brief.pdf",
        "a/b/c/d/brief.pdf",
    ),
    (
        "Windows diep genest pad met backslashes",
        "C:\\archief",
        "C:\\archief\\sub1\\sub2\\brief.pdf",
        "sub1\\sub2\\brief.pdf",
        "C:/archief/sub1/sub2/brief.pdf",
        "sub1/sub2/brief.pdf",
    ),
]


def _agent_response(root_path: str, absolute_path: str, relative_path: str) -> dict:
    return {
        "root": root_path,
        "total_files": 1,
        "files": [
            {
                "name": "brief.pdf",
                "relative_path": relative_path,
                "absolute_path": absolute_path,
                "parent_folder": ".",
                "is_directory": False,
                "size_bytes": 512,
                "modified": 1700000000.0,
            }
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "beschrijving,root_path,agent_absolute,agent_relative,verwacht_full,verwacht_relative",
    PATH_CASES,
    ids=[c[0] for c in PATH_CASES],
)
async def test_absolute_padformaten(
    async_db_session,
    beschrijving,
    root_path,
    agent_absolute,
    agent_relative,
    verwacht_full,
    verwacht_relative,
):
    """Stuurt één bestand per padformaat via de mock-agent door FolderAnalysis en
    FileRepository (echte INSERT) en controleert dat full_path en relative_path
    correct genormaliseerd (backslash → slash) in de DB staan.
    """
    archive_id = uuid.uuid4()

    await async_db_session.execute(
        text("""
            INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
            VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
        """),
        {"id": str(archive_id), "name": beschrijving, "root_path": root_path},
    )
    await async_db_session.flush()

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = _agent_response(root_path, agent_absolute, agent_relative)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("app.create_new_archive.folder_analysis.httpx.AsyncClient") as MockAsyncClient:
        MockAsyncClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        MockAsyncClient.return_value.__aexit__ = AsyncMock(return_value=False)
        entries = await FolderAnalysis().analyze(archive_id, root_path)

    await FileRepository(async_db_session).persist_all(entries)

    result = await async_db_session.execute(
        text("""
            SELECT full_path, relative_path FROM files
            WHERE archive_id = :archive_id AND is_directory = false
        """),
        {"archive_id": str(archive_id)},
    )
    row = result.mappings().one()

    assert row["full_path"] == verwacht_full, (
        f"[{beschrijving}] full_path: verwacht {verwacht_full!r}, kreeg {row['full_path']!r}"
    )
    assert row["relative_path"] == verwacht_relative, (
        f"[{beschrijving}] relative_path: verwacht {verwacht_relative!r}, kreeg {row['relative_path']!r}"
    )
