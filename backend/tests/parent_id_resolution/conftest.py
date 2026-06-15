"""
conftest.py — gedeelde testinfrastructuur voor integration tests.

Alles wat hier staat is automatisch beschikbaar in elk testbestand
in deze map. Je hoeft het hier nooit zelf te importeren.
"""

import os
from pathlib import Path

import pytest_asyncio
from dotenv import load_dotenv
# SQLAlchemy is de library die we gebruiken om met de database te praten.
# sqlalchemy.ext.asyncio is de async-variant daarvan.
#   create_async_engine → maakt een verbindingsfabriek naar de database
#   AsyncSession        → één open gesprek met de database (via die fabriek)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine


# ---------------------------------------------------------------------------
# Stap 1: laad de .env zodat DATABASE_URL beschikbaar is
# ---------------------------------------------------------------------------
# backend/.env bevat o.a. DATABASE_URL=postgresql+asyncpg://...
# Path(__file__) = dit bestand  → .parent x3 = backend/
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")


# ---------------------------------------------------------------------------
# Stap 2: haal de database-URL op
# ---------------------------------------------------------------------------
# Wat is FileRepository?
#   FileRepository is de klasse die bestand-records naar de DB schrijft:
#
#     FolderAnalysis        FileRepository           Database
#     (scant de schijf) →  (schrijft naar DB)  →   files-tabel
#
#   De methode persist_all() krijgt een lijst van bestand-dicts binnen en
#   slaat die op. Per rij lost hij '_parent_path' op naar een echte parent_id.
#   Dat is precies wat we in deze tests controleren.
#
# Waarom een *async* URL?
#   FileRepository verwacht een AsyncSession (async database-verbinding).
#   AsyncSession heeft een async engine nodig, en die engine heeft een
#   async URL nodig — één met 'postgresql+asyncpg://' als prefix.
#
# Optie A: DATABASE_URL staat al als asyncpg-URL in .env  ← ideaal
# Optie B: alleen DATABASE_URL_SYNC beschikbaar → vervang de driver-naam
#
# Het verschil tussen sync en async is alleen het stukje na 'postgresql+':
#   sync:  postgresql+psycopg://...
#   async: postgresql+asyncpg://...
#
_raw_url = os.environ.get("DATABASE_URL", "")

if not _raw_url:
    # Optie B: leid de async URL af van de sync URL
    _sync_url = os.environ.get("DATABASE_URL_SYNC", "")
    _raw_url = (
        _sync_url
        .replace("postgresql+psycopg://",  "postgresql+asyncpg://")
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    )

if not _raw_url:
    raise EnvironmentError(
        "Geen database-URL gevonden. "
        "Stel DATABASE_URL (asyncpg) of DATABASE_URL_SYNC in backend/.env in."
    )

ASYNC_DATABASE_URL = _raw_url


# ---------------------------------------------------------------------------
# Fixture: async_db_session
# ---------------------------------------------------------------------------
# Een 'fixture' is een stukje setup/teardown dat pytest automatisch uitvoert
# voor (en na) elke test die het als parameter opvraagt.
#
# Deze fixture geeft de test een open database-sessie.
# Na de test draait hij alles terug — de database blijft schoon.
#
@pytest_asyncio.fixture()
async def async_db_session():
    # Engine = de verbindingsfabriek naar de database.
    # echo=False: geen SQL-logging in de terminal (zet op True om queries te zien).
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)

    # Session = één gesprek met de database.
    # expire_on_commit=False: objecten blijven bruikbaar ook als we nooit commit() aanroepen.
    session = AsyncSession(engine, expire_on_commit=False)

    try:
        # 'yield' geeft de sessie aan de test.
        # Alles bóven yield = setup (voor de test).
        # Alles ónder yield (in finally) = teardown (na de test).
        yield session

    finally:
        # --- OPRUIMEN ---
        # FileRepository roept alleen flush() aan, nooit commit().
        # flush() stuurt de SQL naar de DB maar maakt de wijziging nog niet permanent.
        # rollback() draait die flush terug → de DB is weer leeg na elke test.
        await session.rollback()
        await session.close()

    # Engine mag pas weg nádat de sessie dicht is.
    await engine.dispose()
