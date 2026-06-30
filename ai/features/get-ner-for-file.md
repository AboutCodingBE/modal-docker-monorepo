# Use Case

Create a new endpoint to fetch NER (Named Entity Recognition) results for a single file. This is called when a user selects a file in the archive browser and clicks the NER tab in the detail panel. Results are fetched per file, not in bulk.

The input of this use case:
- `archive_id` (UUID) — the archive
- `file_id` (UUID) — the specific file to get NER results for

Input mechanism of this use case:
`GET /api/archives/{archive_id}/files/{file_id}/ner`

The output of this feature:
NER entities grouped by category (persons, locations, organisations, misc) for the given file. No counts per entity for individual files — just the list of entities found.

Response when NER results exist:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "persons": ["Michael Van Hees", "Wilfried Martens", "Hugo Schiltz", "Nelly Maes"],
  "locations": ["Antwerpen", "Brussel", "Vlaanderen", "Leuven"],
  "organisations": ["Volksunie", "Partijbestuur", "Kamer van Volksvertegenwoordigers"],
  "misc": ["12 maart 1978", "1977"],
  "total_entities": 14
}
```

Response when no NER results exist for this file:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "persons": [],
  "locations": [],
  "organisations": [],
  "misc": [],
  "total_entities": 0
}
```

# Business Rules

- Fetch NER results from the `ner` table where `file_id` matches.
- The `ner` table stores entities as PostgreSQL arrays (`sa.ARRAY(sa.Text())`). SQLAlchemy returns these as Python lists automatically.
- Ignore the `_count` columns (`persons_count`, `locations_count`, etc.) — calculate `total_entities` by summing the lengths of the four arrays.
- If multiple NER records exist for the same file (from different analysis runs), return the most recent one. Determine recency by joining with `archive_analysis` and ordering by `archive_analysis.date` descending, or by using the highest `analysis_id`.
- If no NER record exists for the file, return empty arrays and `total_entities: 0`.
- Null arrays should be treated as empty arrays in the response.
- The file must belong to the given archive (verify `archive_id` match).
- Return 404 if the file doesn't exist or doesn't belong to the archive.

# Component Overview

## New feature folder: get_ner_for_file

**New folder:** `backend/app/get_ner_for_file/`

Following the existing feature folder pattern.

### `backend/app/get_ner_for_file/__init__.py`
Empty file.

### `backend/app/get_ner_for_file/router.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.get_ner_for_file.get_ner_for_file import GetNerForFile

router = APIRouter(prefix="/api", tags=["ner"])


@router.get("/archives/{archive_id}/files/{file_id}/ner")
async def get_ner_for_file(
    archive_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await GetNerForFile(db).execute(archive_id, file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result
```

### `backend/app/get_ner_for_file/get_ner_for_file.py`

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.get_ner_for_file.repository import NerForFileRepository


class GetNerForFile:
    def __init__(self, session: AsyncSession):
        self._repo = NerForFileRepository(session)

    async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
        # Verify the file exists and belongs to this archive
        file = await self._repo.get_file(archive_id, file_id)
        if file is None:
            return None

        ner = await self._repo.get_ner_for_file(file_id)

        persons = ner.persons or [] if ner else []
        locations = ner.locations or [] if ner else []
        organisations = ner.organisations or [] if ner else []
        misc = ner.misc or [] if ner else []

        return {
            "file_id": str(file_id),
            "file_name": file.name,
            "persons": persons,
            "locations": locations,
            "organisations": organisations,
            "misc": misc,
            "total_entities": len(persons) + len(locations) + len(organisations) + len(misc),
        }
```

### `backend/app/get_ner_for_file/repository.py`

```python
import uuid

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import File, Ner, ArchiveAnalysis


class NerForFileRepository:
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

    async def get_ner_for_file(self, file_id: uuid.UUID) -> Ner | None:
        """Get the most recent NER result for a file."""
        result = await self._session.execute(
            select(Ner)
            .join(ArchiveAnalysis, ArchiveAnalysis.id == Ner.analysis_id)
            .where(Ner.file_id == file_id)
            .order_by(ArchiveAnalysis.date.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
```

## Ner model

Verify that the `Ner` SQLAlchemy model exists in `backend/app/shared/models.py`. It should look like:

```python
class Ner(Base):
    __tablename__ = "ner"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    persons: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    persons_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    locations: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    locations_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    organisations: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    organisations_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    misc: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    misc_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

If it doesn't exist yet, create it following the pattern of other models.

## Register the router

**File:** `backend/app/main.py`

Add the new router:

```python
from app.get_ner_for_file.router import router as get_ner_for_file_router

app.include_router(get_ner_for_file_router)
```

## No changes needed

- **NER table / migrations** — table already exists (migration 0005)
- **Frontend** — not consuming this endpoint yet (that's Phase 3)
- **Other endpoints** — no modifications
