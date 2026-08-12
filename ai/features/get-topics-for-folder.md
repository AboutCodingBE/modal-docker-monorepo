# Use Case

Create a new endpoint to fetch aggregated topic detection results for a single folder. This is called when a user selects a folder in the archive browser and clicks the Topics tab in the detail panel (folder detail tabs: Overzicht, Samenvatting, and now NER/Topics). Results are fetched per folder, not in bulk.

Folder-level topic results already exist in the database: the bottom-up topic aggregation (`CreateTopicDetectionForArchive` / `TopicDetectionRepository.persist_folder`) runs after file-level topic detection and writes one `TopicDetection` row per folder, with `file_id` set to the folder's own `File` id and `parent_folder_id` set to the folder's parent. The `topics` column already contains only the top-N topics for that folder (capped by `settings.topic_folder_top_n` at aggregation time), each stored as `{"topic": "...", "count": N}` where `count` is the aggregated frequency across the folder's files.

This feature only reads those already-aggregated rows — it does not perform any aggregation itself.

The input of this use case:
- `archive_id` (UUID) — the archive
- `folder_id` (UUID) — the specific folder to get topic results for

Input mechanism of this use case:
`GET /api/archives/{archive_id}/folders/{folder_id}/topics`

The output of this feature:
A flat list of topics for the given folder. Mirrors the file-level topics response exactly — no counts, just the topic names. The `count` field on each stored topic is only used to determine the top-N ranking during aggregation; it is discarded when building this response.

Response when topic results exist:
```json
{
  "folder_id": "...",
  "folder_name": "Partijbestuur 1978",
  "topics": ["Werkgelegenheid", "Onderwijs", "Sociale impact"],
  "total_topics": 3
}
```

Response when no topic results exist for this folder:
```json
{
  "folder_id": "...",
  "folder_name": "Partijbestuur 1978",
  "topics": [],
  "total_topics": 0
}
```

# Business Rules

- Fetch topic results from the `topic_detection` table where `file_id` matches the given `folder_id`. Folder aggregation rows are stored in the same table as file rows — they are distinguished only by the fact that `file_id` points to a `File` with `is_directory = True`.
- The `topics` column is a JSONB array of `{"topic": str, "count": int}` objects. Extract only the `topic` value from each object, in the order returned by the database, to build the response list. Do not expose `count` in the response.
- If multiple topic detection records exist for the same folder (from different analysis runs), return the most recent one. Determine recency the same way as the file endpoint: join with `archive_analysis` and order by `archive_analysis.date` descending (or highest `analysis_id`).
- If no topic detection record exists for the folder, return an empty list and `total_topics: 0`.
- Null/missing JSONB array should be treated as an empty list in the response.
- The folder must belong to the given archive (verify `archive_id` match).
- The target `File` must have `is_directory = True`. Return 404 if the folder doesn't exist, doesn't belong to the archive, or is actually a file (not a directory).
- `total_topics` is the length of the extracted topics list.
- This feature must not modify or trigger folder topic aggregation — that logic already exists in `CreateTopicDetectionForArchive` / `TopicDetectionRepository.persist_folder` and is out of scope.

# Component Overview

## New feature folder: get_topics_for_folder

**New folder:** `backend/app/get_topics_for_folder/`

Following the same feature folder pattern as `get_topics_for_file`.

### `backend/app/get_topics_for_folder/__init__.py`
Empty file.

### `backend/app/get_topics_for_folder/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.get_topics_for_folder.get_topics_for_folder import GetTopicsForFolder

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/archives/{archive_id}/folders/{folder_id}/topics")
async def get_topics_for_folder(
    archive_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await GetTopicsForFolder(db).execute(archive_id, folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result
```

## GetTopicsForFolder (flow controller)

The input of this component:
- `archive_id` (UUID)
- `folder_id` (UUID)

The output of this component:
- `dict` matching the response structure in the Use Case section, or `None` if the folder is not found / not a directory / not in this archive.

### `backend/app/get_topics_for_folder/get_topics_for_folder.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_topics_for_folder.repository import TopicsForFolderRepository


class GetTopicsForFolder:
    def __init__(self, session: AsyncSession):
        self._repo = TopicsForFolderRepository(session)

    async def execute(self, archive_id: uuid.UUID, folder_id: uuid.UUID) -> dict | None:
        # Verify the folder exists, belongs to this archive, and is a directory
        folder = await self._repo.get_folder(archive_id, folder_id)
        if folder is None:
            return None

        topic_detection = await self._repo.get_topics_for_folder(folder_id)

        topics = self._extract_topics(topic_detection.topics) if topic_detection else []

        return {
            "folder_id": str(folder_id),
            "folder_name": folder.name,
            "topics": topics,
            "total_topics": len(topics),
        }

    @staticmethod
    def _extract_topics(entries: list[dict] | None) -> list[str]:
        """Pull the 'topic' name out of each {"topic": ..., "count": ...} object."""
        return [e["topic"] for e in (entries or [])]
```

This component depends on:
- `TopicsForFolderRepository`

## TopicsForFolderRepository

Data access for folder topic lookups.

### `backend/app/get_topics_for_folder/repository.py`

```python
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TopicDetection, ArchiveAnalysis


class TopicsForFolderRepository:
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

    async def get_topics_for_folder(self, folder_id: uuid.UUID) -> TopicDetection | None:
        """Get the most recent aggregated topic detection result for a folder.

        Folder-level topic rows are stored in the same `topic_detection` table
        as file-level rows, with `file_id` set to the folder's own id (see
        TopicDetectionRepository.persist_folder).
        """
        result = await self._session.execute(
            select(TopicDetection)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == TopicDetection.analysis_id)
            .where(TopicDetection.file_id == folder_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
```

This component depends on:
- `File`, `TopicDetection`, `ArchiveAnalysis` models from `app.shared.models`

## Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.get_topics_for_folder.router import router as get_topics_for_folder_router

app.include_router(get_topics_for_folder_router)
```

## No changes needed

- **topic_detection table / migrations** — table already supports folder rows (migration 0011, JSONB `topics` column), no schema changes needed
- **Folder topic aggregation** — already implemented in `CreateTopicDetectionForArchive` / `TopicDetectionRepository.persist_folder`, not touched by this feature
- **`get_topics_for_file`** — untouched, remains a separate endpoint/feature folder
- **Frontend** — not consuming this endpoint yet