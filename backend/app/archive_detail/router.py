import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.archive_detail.repository import ArchiveDetailRepository

router = APIRouter(prefix="/api/archives", tags=["archive-detail"])


@router.get("/{archive_id}/stats")
async def archive_stats(archive_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = ArchiveDetailRepository(db)

    archive = await repo.get_archive(archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    return await repo.get_stats(archive_id)


@router.get("/{archive_id}/folder")
async def archive_folder(
    archive_id: uuid.UUID,
    path: str = Query(default="/"),
    db: AsyncSession = Depends(get_db),
):
    repo = ArchiveDetailRepository(db)

    archive = await repo.get_archive(archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    folder = await repo.get_folder(archive_id, path)
    if folder is None:
        raise HTTPException(status_code=404, detail="Folder not found")

    return folder
