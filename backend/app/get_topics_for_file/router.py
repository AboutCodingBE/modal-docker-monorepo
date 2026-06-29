import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
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
