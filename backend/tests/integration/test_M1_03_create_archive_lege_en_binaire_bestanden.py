"""M1 — create_archive: het scannen van een map en het opslaan van alle bestands-
en mapmetadata in de database (app/create_new_archive/).

M1.03 — lege en binaire bestanden.

Story: "Wat gebeurt er met bestanden van 0 bytes of binaire bestanden zoals
.exe, .db, Thumbs.db?"

TODO: implementeren.
"""

import pytest


@pytest.mark.skip(reason="TODO: M1.02 nog niet geïmplementeerd")
@pytest.mark.asyncio
async def test_bestand_van_0_bytes_wordt_correct_opgeslagen():
    pass


@pytest.mark.skip(reason="TODO: M1.02 nog niet geïmplementeerd")
@pytest.mark.asyncio
async def test_binair_bestand_exe_db_thumbsdb_wordt_correct_opgeslagen():
    pass
