"""
Script: NER benchmark — vergelijkt welke named entities verschillende algoritmes vinden.

Output: results.json — één array met per document een object zoals:
{
  "doc_id": "abc123",
  "file_name": "brief_1923.txt",
  "text_preview": "Jan Janssen schreef aan het...",
  "results": {
    "spacy": {
      "duration_ms": 42,
      "NER_persons": ["Jan Janssen"],
      "NER_persons_count": 1,
      "NER_organisations": ["Amsab-ISG"],
      "NER_organisations_count": 1,
      "NER_locations": [],
      "NER_locations_count": 0
    },
    "gliner": {},
    "ollama": {}
  }
}

Run:
    python backend/scripts/ner_benchmark.py

Requires:
    pip install spacy
    python -m spacy download nl_core_news_lg
"""

import json
import os
import time
from pathlib import Path

from loguru import logger

logger.info("Loading dependencies...")

import spacy
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
# Config
# ---------------------------------------------------------------------------
BATCH_SIZE = 100
MAX_BATCHES = 3          # set to None to fetch all records
TEXT_PREVIEW_LEN = 120
SPACY_MODEL = "nl_core_news_lg"
OUTPUT_JSON = Path(__file__).resolve().parent / "results.json"

# spaCy label → categorie mapping (nl_core_news_lg labels)
SPACY_LABEL_MAP = {
    "PER":  "NER_persons",
    "ORG":  "NER_organisations",
    "LOC":  "NER_locations",
    "GPE":  "NER_locations",
}

# ---------------------------------------------------------------------------
# Fetch data from DB
# ---------------------------------------------------------------------------
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
        tika.content
    FROM files f
    JOIN tika_analyses tika ON tika.file_id = f.id
    WHERE tika.content IS NOT NULL
    ORDER BY f.id
    LIMIT :limit OFFSET :offset
""")

all_rows = []

with engine.connect() as conn:
    total = conn.execute(count_query).scalar()
    logger.info("Total analyzed files in DB: {}", total)

    offset = 0
    batch_num = 0

    while True:
        if MAX_BATCHES is not None and batch_num >= MAX_BATCHES:
            logger.info("Reached MAX_BATCHES ({}), stopping.", MAX_BATCHES)
            break

        result = conn.execute(batch_query, {"limit": BATCH_SIZE, "offset": offset})
        rows = result.fetchall()

        if not rows:
            logger.info("No more records.")
            break

        all_rows.extend(rows)
        logger.info("Batch {}: {} records (total: {})", batch_num + 1, len(rows), len(all_rows))
        offset += BATCH_SIZE
        batch_num += 1

logger.success("Fetched {} documents", len(all_rows))

# ---------------------------------------------------------------------------
# spaCy NER
# ---------------------------------------------------------------------------
logger.info("Loading spaCy model '{}'...", SPACY_MODEL)
nlp = spacy.load(SPACY_MODEL, disable=["tok2vec", "tagger", "parser", "attribute_ruler", "lemmatizer"])


def run_spacy(text: str) -> dict:
    t0 = time.perf_counter()
    doc = nlp(text or "")
    duration_ms = round((time.perf_counter() - t0) * 1000)

    buckets: dict[str, list[str]] = {
        "NER_persons": [],
        "NER_organisations": [],
        "NER_locations": [],
    }
    for ent in doc.ents:
        category = SPACY_LABEL_MAP.get(ent.label_)
        if category:
            value = ent.text.strip()
            if value and value not in buckets[category]:
                buckets[category].append(value)

    return {
        "duration_ms": duration_ms,
        "NER_persons":            buckets["NER_persons"],
        "NER_persons_count":      len(buckets["NER_persons"]),
        "NER_organisations":      buckets["NER_organisations"],
        "NER_organisations_count": len(buckets["NER_organisations"]),
        "NER_locations":          buckets["NER_locations"],
        "NER_locations_count":    len(buckets["NER_locations"]),
    }


# ---------------------------------------------------------------------------
# Build results array
# ---------------------------------------------------------------------------
results = []

for i, row in enumerate(all_rows):
    file_id, file_name, content = row.file_id, row.file_name, row.content
    text = content or ""

    logger.info("[{}/{}] Processing: {}", i + 1, len(all_rows), file_name)

    doc_result = {
        "doc_id":       str(file_id),
        "file_name":    file_name,
        "text_preview": text[:TEXT_PREVIEW_LEN].replace("\n", " "),
        "results": {
            "spacy":  run_spacy(text),
            "gliner": {},
            "ollama": {},
        },
    }
    results.append(doc_result)

# ---------------------------------------------------------------------------
# Write output
# ---------------------------------------------------------------------------
OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
logger.success("Saved {} documents to {}", len(results), OUTPUT_JSON)
