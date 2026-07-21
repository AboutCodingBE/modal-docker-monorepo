# Use Case

Permanently delete an archive by id, along with everything derived from it: the file inventory, Tika text extraction, file categories, NER results, topic detection results, summaries, and analysis run history. This is a database-only deletion — the original source files/folders on the user's filesystem, which the archive merely indexes, are never touched.

This will later be triggered from the trash-bin icon on the archive card in the frontend. This context covers only the backend endpoint.

The input of this use case:
- `archive_id` (UUID) — the archive to delete

Input mechanism of this use case:
`DELETE /api/archives/{archive_id}`

The output of this feature:
- `204 No Content` on successful deletion, no response body.
- `404 Not Found` if no archive with that id exists.

# Business Rules

- Verify the archive exists before doing anything. Return 404 if it doesn't. Do not distinguish "already deleted" from "never existed" — both are 404.
- If the archive currently has a running analysis (`ArchiveAnalysis.status == STARTED`), cancel it first, before deleting: set its status to `CANCELLED`. This mirrors the existing cancellation behavior used during application shutdown (`cancel_all_analyses` feature), but scoped to this single `archive_id` instead of all archives. If the existing shutdown cancellation logic can be reused/parameterized by `archive_id`, prefer that over duplicating the logic.
- After cancellation, delete the `Archive` row itself. All of the following must be gone afterward, for this archive only:
    - `files` (the full file/folder tree, including folder-level rows)
    - `tika_analyses`
    - `generic_types`
    - `ner` (both file-level and folder-level aggregated rows)
    - `topic_detection` (both file-level and folder-level aggregated rows)
    - `summary`
    - `archive_analysis`
    - `analysis_tasks`
- Do not write manual per-table delete statements for the child tables above. Every one of them already has an `ON DELETE CASCADE` foreign key back to `archives` (directly via `archive_id`, or transitively via `files.archive_id` → `files.id` for `tika_analyses`/`generic_types`). A single `DELETE` on the `Archive` row is expected to cascade through all of them at the database level. Verify this cascade actually fires end-to-end as part of implementing/testing this feature — do not assume it works without checking.
- Never delete, move, or otherwise touch anything on the filesystem. This feature only removes the app's database records about the archive.
- Deletion is permanent. There is no soft-delete, no undo, and no confirmation step at the backend level (any "are you sure?" confirmation is a frontend concern, out of scope here).

# Component Overview

## Router

**File:** `backend/app/delete_archive/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.delete_archive.delete_archive import DeleteArchive

router = APIRouter(prefix="/api", tags=["archives"])


@router.delete("/archives/{archive_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deleted = await DeleteArchive(db).execute(archive_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Archive not found")
```

**New folder:** `backend/app/delete_archive/`, with an empty `__init__.py`, following the existing feature folder pattern.

## DeleteArchive (flow controller)

Orchestrates the deletion: verify the archive exists, cancel any running analysis for it, then delete the archive row (letting the database cascade handle child records).

The input of this component:
- `archive_id` (UUID)

The output of this component:
- `bool` — `True` if the archive was found and deleted, `False` if no such archive existed.

**File:** `backend/app/delete_archive/delete_archive.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.delete_archive.repository import DeleteArchiveRepository


class DeleteArchive:
    def __init__(self, session: AsyncSession):
        self._repo = DeleteArchiveRepository(session)

    async def execute(self, archive_id: uuid.UUID) -> bool:
        archive = await self._repo.get_archive(archive_id)
        if archive is None:
            return False

        await self._repo.cancel_running_analyses(archive_id)
        await self._repo.delete_archive(archive)
        await self._repo.commit()
        return True
```

This component depends on:
- `DeleteArchiveRepository`

## DeleteArchiveRepository

Data access for looking up the archive, cancelling its running analyses, and deleting it.

**File:** `backend/app/delete_archive/repository.py`

```python
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, ArchiveAnalysis, ArchiveAnalysisStatus


class DeleteArchiveRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_archive(self, archive_id: uuid.UUID) -> Archive | None:
        result = await self._session.execute(
            select(Archive).where(Archive.id == archive_id)
        )
        return result.scalar_one_or_none()

    async def cancel_running_analyses(self, archive_id: uuid.UUID) -> None:
        """Mark any STARTED analyses for this archive as CANCELLED before deletion.

        Mirrors the cancellation behavior of the existing cancel_all_analyses
        feature (used on shutdown), but scoped to a single archive. If that
        feature already exposes a reusable, archive-scoped method, call it
        here instead of duplicating this query.
        """
        await self._session.execute(
            update(ArchiveAnalysis)
            .where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.status == ArchiveAnalysisStatus.STARTED,
            )
            .values(status=ArchiveAnalysisStatus.CANCELLED)
        )

    async def delete_archive(self, archive: Archive) -> None:
        """Delete the archive row. All child rows (files, tika_analyses,
        generic_types, ner, topic_detection, summary, archive_analysis,
        analysis_tasks) are expected to cascade-delete via existing
        ON DELETE CASCADE foreign keys.
        """
        await self._session.delete(archive)

    async def commit(self) -> None:
        await self._session.commit()
```

This component depends on:
- `Archive`, `ArchiveAnalysis`, `ArchiveAnalysisStatus` from `app.shared.models`

## Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.delete_archive.router import router as delete_archive_router

app.include_router(delete_archive_router)
```

## No changes needed

- **Migrations** — no schema changes needed; all required `ON DELETE CASCADE` foreign keys already exist
- **Filesystem / agent** — not involved; this feature never touches files on disk
- **Frontend** — not wired up yet; the trash-bin icon on the archive card will call this endpoint in a later phase, out of scope here