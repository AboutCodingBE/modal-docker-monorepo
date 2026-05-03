Implement the AI summarization feature in the backend.
The Ollama service is already configured in docker-compose
and the database migration for the new tables is done.

## Environment
Add OLLAMA_URL to app/config.py:
- Docker: http://ollama:11434
- Local dev (.env): http://localhost:11434

## Backend endpoint

POST /api/analysis/start
Accepts the following request body:

{
"archiveId": "uuid",
"analysis": [
{ "type": "summary", "model": "gemma3:1b" }
]
}

This always processes the entire archive.

For each entry in the analysis array:
1. Create an ArchiveAnalysis record with status "started"
2. Create an AnalysisTask record for progress tracking
3. Run the analysis as a background asyncio task

The analyses run sequentially — one after another, not
in parallel.

## Use case: create_summaries_for_archive

Create this as app/create_summaries_for_archive/ following
the existing feature folder pattern.

The summarization happens in two phases:

### Phase 1 — File summaries

For each file in the archive:
1. Skip files that are directories (is_directory=true)
2. Skip files that have no Tika-extracted text
3. Skip files with fewer than 30 words of extracted text
4. Skip files that already have a completed summary for
   this archive analysis (for resumability)
5. Send the first 1000 characters of extracted text to
   Ollama:

   POST http://OLLAMA_URL/api/generate
   {
   "model": "<model from request>",
   "prompt": "Geef een antwoord in een korte zin. Geef GEEN verdere toelichting bij je antwoord.\n\nVat deze tekst samen in het Nederlands:\n\n<text>",
   "stream": false
   }

6. Store the result in the Summary table with archive_id,
   analysis_id, parent_folder_id, file_id, and the result
7. Update the AnalysisTask progress (processed count)

### Phase 2 — Folder summaries (summary of summaries)

After all file summaries are created, create a summary
for each subfolder in the archive:

1. Get all subfolders in the archive (files where
   is_directory=true), excluding the root folder
2. For each subfolder, collect all the file summaries
   where parent_folder_id matches that folder
3. If the folder has no file summaries, skip it
4. Concatenate the file summaries into one text block
5. Send to Ollama with prompt:
   "Geef een antwoord in een korte zin. Geef GEEN verdere
   toelichting bij je antwoord.\n\nVat deze samenvattingen
   samen in het Nederlands:\n\n<concatenated summaries>"
6. Store the result in the Summary table with the folder's
   id as file_id and the folder's parent as parent_folder_id

Important: do NOT create a summary of summaries for the
root folder / archive level. Only subfolders get a
summary of summaries. An archive with 3000 files would
produce an impractically long summary.

Update the AnalysisTask progress during Phase 2 as well —
the total should include both file count and subfolder count.

### Completion

After both phases:
- Update ArchiveAnalysis status to "completed"
- On failure, update ArchiveAnalysis status to "failed"

## Error handling

- If a single file fails, log the error, mark that file as
  failed, and continue to the next file
- If 5 consecutive files fail, stop the task entirely and
  mark both the AnalysisTask and ArchiveAnalysis as "failed"
  with message "Repeated failures — processing stopped"
- Catch Ollama connection errors specifically — if Ollama
  is unreachable, fail immediately with "Ollama service
  unavailable"
- Use httpx with timeout=120 seconds for Ollama calls
  (LLM inference can be slow)

## SSE progress endpoint

Reuse the existing GET /api/analysis/tasks/{task_id}/progress
SSE endpoint. The progress events should include:

{
"task_id": "uuid",
"status": "running",
"total_files": 438,
"processed": 127,
"failed_count": 2,
"current_file": "documents/report.pdf",
"percentage": 29
}

## All datetime fields must be datetime objects, not strings.