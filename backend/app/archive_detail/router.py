import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.archive_detail.repository import ArchiveDetailRepository

router = APIRouter(prefix="/api/archives", tags=["archive-detail"])


@router.get("/{archive_id}/stats")
async def archive_stats(archive_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    repo = ArchiveDetailRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return await repo.get_stats(archive_id)


@router.get("/{archive_id}/analysis/{file_id}")
async def archive_file_analysis(
    archive_id: uuid.UUID,
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = ArchiveDetailRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    result = await repo.get_file_analysis(archive_id, file_id)
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
    return result


@router.get("/{archive_id}/folder/root/files")
async def archive_root_files(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = ArchiveDetailRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return await repo.get_root_files(archive_id)


@router.get("/{archive_id}/folder/{folder_id}/files")
async def archive_folder_files(
    archive_id: uuid.UUID,
    folder_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    repo = ArchiveDetailRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    result = await repo.get_folder_files(archive_id, folder_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Folder not found")
    return result


@router.get("/{archive_id}/folder")
async def archive_folder(
    archive_id: uuid.UUID,
    path: str = Query(default="/"),
    db: AsyncSession = Depends(get_db),
):
    repo = ArchiveDetailRepository(db)
    if await repo.get_archive(archive_id) is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return await repo.get_folder(archive_id, path)
