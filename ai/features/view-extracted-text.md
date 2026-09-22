# Use Case

Let a user view a file's full Tika-extracted text, not just whatever's already shown elsewhere in the UI — with the ability to switch between a short preview and the complete text. This is **file-only**, not folders (folders have no `tika_analyses` row — there's no "raw extracted text" concept for a folder, only its AI-generated summary/NER/topics, which already have their own tabs).

Design decision: **one endpoint, fetched once.** The preview/full toggle is a client-side concern — the frontend fetches the (capped) text a single time and slices the first ~1000 characters for the collapsed view, expanding to the rest already sitting in memory when the user asks to see more. No separate "preview" endpoint, no second round-trip on toggle.

Input mechanism:
`GET /api/files/{file_id}/content`

# Business Rules

- Look up the file's `tika_analyses` row via `file_id` (this is a clean 1:1 relationship — `tika_analyses.file_id` is unique, so unlike analysis results there's no "most recent" ambiguity to resolve here at all).
- If the file doesn't exist, or is a directory (`is_directory = True`), return `404`.
- If the file exists but has no `tika_analyses` row, or its `content` is `NULL`/empty, this is **not an error** — return `200` with `content: null`. This is a normal, expected state (e.g. an image with OCR off, or a file type Tika genuinely couldn't extract anything from), same "missing result is null, not a failure" philosophy used elsewhere in this app (e.g. the export feature's missing-analysis rule).
- No cap on returned content length. Since this is plain, unstyled text (no per-word/entity wrapping, no highlighting), the earlier concern about DOM/memory blowup doesn't actually apply — browsers handle one large text block fine; the real risk with large DOM trees comes from thousands of individual elements, not character count in a single node. If Tika ever produces pathologically large "extracted text" from a mis-parsed/corrupted file (unrelated to genuine document size), that's a distinct, separate problem to address later if it actually occurs — not solved here.
- No character-length setting or constant is introduced for this (unlike `processing_settings`/`export_settings`) — full content is simply returned as-is.

Response shape:
```json
{
  "file_id": "...",
  "content": "de volledige geëxtraheerde tekst..."
}
```

No content extracted:
```json
{
  "file_id": "...",
  "content": null
}
```

# Component Overview

## Repository

**New file:** `backend/app/get_file_content/repository.py`

```python
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TikaAnalysis


class FileContentRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_file(self, file_id: uuid.UUID) -> File | None:
        result = await self._session.execute(
            select(File).where(
                and_(File.id == file_id, File.is_directory == False)  # noqa: E712
            )
        )
        return result.scalar_one_or_none()

    async def get_tika_content(self, file_id: uuid.UUID) -> str | None:
        result = await self._session.execute(
            select(TikaAnalysis.content).where(TikaAnalysis.file_id == file_id)
        )
        row = result.scalar_one_or_none()
        return row
```

## Flow controller

**New file:** `backend/app/get_file_content/get_file_content.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_file_content.repository import FileContentRepository


class GetFileContent:
    def __init__(self, session: AsyncSession):
        self._repo = FileContentRepository(session)

    async def execute(self, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(file_id)
        if file is None:
            return None

        content = await self._repo.get_tika_content(file_id)

        return {
            "file_id": str(file_id),
            "content": content,  # None if no tika_analyses row or empty content
        }
```

## Router

**New file:** `backend/app/get_file_content/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.get_file_content.get_file_content import GetFileContent

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await GetFileContent(db).execute(file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result
```

## Register the router

**File:** `backend/app/main.py`

```python
from app.get_file_content.router import router as get_file_content_router

app.include_router(get_file_content_router)
```

## No changes needed

- **`tika_analyses` table, `TikaRepository`** — untouched, this is a read-only feature over existing data
- **Folders** — explicitly out of scope; no folder-level equivalent exists or is needed
- **`processing_settings`, `export_settings`** — untouched; no new setting introduced by this feature
- **Frontend** — not implemented here; the preview/full toggle is a client-side slice of the single fetched response, no second endpoint or request involved