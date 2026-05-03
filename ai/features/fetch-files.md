Add a new endpoint to fetch all files in a specific folder
of an archive, including their Tika analysis data.

## Endpoint
GET /api/archives/{archive_id}/folder/{folder_id}/files

Returns all files that are direct children of the given folder
(where parent_id matches folder_id and is_directory=false).

## Response
Each file should include:
- id
- name
- relative_path
- extension
- size_bytes
- mime_type (from the related tika_analyses table, joined via file_id)

Response example:
{
"folder_id": "uuid",
"folder_name": "Briefwisseling",
"files": [
{
"id": "uuid",
"name": "brief-1920.pdf",
"relative_path": "Briefwisseling/brief-1920.pdf",
"extension": ".pdf",
"size_bytes": 245000,
"mime_type": "application/pdf"
}
]
}

## Implementation notes
- Join files with tika_analyses using file_id to get the mime_type
- Files without a tika analysis should still be returned with
  mime_type as null
- Only return files, not subdirectories (is_directory=false)
- Use async SQLAlchemy with the existing database session
- Add this to the existing archives feature or wherever the
  folder endpoint currently lives
- Handle edge cases: folder not found (404), folder has no
  files (return empty array)