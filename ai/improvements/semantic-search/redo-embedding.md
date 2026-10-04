# Redo Embedding

## Context

When embedding settings change (`embedding_chunk_size`, `embedding_max_chunks_per_file`), existing embeddings become stale and need to be regenerated. The pipeline's resumability check (`EmbeddingRepository.exists()`) skips files that already have embeddings, so re-running the analysis without clearing first has no effect.

## Implementation plan

### Backend

1. `EmbeddingRepository.delete_for_archive(archive_id)` — `DELETE FROM embeddings WHERE file_id IN (SELECT id FROM files WHERE archive_id = ?)`.
2. Delete (or reset) the existing COMPLETED `archive_analysis` row for EMBEDDING — otherwise `completed_analysis_types` stays "done" on the archive card while re-indexing is in progress.
3. New endpoint `POST /api/archives/{archive_id}/embeddings/reindex` that:
   - Calls `delete_for_archive`
   - Removes/resets the old `archive_analysis` EMBEDDING row
   - Calls the existing start-analysis flow for EMBEDDING (reuses `CreateEmbeddingsForArchive`)
   - Returns `{ task_id }` for progress tracking

### Frontend

- A **"Opnieuw indexeren"** button on the semantic search page.
- On click: call the reindex endpoint, then track progress via SSE on the returned `task_id` (same flow as the initial indexing step).

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
