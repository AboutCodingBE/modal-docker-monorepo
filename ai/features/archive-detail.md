Implement the archive dashboard API with two endpoints.
Reference the wireframe: top section shows archive-wide stats
(loaded once), middle and bottom sections show folder-level
data (loaded on each folder navigation).

## Important data model context
- The files table has a foreign key to the archive table (archive_id)
- The tika analysis table has a foreign key to the files table
- So to get mime types for an archive: join files → tika analysis,
  filtered by archive_id
- Use the content_type / mime_type from the tika analysis results,
  NOT the file extension from the files table

## Endpoint 1: Archive Stats (top section)
GET /api/archives/{archive_id}/stats

Called once on page load. Returns recursive totals for the
entire archive:
- total_files (int)
- total_folders (int)
- mime_types (list of {mime_type, count}, sorted by count desc)

Query the files table filtering by archive_id. Count files
where is_directory=false for total_files, is_directory=true
for total_folders. Join with the tika analysis table and group
by mime_type for the type distribution.

Response example:
{
"total_files": 1089,
"total_folders": 18,
"mime_types": [
{"mime_type": "application/pdf", "count": 514},
{"mime_type": "image/jpeg", "count": 429},
{"mime_type": "image/tiff", "count": 119},
{"mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "count": 16}
]
}

## Endpoint 2: Folder Contents + Stats (middle + bottom section)
GET /api/archives/{archive_id}/folder?path=/

Called every time the user navigates to a folder. Returns
direct children and stats for that specific folder level only,
NOT recursive.

- path (the current folder path)
- direct_file_count (files directly in this folder, not in subfolders)
- subfolders (list of {name, path} for direct child folders)
- mime_types (list of {mime_type, count} for files directly in
  this folder only, joined with tika analysis table,
  sorted by count desc)

To determine "direct children": query files where archive_id
matches AND parent_id matches the folder record for the given
path. If path is "/" or empty, use files where parent_id is
the root folder.

Response example for path="/":
{
"path": "/",
"direct_file_count": 3,
"subfolders": [
{"name": "Briefwisseling", "path": "/Briefwisseling"},
{"name": "Notariële akten", "path": "/Notariële akten"},
{"name": "Kaarten en plannen", "path": "/Kaarten en plannen"},
{"name": "Foto-archief", "path": "/Foto-archief"},
{"name": "Registers", "path": "/Registers"}
],
"mime_types": [
{"mime_type": "text/markdown", "count": 1},
{"mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "count": 1},
{"mime_type": "application/json", "count": 1}
]
}

## Implementation notes
- Create this as a new feature folder or add to the existing
  archives feature, whichever fits the current project structure.
- Use async SQLAlchemy queries with the existing database session.
- All datetime fields must be datetime objects, not strings.
- Files that have not been processed by Tika yet (no entry in
  the tika analysis table) should still be counted in
  total_files and direct_file_count, but will not appear in
  the mime_types breakdown.
- Handle edge cases: empty folders, root path as "/" or empty
  string, archive not found (404), folders with no Tika
  results yet.