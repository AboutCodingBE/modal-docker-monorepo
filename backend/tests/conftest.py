import os
import uuid
from pathlib import Path

import httpx
import pytest
import pytest_asyncio
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

# Load DATABASE_URL_SYNC from backend/.env (same as the other scripts)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL_SYNC")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL_SYNC is not set in .env")


# ---------------------------------------------------------------------------
# Async DB-sessie — gebruikt door integration/e2e tests die FileRepository,
# TikaRepository e.d. (async SQLAlchemy) rechtstreeks aanroepen.
# ---------------------------------------------------------------------------
_raw_async_url = os.environ.get("DATABASE_URL", "")
if not _raw_async_url:
    _raw_async_url = (
        DATABASE_URL
        .replace("postgresql+psycopg://", "postgresql+asyncpg://")
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
    )
ASYNC_DATABASE_URL = _raw_async_url


# ---------------------------------------------------------------------------
# Service-beschikbaarheid — faalt de test als een vereiste service niet
# bereikbaar is, zodat het altijd duidelijk is waarom een test mislukt.
#
# Principe: gebruik pytest.fail() en nooit pytest.skip().
# Een geskipte test geeft valse zekerheid — hij telt als "groen" terwijl
# er niets getest is. Een FAIL dwingt de developer de stack op te starten.
#
# Patroon:
#   1. *_available (scope="session") — doet de HTTP-check éénmalig per run.
#   2. requires_* (scope="function") — roept pytest.fail() aan als de
#      beschikbaarheidscheck False teruggaf.
#
# Gebruik in een test:
#   async def test_foo(async_db_session, requires_tika):
#       ...  # Tika is gegarandeerd beschikbaar als we hier komen
# ---------------------------------------------------------------------------

def _service_url(name: str) -> str:
    """Leest een service-URL uit de app-settings."""
    from app.config import settings
    return {"tika": settings.tika_url, "agent": settings.agent_url}[name]


@pytest.fixture(scope="session")
def tika_available() -> bool:
    """Controleert éénmalig per test-sessie of de Tika-server bereikbaar is."""
    try:
        resp = httpx.get(f"{_service_url('tika')}/tika", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture()
def requires_tika(tika_available) -> str:
    """Faalt de test als de Tika Docker container niet bereikbaar is.
    Geeft de Tika-URL terug zodat de fixture als variabele gebruikt kan worden.
    """
    if not tika_available:
        pytest.fail(
            f"Tika niet bereikbaar op {_service_url('tika')} — "
            "start de stack met: docker compose up"
        )
    return _service_url("tika")


@pytest.fixture(scope="session")
def agent_available() -> bool:
    """Controleert éénmalig per test-sessie of de agent bereikbaar is."""
    try:
        resp = httpx.get(f"{_service_url('agent')}/health", timeout=3.0)
        return resp.status_code == 200
    except Exception:
        return False


@pytest.fixture()
def requires_agent(agent_available) -> str:
    """Faalt de test als de agent niet bereikbaar is.
    Geeft de agent-URL terug zodat de fixture als variabele gebruikt kan worden.
    """
    if not agent_available:
        pytest.fail(
            f"Agent niet bereikbaar op {_service_url('agent')} — "
            "start de stack met: docker compose up"
        )
    return _service_url("agent")


@pytest_asyncio.fixture()
async def async_db_session():
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
    session = AsyncSession(engine, expire_on_commit=False)
    try:
        yield session
    finally:
        # FileRepository roept alleen flush() aan, nooit commit() — rollback()
        # draait die flush terug zodat de DB na elke test weer leeg is.
        await session.rollback()
        await session.close()
    await engine.dispose()


@pytest_asyncio.fixture()
async def committing_db_session():
    """Async DB-sessie voor tests die echte commits vereisen.

    Gebruik wanneer de te testen code intern session.commit() aanroept
    (bv. PerformTikaAnalysis.execute() voor voortgangsupdates). De rollback-
    aanpak van async_db_session werkt dan niet meer.

    Cleanup via expliciete DELETE-statements per archive_id na de test.

    Gebruik in een test:
        session, cleanup_ids = committing_db_session
        archive_id = ...
        cleanup_ids.append(archive_id)   # registreer voor cleanup
        await session.commit()           # commit de setup zelf
        await PerformTikaAnalysis(session).execute(archive_id, task_id)
    """
    engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
    session = AsyncSession(engine, expire_on_commit=False)
    archive_ids: list[uuid.UUID] = []
    try:
        yield session, archive_ids
    finally:
        for aid in archive_ids:
            for stmt in [
                "DELETE FROM tika_analyses WHERE file_id IN (SELECT id FROM files WHERE archive_id = :aid)",
                "DELETE FROM ner WHERE file_id IN (SELECT id FROM files WHERE archive_id = :aid)",
                "DELETE FROM analysis_tasks WHERE archive_id = :aid",
                "DELETE FROM files WHERE archive_id = :aid",
                "DELETE FROM archives WHERE id = :aid",
            ]:
                await session.execute(text(stmt), {"aid": str(aid)})
        await session.commit()
        await session.close()
    await engine.dispose()


# scope="session" means this engine is created once for the entire test run,
# not once per test. Creating a DB engine is expensive, so we reuse it.
# fixture == preparatory work before the actual testing
@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(DATABASE_URL)
    yield engine
    engine.dispose()  # close all connections when the test session ends


# This fixture opens a single DB connection and hands it to the test.
# After the test finishes, conn.rollback() undoes everything the test wrote —
# so no test data leaks into the real database.
@pytest.fixture()
def db_conn(db_engine):
    with db_engine.connect() as conn:
        yield conn
        conn.rollback()  # undo all inserts/updates made during the test


# The ner table has foreign keys to archives, files and archive_analysis.
# Those rows must exist before we can insert into ner, so this fixture
# creates the minimum required parent records first.
#
# It uses a SAVEPOINT (a named checkpoint inside the transaction) so that
# after the test we can roll back only to that point, cleanly removing the
# prerequisite rows along with any ner rows the test inserted.
@pytest.fixture()
def ner_prerequisites(db_conn):
    archive_id = uuid.uuid4()
    file_id = uuid.uuid4()
    analysis_id = uuid.uuid4()

    # 1. Insert a minimal archive row (required by files and archive_analysis)
    db_conn.execute(text("""
        INSERT INTO archives (id, name, root_path, analysis_status, file_count, directory_count, total_size_bytes)
        VALUES (:id, :name, :root_path, 'pending', 0, 0, 0)
    """), {"id": str(archive_id), "name": "test-archief", "root_path": f"/tmp/test/{archive_id}"})

    # 2. Insert a minimal file row (required by ner.file_id)
    db_conn.execute(text("""
        INSERT INTO files (id, archive_id, name, full_path, relative_path, is_directory)
        VALUES (:id, :archive_id, :name, :full_path, :relative_path, false)
    """), {
        "id": str(file_id),
        "archive_id": str(archive_id),
        "name": "brief_1923.txt",
        "full_path": f"/tmp/test/{archive_id}/brief_1923.txt",
        "relative_path": "brief_1923.txt",
    })

    # 3. Insert a minimal archive_analysis row (required by ner.analysis_id)
    #    type must be one of: STT, NER, SUMMARY  (defined in the 0004 migration enum)
    #    status must be one of: STARTED, FAILED, COMPLETED
    db_conn.execute(text("""
        INSERT INTO archive_analysis (id, archive_id, type, model, status)
        VALUES (:id, :archive_id, 'NER', 'nl_core_news_lg', 'STARTED')
    """), {"id": str(analysis_id), "archive_id": str(archive_id)})

    # Mark this point in the transaction so we can roll back to it after the test.
    # Everything inserted above (and by the test itself) will be undone by the
    # ROLLBACK TO SAVEPOINT at the end — the outer db_conn fixture then rolls
    # back the whole transaction, leaving the database completely unchanged.
    db_conn.execute(text("SAVEPOINT prereqs"))

    # Yield the generated IDs to the test so it can reference the parent rows
    yield {"archive_id": archive_id, "file_id": file_id, "analysis_id": analysis_id}

    db_conn.execute(text("ROLLBACK TO SAVEPOINT prereqs"))
