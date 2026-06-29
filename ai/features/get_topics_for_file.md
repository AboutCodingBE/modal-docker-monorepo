# Context 1: Backend — File Topics Endpoint

## Use Case

Create a new endpoint to fetch topic detection results for a single file. This is called when a user selects a file in the archive browser and clicks the Topics tab in the detail panel. Results are fetched per file, not in bulk.

The input of this use case:
- `archive_id` (UUID) — the archive
- `file_id` (UUID) — the specific file to get topics for

Input mechanism of this use case:
`GET /api/archives/{archive_id}/files/{file_id}/topics`

The output of this feature:
A flat list of topics detected in the given file. No counts per topic for individual files — just the list.

Response when topic results exist:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "topics": ["Verkiezingsstrategie", "Kandidatenlijst", "Partijorganisatie", "Vlaamse autonomie", "Provinciale politiek"],
  "total_topics": 5
}
```

Response when no topic results exist for this file:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "topics": [],
  "total_topics": 0
}
```

## Business Rules

- Fetch topic results from the `topic_detection` table where `file_id` matches.
- The `topic_detection` table stores topics as a PostgreSQL array (`sa.ARRAY(sa.Text())`). SQLAlchemy returns these as Python lists automatically.
- Ignore the `topics_count` column — calculate `total_topics` from the length of the topics array.
- If multiple topic detection records exist for the same file (from different analysis runs), return the most recent one. Determine recency by joining with `archive_analysis` and ordering by `archive_analysis.date` descending.
- If no topic detection record exists for the file, return an empty array and `total_topics: 0`.
- Null arrays should be treated as empty arrays in the response.
- The file must belong to the given archive (verify `archive_id` match).
- Return 404 if the file doesn't exist or doesn't belong to the archive.

## Component Overview

### New feature folder: get_topics_for_file

**New folder:** `backend/app/get_topics_for_file/`

Following the existing feature folder pattern (same as `get_ner_for_file`).

#### `backend/app/get_topics_for_file/__init__.py`
Empty file.

#### `backend/app/get_topics_for_file/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.get_topics_for_file.get_topics_for_file import GetTopicsForFile

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/archives/{archive_id}/files/{file_id}/topics")
async def get_topics_for_file(
    archive_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await GetTopicsForFile(db).execute(archive_id, file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result
```

#### `backend/app/get_topics_for_file/get_topics_for_file.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_topics_for_file.repository import TopicsForFileRepository


class GetTopicsForFile:
    def __init__(self, session: AsyncSession):
        self._repo = TopicsForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        topic_detection = await self._repo.get_topics_for_file(file_id)

        topics = topic_detection.topics or [] if topic_detection else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "topics": topics,
            "total_topics": len(topics),
        }
```

#### `backend/app/get_topics_for_file/repository.py`

```python
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, TopicDetection, ArchiveAnalysis


class TopicsForFileRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_file(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> File | None:
        """Verify the file exists and belongs to this archive."""
        result = await self._session.execute(
            select(File).where(
                and_(
                    File.id == file_id,
                    File.archive_id == archive_id,
                    File.is_directory == False,
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_topics_for_file(self, file_id: uuid.UUID) -> TopicDetection | None:
        """Get the most recent topic detection result for a file."""
        result = await self._session.execute(
            select(TopicDetection)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == TopicDetection.analysis_id)
            .where(TopicDetection.file_id == file_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
```

### TopicDetection model

Verify that the `TopicDetection` SQLAlchemy model exists in `backend/app/shared/models.py`. It should look like:

```python
class TopicDetection(Base):
    __tablename__ = "topic_detection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    topics: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    topics_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

If it doesn't exist yet, create it following the pattern of the `Ner` model.

### Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.get_topics_for_file.router import router as get_topics_for_file_router

app.include_router(get_topics_for_file_router)
```

### No changes needed

- **topic_detection table / migrations** — table already exists (migration 0009)
- **Frontend** — not consuming this endpoint yet (see Context 2 below)
- **Other endpoints** — no modifications

### Testing Notes

- Call `GET /api/archives/{id}/files/{file_id}/topics` for a file with topic results — verify topics array is populated and `total_topics` matches
- Call for a file without topic results — verify empty array and `total_topics: 0`
- Call with a non-existent `file_id` — should return 404
- Call with a `file_id` that belongs to a different archive — should return 404
- Call with a directory's `file_id` — should return 404
- If a file has topic results from multiple analysis runs, verify only the most recent is returned
- Verify null arrays in the database are returned as empty arrays `[]` in the response

---

# Context 2: Frontend — Topics Tab

## Use Case

Add a "Topics" tab to the file detail panel in the archive browser. When a user selects a file and clicks the Topics tab, the detected topics for that file are displayed as green-colored tags.

The input of this use case:
User selects a file in the archive browser and clicks the "Topics" tab.

Input mechanism of this use case:
Click on the "Topics" tab in the file detail panel (pane 3).

The output of this feature:
The Topics tab shows a flat list of topic tags in green, with a total count at the bottom.

## Wireframe

Refer to the topics wireframe at: `ai/wireframes/topic-tab.html`

## Changes

### File detail panel — add Topics tab

The file detail panel currently has two tabs: Samenvatting, NER. Add a third tab: **Topics**.

Tab order: **Samenvatting | NER | Topics**

### Topics tab content

- A flat list of topic tags (no subcategories, unlike NER)
- Each topic is a green-colored chip/tag
- At the bottom: "**X** topics gedetecteerd in dit bestand" (grey text, top border separator)
- If no topics exist: show "Geen topics beschikbaar"

### Data source

- Call `GET /api/archives/{archive_id}/files/{file_id}/topics` when the Topics tab is clicked (lazy loading, same pattern as NER)
- Response provides: `topics` (array of strings), `total_topics` (count)

### Topic tag styling

All topics use the same color (no categories):
- `background: #ecfdf5`
- `border: 1px solid #a7f3d0`
- `color: #065f46`
- `border-radius: 5px`
- `font-size: 11px`
- `padding: 4px 10px`

### Total line styling
- `font-size: 11px`
- `color: #9ca3af`
- `margin-top: 14px`
- `padding-top: 10px`
- `border-top: 1px solid #f3f4f6`
- Count in bold: `color: #6b7280`

### Folder Topics tab

Not implemented yet — folder topic aggregation is a future feature. Do NOT show a Topics tab for folders in this phase. Same approach as folder NER.

## Component suggestion

Create a reusable **TopicTagsComponent** (similar to the NerTagsComponent from Phase 3) that accepts a list of topic strings and renders them as green tags. This component can be reused later for folder topic aggregation.

## No changes needed

- **Backend** — endpoint ready (Context 1 above)
- **Other tabs** — Samenvatting and NER tabs unchanged
- **Folder detail panel** — no Topics tab added
