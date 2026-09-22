import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.get_file_content.get_file_content import GetFileContent

router = APIRouter(prefix="/api", tags=["files"])


@router.get("/files/{file_id}/content")
async def get_file_content(file_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await GetFileContent(db).execute(file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result
