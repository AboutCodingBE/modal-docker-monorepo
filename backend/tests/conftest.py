import os
import uuid
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# Load DATABASE_URL_SYNC from backend/.env (same as the other scripts)
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL_SYNC")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL_SYNC is not set in .env")


# scope="session" means this engine is created once for the entire test run,
# not once per test. Creating a DB engine is expensive, so we reuse it.
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
