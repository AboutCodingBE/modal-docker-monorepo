import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.get_ner_for_folder.get_ner_for_folder import GetNerForFolder

router = APIRouter(prefix="/api", tags=["ner"])


@router.get("/archives/{archive_id}/folders/{folder_id}/ner")
async def get_ner_for_folder(
    archive_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await GetNerForFolder(db).execute(archive_id, folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result
