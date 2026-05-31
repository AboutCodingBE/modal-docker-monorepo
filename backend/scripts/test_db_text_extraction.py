"""
Test script: verify database connectivity via SQLAlchemy + psycopg2.

Run from anywhere in the project:
    python backend/scripts/test_db_text_extraction.py

Requires:
    - A .env file in backend/ with DATABASE_URL_SYNC set
    - pip install python-dotenv psycopg2-binary sqlalchemy loguru
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Load environment variables from backend/.env (relative to this script).
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
env_path = BACKEND_DIR / ".env"
load_dotenv(env_path)
logger.info("Loaded .env from {}", env_path.resolve())

DATABASE_URL = os.environ.get("DATABASE_URL_SYNC")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL_SYNC is not set in .env")

# ---------------------------------------------------------------------------
# Connect and query
# ---------------------------------------------------------------------------
logger.info("Connecting to database...")
engine = create_engine(DATABASE_URL)

try:
    with engine.connect() as conn:
        logger.success("Connection successful!")

        # information_schema.table_names is a built-in PostgreSQL view that lists all table_names
        # Filtering on table_schema='public' => only user-created table_names
        result = conn.execute(
            text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
            """)
        )
        # each row is a SQLAlchemy Row object => row = ('table_name',) => row[0] = 'table_name'
        table_names = [row[0] for row in result]

        if table_names:
            logger.info("Found {} public table_names:", len(table_names))
            for table in table_names:
                logger.info("  - {}", table)
        else:
            logger.warning("Connected, but no public table_names found.")

except Exception as e:
    logger.error("Connection failed: {}", e)
    raise
