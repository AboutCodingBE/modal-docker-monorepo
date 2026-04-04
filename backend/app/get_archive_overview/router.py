from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.get_archive_overview.get_archives import GetArchives

router = APIRouter()


@router.get("/api/archives")
async def get_archives(db: AsyncSession = Depends(get_db)):
    return await GetArchives(db).execute()
