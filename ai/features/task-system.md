Create a reusable analysis task tracking system and integrate
Tika processing into the ingestion flow.

## Task Tracking (reusable for all future analyses)

1. New model in app/analysis/models.py: AnalysisTask
   (id, archive_id FK, task_type VARCHAR, status enum
   [pending/running/completed/failed], total_files, processed,
   failed_count, started_at, completed_at).
   Generate Alembic migration.

2. task_tracker.py — shared service for creating tasks,
   updating progress counts, and streaming progress via SSE.

3. GET /api/analysis/tasks/{task_id}/progress — SSE endpoint
   using FastAPI StreamingResponse. Polls the task record and
   yields progress events. Closes when completed or failed.

4. GET /api/analysis/tasks/archive/{archive_id} — returns all
   tasks for an archive (so the frontend can show status).

## Tika Integration (automatic, part of ingestion)

5. Tika processing starts AUTOMATICALLY after the file
   inventory phase completes during ingestion. It is NOT
   triggered by a separate user action.

   The ingestion flow becomes:
   a) User picks folder → backend walks files via agent →
   stores file inventory in database (existing code)
   b) Immediately after inventory completes: backend creates
   an AnalysisTask with task_type="tika", then kicks off
   Tika processing as a background asyncio task
   c) The ingestion endpoint returns the archive AND the
   tika task_id so the frontend can immediately subscribe
   to the progress stream

6. Tika processing loop (in app/analysis/tika_service.py):
    - Iterate over all files in the archive
    - For each file: pull content from agent
      (GET /file-content?path=...), send to Tika
      (PUT to TIKA_URL/tika), store extracted text and
      metadata, update task progress
    - Skip directories

8. All datetime fields must be datetime objects, not strings.

## Future analyses (NER, classification, etc.)

These will be triggered manually by the user via separate
endpoints like POST /api/analysis/ner/{archive_id}.
They will reuse the same AnalysisTask model and SSE progress
endpoint. Do NOT implement these yet — just make sure the
task system is designed to support them.

## Key point
The frontend will show a progress bar on the archive card
immediately after ingestion starts. It subscribes to the
SSE stream using the tika task_id returned from the
ingestion endpoint.