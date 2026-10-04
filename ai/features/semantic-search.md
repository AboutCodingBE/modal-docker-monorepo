# Semantic Search

## UX flow

Semantic search is an opt-in feature that requires two one-time setup steps before it can be used.

### Step 1 — Unlock semantic search (once per installation)
The user must download the embedding model (`qwen3-embedding:0.6b`, ~500 MB) from Ollama before anything else works.
This only needs to happen once across the entire application — not per archive.
The UI should make this explicit: a clear "unlock" or "set up semantic search" action with a progress indicator for the download.

### Step 2 — Index an archive (once per archive)
Before search is available for a specific archive, the user must trigger the embedding analysis for that archive.
This runs the embedding pipeline: chunks each file's Tika-extracted text and stores the vectors in the database.
Only requires Tika to have completed — NER and topic detection are not needed.
Once done, the archive is "search-ready" and stays that way unless files are re-ingested.
ok
### Step 3 — Search
With the model downloaded and the archive indexed, the search bar becomes available.
The user enters a natural language query; the backend embeds it and returns the top N most relevant chunks with their source file.

## Technical notes

- Model: `qwen3-embedding:0.6b`, 1024 dimensions, ~500 MB
- Any other Ollama embedding model with 1024-dim output is a drop-in replacement (e.g. `mxbai-embed-large`, `bge-m3`)
- Switching to a model with a different output dimension requires a new DB migration and re-embedding all archives
- The dispatcher in `start_router.py` still needs `EMBEDDING` wired up alongside `ner` and `topic_detection`
- Search endpoint: `GET /api/archives/{archive_id}/search?q=...&top_n=25`
