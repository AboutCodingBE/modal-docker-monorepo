import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.search_files_for_archive.repository import SearchFilesRepository
from app.shared.database import get_db

router = APIRouter(prefix="/api/archives", tags=["literal-search"])


@router.get("/{archive_id}/files/search")
async def search_files_for_archive(
    archive_id: uuid.UUID,
    q: str = Query(..., description="Search term (exact phrase, case-insensitive)"),
    folder_path: str | None = Query(default=None, description="Scope search to this folder subtree"),
    cursor_id: uuid.UUID | None = Query(default=None, description="Cursor: id of the last seen file"),
    cursor_value: str | None = Query(default=None, description="Cursor: relative_path of the last seen file"),
    db: AsyncSession = Depends(get_db),
):
    if not q.strip():
        raise HTTPException(status_code=400, detail="Search term must not be empty")

    repo = SearchFilesRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    return await repo.search(
        archive_id=archive_id,
        term=q.strip(),
        folder_path=folder_path,
        cursor_id=cursor_id,
        cursor_value=cursor_value,
    )
