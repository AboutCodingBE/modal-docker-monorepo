import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.delete_archive.delete_archive import DeleteArchive

router = APIRouter(prefix="/api", tags=["archives"])


@router.delete("/archives/{archive_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_archive(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    deleted = await DeleteArchive(db).execute(archive_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Archive not found")
