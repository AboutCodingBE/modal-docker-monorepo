from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.processing_settings_repository import ProcessingSettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ProcessingSettingsResponse(BaseModel):
    summary_char_limit: int
    topic_char_limit: int
    ner_llm_char_limit: int


class UpdateProcessingSettingsRequest(BaseModel):
    summary_char_limit: int = Field(gt=0)
    topic_char_limit: int = Field(gt=0)
    ner_llm_char_limit: int = Field(gt=0)


@router.get("/processing", response_model=ProcessingSettingsResponse)
async def get_processing_settings(db: AsyncSession = Depends(get_db)):
    return await ProcessingSettingsRepository(db).get()


@router.put("/processing", response_model=ProcessingSettingsResponse)
async def update_processing_settings(
    body: UpdateProcessingSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await ProcessingSettingsRepository(db).update(
        body.summary_char_limit, body.topic_char_limit, body.ner_llm_char_limit
    )
    await db.commit()
    return result
