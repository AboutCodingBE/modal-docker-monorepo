import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_files_for_archive.repository import ListFilesRepository

router = APIRouter(prefix="/api/archives", tags=["list-files"])


@router.get("/{archive_id}/files")
async def list_files_for_archive(
    archive_id: uuid.UUID,
    folder_path: str | None = Query(default=None, description="Relative path of folder to scope the listing; omit for whole archive"),
    sort_by: str = Query(default="content_created_at", description="Sort field: content_created_at | relative_path | category"),
    sort_dir: str = Query(default="desc", description="Sort direction: asc | desc"),
    mime_type: str | None = Query(default=None, description="Filter by MIME type"),
    category: str | None = Query(default=None, description="Filter by generic category/klasse"),
    entities: list[str] = Query(default=[], description="Exact entity_text values to filter by (OR within facet); repeat param for multiple"),
    topics: list[str] = Query(default=[], description="Exact topic_label values to filter by (OR within facet); repeat param for multiple"),
    cursor_id: uuid.UUID | None = Query(default=None, description="Cursor: id of the last seen file"),
    cursor_value: str | None = Query(default=None, description="Cursor: sort-field value of the last seen file (ISO date, path, or category); omit if null"),
    db: AsyncSession = Depends(get_db),
):
    repo = ListFilesRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return await repo.list_files(
        archive_id=archive_id,
        folder_path=folder_path,
        sort_by=sort_by,
        sort_dir=sort_dir,
        mime_type_filter=mime_type,
        category_filter=category,
        entities=entities or None,
        topics=topics or None,
        cursor_id=cursor_id,
        cursor_value=cursor_value,
    )
