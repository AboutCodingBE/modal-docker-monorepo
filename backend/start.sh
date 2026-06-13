#!/bin/bash
set -e

echo "Running database migrations..."
alembic upgrade head

echo "Checking NLP model..."
python -c "import spacy; spacy.load('nl_core_news_lg')" || { echo "ERROR: NLP model not found in image"; exit 1; }

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000

#WARNING: Albemic was facing issues in this file because git pull converts /n into /r/n, in IDE change CRLF<>LF