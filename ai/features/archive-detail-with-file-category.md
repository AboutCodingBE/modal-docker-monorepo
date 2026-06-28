# Use Case

Update the folder contents endpoint to return file categories alongside the existing mime types. The `generic_types` table already contains the category for each file (populated during ingestion). This phase adds a `categories` field to the folder contents response, grouped and counted the same way mime types are.

The input of this use case:
Same as current — `GET /api/archives/{archive_id}/folder?path=/some/path`

Input mechanism of this use case:
Existing REST endpoint, no changes to the URL or parameters.

The output of this feature:
The response includes a new `categories` field alongside the existing `mime_types`. The `mime_types` field is preserved for backwards compatibility.

Current response:
```json
{
  "path": "/",
  "folder_id": "...",
  "direct_file_count": 3,
  "subfolders": [...],
  "mime_types": [
    { "mime_type": "application/pdf", "count": 2 },
    { "mime_type": "image/jpeg", "count": 1 }
  ]
}
```

New response:
```json
{
  "path": "/",
  "folder_id": "...",
  "direct_file_count": 3,
  "subfolders": [...],
  "mime_types": [
    { "mime_type": "application/pdf", "count": 2 },
    { "mime_type": "image/jpeg", "count": 1 }
  ],
  "categories": [
    { "category": "tekstbestand", "count": 2 },
    { "category": "beeldbestand", "count": 1 }
  ]
}
```

# Business Rules

- The `categories` field contains the distinct `generic_type` values for direct files in the current folder, with a count per category.
- Categories come from the `generic_types` table, joined on `file_id`.
- Files without a `generic_types` entry should be excluded from the categories list (they haven't been classified yet).
- Categories are sorted by count descending (most common first), same as mime_types.
- The `mime_types` field remains unchanged for backwards compatibility.
- The possible category values are: tekstbestand, geluidsbestand, beeldbestand, rekenbestand, presentatiebestand, compressiebestand, gegevensbestand, berichtbestand, lettertypebestand, videobestand, andere, onbekend.

# Component Overview

## Update ArchiveDetailRepository.get_folder

**File:** `backend/app/get_folder_contents/archive_detail_repository.py` (or wherever `get_folder` lives)

After the existing `mime_types` query, add a similar query for categories:

```python
# Categories for direct files
categories = []
if file_ids:
    cat_result = await self._session.execute(
        select(GenericType.generic_type, func.count().label("count"))
        .where(
            and_(
                GenericType.file_id.in_(file_ids),
                GenericType.generic_type.isnot(None),
            )
        )
        .group_by(GenericType.generic_type)
        .order_by(func.count().desc())
    )
    categories = [
        {"category": r.generic_type, "count": r.count}
        for r in cat_result.all()
    ]
```

Then add `categories` to the return dict:

```python
return {
    "path": display_path,
    "folder_id": str(folder.id) if folder else None,
    "direct_file_count": len(direct_files),
    "subfolders": subfolder_list,
    "mime_types": mime_types,
    "categories": categories,  # NEW
}
```

This component depends on:
- `GenericType` model (must be imported)
- `file_ids` list (already computed in the existing code for the mime_types query)

## GenericType model

Verify that the `GenericType` SQLAlchemy model exists in `backend/app/shared/models.py`. It should look like:

```python
class GenericType(Base):
    __tablename__ = "generic_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    file_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("files.id", ondelete="CASCADE"), nullable=False, unique=True)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    generic_type: Mapped[str | None] = mapped_column(String(255), nullable=True)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
```

If it doesn't exist yet, let me know, give a warning! 

## No changes needed

- **Router/endpoint** — no changes to the URL, parameters, or HTTP method
- **Frontend** — not consuming the new field yet (that's Phase 3)
- **Migration** — table already exists (migration 0008)
- **FileClassifier** — already runs during ingestion, categories are already in the database
- **mime_types** — kept as-is for backwards compatibility