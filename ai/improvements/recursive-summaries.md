# Bottom-up folder summaries

Bottom-up folder summaries: change the summarization flow so that folder summaries include knowledge of everything beneath them (child files AND child folders), not just direct child files. The root folder of the archive must also receive a summary.

This requires three changes:
1. Add the root folder as a `File` entry during ingestion
2. Change folder retrieval to include the root and sort deepest-first
3. The summary flow already picks up child folder summaries — no query changes needed, only the folder iteration order matters

The input of this use case:
Same as today — `archive_id`, `archive_analysis_id`, `task_id`, `model` passed to `CreateSummariesForArchive.execute()`

Input mechanism of this use case:
Existing async method call — nothing changes at the API level.

The output of this feature:
Same `Summary` rows in the database, but folder summaries now reflect everything below them recursively. The root folder (the archive's top-level directory) also gets a summary row.

# Business Rules

- Folders must be processed bottom-up (deepest first) so that child folder summaries exist before their parent is summarized
- Depth is determined by counting `/` separators in `relative_path`
- The root folder has `relative_path = "."`, `parent_id = None`, `is_directory = True`
- `get_file_summaries_for_folder` (now covering both file and folder children) already works correctly — it selects summaries where `parent_folder_id = folder_id` and `file_id != folder_id`. No changes needed.
- The root folder summary's `parent_folder_id` will be `None` (it has no parent)
- Existing archives that were ingested before this change will NOT have a root folder entry. The summary flow should handle this gracefully — if no root folder is found, skip root summarization (don't crash).

# Component Overview

## Change 1: FolderAnalysis (ingestion)

**File:** `backend/app/ingestion/folder_analysis.py`

Add the root folder entry at the top of the entries list, before the loop over agent results. Insert it right after `discovered_at` is set and `entries = []` is created:

```python
entries.append({
    "archive_id": archive_id,
    "_parent_path": None,
    "name": os.path.basename(folder_path),
    "full_path": folder_path,
    "relative_path": ".",
    "is_directory": True,
    "extension": None,
    "size_bytes": None,
    "sha256_hash": None,
    "created_at": None,
    "modified_at": None,
    "discovered_at": discovered_at,
})
```

Important: normalize `folder_path` with `.rstrip("/")` before using it as `full_path`, to avoid mismatches with `os.path.dirname()` output from child entries.

This component depends on:
- Nothing new — same agent `/files` endpoint

## Change 2: FileRepository in create_summaries_for_archive

**File:** `backend/app/create_summaries_for_archive/file_repository.py`

Rename `get_subfolders` to `get_all_folders`. Changes:
- Remove the `File.parent_id.isnot(None)` filter so the root is included
- Sort results deepest-first by counting `/` in `relative_path`

```python
async def get_all_folders(self, archive_id: uuid.UUID) -> list[dict]:
    """Returns all directories including root, sorted deepest first."""
    result = await self._session.execute(
        select(File).where(
            File.archive_id == archive_id,
            File.is_directory == True,
        )
    )
    folders = [
        {
            "id": f.id,
            "name": f.name,
            "relative_path": f.relative_path,
            "parent_id": f.parent_id,
        }
        for f in result.scalars().all()
    ]
    folders.sort(key=lambda f: f["relative_path"].count("/"), reverse=True)
    return folders
```

This component depends on:
- `File` model (no changes to the model)

## Change 3: CreateSummariesForArchive flow controller

**File:** `backend/app/create_summaries_for_archive/create_summaries_for_archive.py`

In Phase 2, change `file_repo.get_subfolders(archive_id)` to `file_repo.get_all_folders(archive_id)`.

That is the only change in this file. The rest of the Phase 2 logic (iterating folders, calling `get_file_summaries_for_folder`, generating summary via Ollama, persisting) stays exactly the same. Because folders are now sorted deepest-first, by the time a parent folder is processed, its child folder summaries already exist in the database and will be returned by `get_file_summaries_for_folder`.

This component depends on:
- `FileRepository.get_all_folders()` (renamed from `get_subfolders`)
- `SummaryRepository.get_file_summaries_for_folder()` (unchanged)

## No changes needed

- **SummaryRepository** — `get_file_summaries_for_folder` already returns all child summaries (files and folders) for a given `folder_id`. No modification required.
- **Summary model** — no schema changes
- **File model** — no schema changes
- **API endpoints** — no changes
- **Alembic migrations** — no new migrations needed (the root folder is just a regular `File` row)

## Testing notes

- After deploying, you'll need to re-ingest existing archives to get the root folder entry. Or write a one-off script/migration that inserts root folder rows for existing archives.
- To verify: after summarization, check that the root folder (the `File` with `parent_id = NULL` and `is_directory = TRUE`) has a corresponding `Summary` row.
- Verify the summary content of a mid-level folder mentions topics from its grandchild files (proving the bottom-up chain works).