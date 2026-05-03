Implement an analysis results endpoint that returns all
analysis data for a specific file or folder.

## Endpoint
GET /api/archives/{archive_id}/analysis/{file_id}

This works for both files and folders (both are records in
the files table). The response adapts based on what analysis
data is available.

## Response for a file
{
"file_id": "uuid",
"type": "file",
"summaries": [
{
"analysis_id": "uuid",
"model": "gemma3:1b",
"date": "2026-04-24",
"result": "Dit document beschrijft..."
}
]
}

## Response for a folder
{
"file_id": "uuid",
"type": "folder",
"summaries": [
{
"analysis_id": "uuid",
"model": "gemma3:1b",
"date": "2026-04-24",
"result": "De SOLID-POST map bevat social media posts..."
}
]
}

## Implementation notes
- Query the summary table where file_id matches the requested
  file_id
- Join with archive_analysis to get the model name and date
- The summaries array can contain multiple entries if the same
  file was summarized with different models or in different
  analysis runs
- Return an empty summaries array if no analysis has been done
- The "type" field should be determined from the files table
  (is_directory)
- This endpoint will be extended later with NER results and
  other analysis types — structure it so adding new analysis
  types is just adding new fields to the response
- Handle edge cases: file not found (404), no analysis data
  (return empty arrays)
