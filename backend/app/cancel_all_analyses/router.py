from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.cancel_all_analyses.cancel_all_analyses import CancelAllAnalyses

router = APIRouter(prefix="/api", tags=["analysis"])


@router.post("/cancel-all-analyses")
async def cancel_all_analyses(db: AsyncSession = Depends(get_db)):
    return await CancelAllAnalyses(db).execute()
