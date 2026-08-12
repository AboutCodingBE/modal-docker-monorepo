# Use Case

Update the `get_ner_for_file` and `get_topics_for_file` features to work with the new JSONB column format. The NER and topic detection tables have been refactored: instead of PostgreSQL arrays of text, they now store JSONB arrays of objects with entity/topic names and counts. The response format to the frontend stays unchanged — flat arrays of strings.

# What Changed in the Database

## NER table (`ner`)
**Before (migration 0005):** Four `ARRAY(Text)` columns + four `Integer` count columns
```
persons: {Lieve De Winter, Hugo Schiltz}
persons_count: 2
```

**After (migration 0010):** Four `JSONB` columns, count columns removed
```json
persons: [{"entity": "Lieve De Winter", "count": 1}, {"entity": "Hugo Schiltz", "count": 1}]
```

The key in each object is `"entity"`. The `"count"` is always 1 for files, can be >1 for folder aggregation.

## Topic detection table (`topic_detection`)
**Before (migration 0009):** One `ARRAY(Text)` column + one `Integer` count column
```
topics: {Onderwijs, Werkgelegenheid}
topics_count: 2
```

**After (migration 0011):** One `JSONB` column, count column removed
```json
topics: [{"topic": "Buittegenwegonderwijs", "count": 1}, {"topic": "Werkgelegenheid", "count": 1}]
```

The key in each object is `"topic"`. The `"count"` is always 1 for files, can be >1 for folder aggregation.

# Change 1: Update get_ner_for_file

## Model update

**File:** `backend/app/shared/models.py`

Update the `Ner` model — change the four category columns from `ARRAY(Text)` to `JSONB` and remove the count columns:

```python
from sqlalchemy.dialects.postgresql import JSONB

class Ner(Base):
    __tablename__ = "ner"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    persons: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    locations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    organisations: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
    misc: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
```

Remove: `persons_count`, `locations_count`, `organisations_count`, `misc_count` columns.

## Use case update

**File:** `backend/app/get_ner_for_file/get_ner_for_file.py`

The extraction logic changes. Previously the columns were Python lists of strings. Now they are lists of dicts. Extract the `"entity"` key from each object:

```python
def _extract_entities(jsonb_list: list | None) -> list[str]:
    """Extract entity names from JSONB array of {entity, count} objects."""
    if not jsonb_list:
        return []
    return [item["entity"] for item in jsonb_list if "entity" in item]
```

Update the execute method:

```python
async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
    file = await self._repo.get_file(archive_id, file_id)
    if file is None:
        return None

    ner = await self._repo.get_ner_for_file(file_id)

    persons = _extract_entities(ner.persons) if ner else []
    locations = _extract_entities(ner.locations) if ner else []
    organisations = _extract_entities(ner.organisations) if ner else []
    misc = _extract_entities(ner.misc) if ner else []

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

## Repository — no changes needed

**File:** `backend/app/get_ner_for_file/repository.py`

The repository queries the `Ner` model and returns it. The JSONB deserialization happens automatically by SQLAlchemy — JSONB columns are returned as Python dicts/lists. No query changes needed.

## Response format — unchanged

The frontend still receives:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "persons": ["Lieve De Winter", "Hugo Schiltz"],
  "locations": ["Antwerpen", "Brussel"],
  "organisations": ["Volksunie"],
  "misc": ["12 maart 1978"],
  "total_entities": 6
}
```

No frontend changes needed.

---

# Change 2: Update get_topics_for_file

## Model update

**File:** `backend/app/shared/models.py`

Update the `TopicDetection` model — change `topics` from `ARRAY(Text)` to `JSONB` and remove `topics_count`:

```python
class TopicDetection(Base):
    __tablename__ = "topic_detection"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    analysis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archive_analysis.id", ondelete="CASCADE"), nullable=False)
    parent_folder_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False)
    topics: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=sa.text("'[]'::jsonb"))
```

Remove: `topics_count` column.

## Use case update

**File:** `backend/app/get_topics_for_file/get_topics_for_file.py`

Same pattern as NER — extract the `"topic"` key from each object:

```python
def _extract_topics(jsonb_list: list | None) -> list[str]:
    """Extract topic names from JSONB array of {topic, count} objects."""
    if not jsonb_list:
        return []
    return [item["topic"] for item in jsonb_list if "topic" in item]
```

Update the execute method:

```python
async def execute(self, archive_id: uuid.UUID, file_id: uuid.UUID) -> dict | None:
    file = await self._repo.get_file(archive_id, file_id)
    if file is None:
        return None

    topic_detection = await self._repo.get_topics_for_file(file_id)

    topics = _extract_topics(topic_detection.topics) if topic_detection else []

    return {
        "file_id": str(file_id),
        "file_name": file.name,
        "topics": topics,
        "total_topics": len(topics),
    }
```

## Repository — no changes needed

**File:** `backend/app/get_topics_for_file/repository.py`

Same as NER — JSONB deserialization is automatic. No query changes.

## Response format — unchanged

The frontend still receives:
```json
{
  "file_id": "...",
  "file_name": "MICHAEL",
  "topics": ["Verkiezingsstrategie", "Kandidatenlijst", "Partijorganisatie"],
  "total_topics": 3
}
```

No frontend changes needed.

---

# Testing Notes

## NER
- Verify `GET /api/archives/{id}/files/{file_id}/ner` returns flat string arrays (not JSONB objects)
- Verify a file with `persons: [{"entity": "Test", "count": 1}]` returns `"persons": ["Test"]`
- Verify empty JSONB arrays `[]` return empty arrays `[]`
- Verify `total_entities` is the sum of all four array lengths
- Verify the NER tab in the frontend still displays correctly with no frontend changes

## Topics
- Verify `GET /api/archives/{id}/files/{file_id}/topics` returns a flat string array (not JSONB objects)
- Verify a file with `topics: [{"topic": "Test", "count": 1}]` returns `"topics": ["Test"]`
- Verify empty JSONB arrays `[]` return empty arrays `[]`
- Verify `total_topics` matches the array length
- Verify the Topics tab in the frontend still displays correctly with no frontend changes