# Redo Embedding

## Context

When embedding settings change (`embedding_chunk_size`, `embedding_max_chunks_per_file`), existing embeddings become stale and need to be regenerated. The pipeline's resumability check (`EmbeddingRepository.exists()`) skips files that already have embeddings, so re-running the analysis without clearing first has no effect.

## Required steps

1. **Delete existing embeddings** for the archive — remove all rows from the `embeddings` table where `file_id` belongs to the archive, and reset the corresponding `archive_analysis` row (status back to a non-completed state).
2. **Re-run the embedding analysis** — trigger the pipeline as normal; it will now re-embed all files using the current settings.

## UI

A single **"Opnieuw indexeren"** button that executes both steps in sequence. The button should only be visible when the archive is already indexed (i.e. embedding analysis has been completed at least once).

Placement options:
- On the semantic search setup page, next to the step 2 status
- In the embedding settings panel (after saving new settings)

The simplest approach: one button, user is responsible for knowing when a re-index is needed. A future improvement could detect settings changes and prompt automatically.

## Notes

- Changing `embedding_chunk_size` makes all existing embeddings incompatible — full re-index required.
- Changing `embedding_max_chunks_per_file` also requires a full re-index (more or fewer chunks per file than currently stored).
- Changing `search_max_distance` or `search_top_n` does **not** require a re-index — those only affect query time.
