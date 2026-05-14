"""
Script: extract text content from the database into a pandas DataFrame.

Joins files with their tika_analyses to get the extracted text per file.
Fetches records in batches using LIMIT/OFFSET. For now stops after MAX_BATCHES
batches so you can inspect the data without loading everything.

Run from anywhere in the project:
    python backend/scripts/extract_sample_db_to_df.py

Requires:
    - pip install pandas

-------------------------------------------------------------------------------
Schema: files
-------------------------------------------------------------------------------
| column        | type      | example                                         |
|---------------|-----------|-------------------------------------------------|
| id            | UUID      | 3f2a1b4c-1234-5678-abcd-ef0123456789            |
| archive_id    | UUID      | 7e1d0c3b-abcd-1234-5678-fedcba987654            |
| parent_id     | UUID|NULL | 1a2b3c4d-... (NULL for root-level files)        |
| name          | str       | rapport_2023.pdf                                |
| full_path     | str       | C:/data/archief/rapport_2023.pdf                |
| relative_path | str       | archief/rapport_2023.pdf                        |
| is_directory  | bool      | False                                           |
| extension     | str|NULL  | .pdf                                            |
| size_bytes    | int|NULL  | 204800                                          |
| sha256_hash   | str|NULL  | a3f1bc...                                       |
| created_at    | datetime  | 2023-01-15 09:30:00+00                          |
| modified_at   | datetime  | 2023-06-20 14:45:00+00                          |
| discovered_at | datetime  | 2024-03-01 10:00:00+00                          |

-------------------------------------------------------------------------------
Schema: tika_analyses
-------------------------------------------------------------------------------
| column             | type      | example                                    |
|--------------------|-----------|--------------------------------------------|
| id                 | UUID      | 9c8b7a6d-...                               |
| file_id            | UUID      | 3f2a1b4c-... (FK → files.id)               |
| mime_type          | str|NULL  | application/pdf                            |
| tika_parser        | str|NULL  | org.apache.tika.parser.pdf.PDFParser       |
| content            | str|NULL  | "Dit is de geëxtraheerde tekst van het..." |
| language           | str|NULL  | nl                                         |
| word_count         | int|NULL  | 1842                                       |
| author             | str|NULL  | Jan Janssen                                |
| content_created_at | datetime  | 2022-11-10 08:00:00+00                     |
| analyzed_at        | datetime  | 2024-03-01 10:05:00+00                     |
"""

import os
import time
from pathlib import Path

from loguru import logger

logger.info("Loading dependencies...")

import pandas as pd
from dotenv import load_dotenv
from sqlalchemy import create_engine, text

# ---------------------------------------------------------------------------
# Load environment
# ---------------------------------------------------------------------------
BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

DATABASE_URL = os.environ.get("DATABASE_URL_SYNC")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL_SYNC is not set in .env")

# ---------------------------------------------------------------------------
# Config: database extraction
# ---------------------------------------------------------------------------
BATCH_SIZE = 100
MAX_BATCHES = 3  # set to None to fetch all records

# ---------------------------------------------------------------------------
# Queries
# ---------------------------------------------------------------------------
logger.info("Connecting to database...")
engine = create_engine(DATABASE_URL)

count_query = text("""
    SELECT COUNT(*)
    FROM files f
    JOIN tika_analyses t ON t.file_id = f.id
    WHERE t.content IS NOT NULL
""")

batch_query = text("""
    SELECT
        f.id          AS file_id,
        f.name        AS file_name,
        f.full_path   AS file_path,
        f.extension,
        tika.language,
        tika.word_count,
        tika.content
    FROM files f
    JOIN tika_analyses tika ON tika.file_id = f.id
    WHERE tika.content IS NOT NULL
    ORDER BY f.id
    LIMIT :limit OFFSET :offset
""")
#TODO: DIT SLUIT WEL DE MISLUKE TIKA'S UIT
# ---------------------------------------------------------------------------
# Fetch in batches
# ---------------------------------------------------------------------------
all_rows = []
columns = None

with engine.connect() as conn:
    logger.info("Counting total records in DB...")
    total = conn.execute(count_query).scalar()
    logger.info("Total analyzed files in DB: {}", total)

    offset = 0
    batch_num = 0

    while True:
        if MAX_BATCHES is not None and batch_num >= MAX_BATCHES:
            logger.info("Reached MAX_BATCHES ({}), stopping.", MAX_BATCHES)
            break

        logger.info("Fetching batch {} (offset {})...", batch_num + 1, offset)
        t0 = time.perf_counter()
        result = conn.execute(batch_query, {"limit": BATCH_SIZE, "offset": offset})
        rows = result.fetchall()
        elapsed = time.perf_counter() - t0

        if not rows:
            logger.info("No more records.")
            break

        if columns is None:
            columns = result.keys()

        all_rows.extend(rows)
        logger.info(
            "Batch {}: got {} records in {:.2f}s (total fetched: {})",
            batch_num + 1, len(rows), elapsed, len(all_rows)
        )

        offset += BATCH_SIZE
        batch_num += 1

logger.info("Fetched {} / {} records", len(all_rows), total)

df = pd.DataFrame(all_rows, columns=columns)
logger.success("DataFrame created with shape {}", df.shape)
print(df.head())
