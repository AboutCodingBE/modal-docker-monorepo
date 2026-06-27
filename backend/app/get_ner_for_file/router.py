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
