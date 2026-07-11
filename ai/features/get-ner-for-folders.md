# Use Case

Create a new endpoint to fetch aggregated NER (Named Entity Recognition) results for a single folder. This is called when a user selects a folder in the archive browser and clicks the NER tab in the detail panel (folder detail tabs: Overzicht, Samenvatting, and now NER/Topics). Results are fetched per folder, not in bulk.

Folder-level NER results already exist in the database: the bottom-up NER aggregation (`CreateNerForArchive` / `NerRepository.persist_folder`) runs after file-level NER and writes one `Ner` row per folder, with `file_id` set to the folder's own `File` id and `parent_folder_id` set to the folder's parent. Each of the four category columns (`persons`, `locations`, `organisations`, `misc`) already contains only the top-N entities for that folder (capped by `settings.ner_folder_top_n` at aggregation time), each stored as `{"entity": "...", "count": N}` where `count` is the aggregated frequency across the folder's files.

This feature only reads those already-aggregated rows — it does not perform any aggregation itself.

The input of this use case:
- `archive_id` (UUID) — the archive
- `folder_id` (UUID) — the specific folder to get NER results for

Input mechanism of this use case:
`GET /api/archives/{archive_id}/folders/{folder_id}/ner`

The output of this feature:
NER entities grouped by category (persons, locations, organisations, misc) for the given folder. Mirrors the file-level NER response exactly — no counts, just the entity names. The `count` field on each stored entity is only used to determine the top-N ranking during aggregation; it is discarded when building this response.

Response when NER results exist:
```json
{
  "folder_id": "...",
  "folder_name": "Partijbestuur 1978",
  "persons": ["Wilfried Martens", "Hugo Schiltz", "Nelly Maes"],
  "locations": ["Antwerpen", "Brussel", "Vlaanderen"],
  "organisations": ["Volksunie", "Kamer van Volksvertegenwoordigers"],
  "misc": ["1977", "1978"],
  "total_entities": 8
}
```

Response when no NER results exist for this folder:
```json
{
  "folder_id": "...",
  "folder_name": "Partijbestuur 1978",
  "persons": [],
  "locations": [],
  "organisations": [],
  "misc": [],
  "total_entities": 0
}
```

# Business Rules

- Fetch NER results from the `ner` table where `file_id` matches the given `folder_id`. Folder aggregation rows are stored in the same table as file rows — they are distinguished only by the fact that `file_id` points to a `File` with `is_directory = True`.
- Each of the four columns is a JSONB array of `{"entity": str, "count": int}` objects. Extract only the `entity` value from each object, in the order returned by the database, to build the response lists. Do not expose `count` in the response.
- If multiple NER records exist for the same folder (from different analysis runs), return the most recent one. Determine recency the same way as the file endpoint: join with `archive_analysis` and order by `archive_analysis.date` descending (or highest `analysis_id`).
- If no NER record exists for the folder, return empty arrays and `total_entities: 0`.
- Null/missing JSONB arrays should be treated as empty arrays in the response.
- The folder must belong to the given archive (verify `archive_id` match).
- The target `File` must have `is_directory = True`. Return 404 if the folder doesn't exist, doesn't belong to the archive, or is actually a file (not a directory).
- `total_entities` is the sum of the lengths of the four extracted entity lists (after extracting `entity` from each JSONB object, same calculation as the file endpoint).
- This feature must not modify or trigger folder NER aggregation — that logic already exists in `CreateNerForArchive` / `NerRepository.persist_folder` and is out of scope.

# Component Overview

## New feature folder: get_ner_for_folder

**New folder:** `backend/app/get_ner_for_folder/`

Following the same feature folder pattern as `get_ner_for_file`.

### `backend/app/get_ner_for_folder/__init__.py`
Empty file.

### `backend/app/get_ner_for_folder/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.get_ner_for_folder.get_ner_for_folder import GetNerForFolder

router = APIRouter(prefix="/api", tags=["ner"])


@router.get("/archives/{archive_id}/folders/{folder_id}/ner")
async def get_ner_for_folder(
    archive_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await GetNerForFolder(db).execute(archive_id, folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result
```

## GetNerForFolder (flow controller)

The input of this component:
- `archive_id` (UUID)
- `folder_id` (UUID)

The output of this component:
- `dict` matching the response structure in the Use Case section, or `None` if the folder is not found / not a directory / not in this archive.

### `backend/app/get_ner_for_folder/get_ner_for_folder.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_ner_for_folder.repository import NerForFolderRepository


class GetNerForFolder:
    def __init__(self, session: AsyncSession):
        self._repo = NerForFolderRepository(session)

    async def execute(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> dict | None:
        # Verify the folder exists, belongs to this archive, and is a directory
        folder = await self._repo.get_folder(archive_id, folder_id)
        if folder is None:
            return None

        ner = await self._repo.get_ner_for_folder(folder_id)

        persons = self._extract_entities(ner.persons) if ner else []
        locations = self._extract_entities(ner.locations) if ner else []
        organisations = self._extract_entities(ner.organisations) if ner else []
        misc = self._extract_entities(ner.misc) if ner else []

        return {
            "folder_id": str(folder_id),
            "folder_name": folder.name,
            "persons": persons,
            "locations": locations,
            "organisations": organisations,
            "misc": misc,
            "total_entities": len(persons) + len(locations) + len(organisations) + len(misc),
        }

    @staticmethod
    def _extract_entities(entries: list[dict] | None) -> list[str]:
        """Pull the 'entity' name out of each {"entity": ..., "count": ...} object."""
        return [e["entity"] for e in (entries or [])]
```

This component depends on:
- `NerForFolderRepository`

## NerForFolderRepository

Data access for folder NER lookups.

### `backend/app/get_ner_for_folder/repository.py`

```python
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, Ner, ArchiveAnalysis


class NerForFolderRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_folder(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> File | None:
        """Verify the folder exists, belongs to this archive, and is a directory."""
        result = await self._session.execute(
            select(File).where(
                and_(
                    File.id == folder_id,
                    File.archive_id == archive_id,
                    File.is_directory == True,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_ner_for_folder(self, folder_id: uuid.UUID) -> Ner | None:
        """Get the most recent aggregated NER result for a folder.

        Folder-level NER rows are stored in the same `ner` table as file-level
        rows, with `file_id` set to the folder's own id (see
        NerRepository.persist_folder).
        """
        result = await self._session.execute(
            select(Ner)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == Ner.analysis_id)
            .where(Ner.file_id == folder_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
```

This component depends on:
- `File`, `Ner`, `ArchiveAnalysis` models from `app.shared.models`

## Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.get_ner_for_folder.router import router as get_ner_for_folder_router

app.include_router(get_ner_for_folder_router)
```

## No changes needed

- **NER table / migrations** — table already supports folder rows (migration 0010, JSONB columns), no schema changes needed
- **Folder NER aggregation** — already implemented in `CreateNerForArchive` / `NerRepository.persist_folder`, not touched by this feature
- **`get_ner_for_file`** — untouched, remains a separate endpoint/feature folder
- **Frontend** — not consuming this endpoint yet