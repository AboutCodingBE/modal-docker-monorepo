import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.list_analysis_models.set_default_models import DuplicateTypeError, SetDefaultModels

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SetDefaultModelsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


@router.get("/models")
async def list_analysis_models(db: AsyncSession = Depends(get_db)):
    return await ListAnalysisModels(db).execute()


@router.put("/models/defaults")
async def set_default_models(body: SetDefaultModelsRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await SetDefaultModels(db).execute(body.ids)
    except DuplicateTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="One or more configuration entries not found")
    return result
