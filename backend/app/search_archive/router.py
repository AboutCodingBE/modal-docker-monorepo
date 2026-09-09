import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.shared.database import get_db
from app.search_archive.search_archive import SearchArchive

router = APIRouter(prefix="/api/archives", tags=["search"])


@router.get("/{archive_id}/search")
async def search_archive(
    archive_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    top_n: int = Query(default=settings.search_top_n, ge=1),
    db: AsyncSession = Depends(get_db),
):
    result = await SearchArchive(db).execute(archive_id, q, top_n)
    if result is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return result
