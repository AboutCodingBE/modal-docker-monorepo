from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_analysis_models.list_analysis_models import ListAnalysisModels

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/models")
async def list_analysis_models(db: AsyncSession = Depends(get_db)):
    return await ListAnalysisModels(db).execute()
