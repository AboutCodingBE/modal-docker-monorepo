import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
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
