from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.export_settings_repository import ExportSettingsRepository
from app.shared.export_settings_service import get_or_initialize_export_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ExportSettingsResponse(BaseModel):
    default_export_path: str | None
    content_char_limit: int


class UpdateExportSettingsRequest(BaseModel):
    default_export_path: str | None = None
    content_char_limit: int = Field(gt=0)


@router.get("/export", response_model=ExportSettingsResponse)
async def get_export_settings(db: AsyncSession = Depends(get_db)):
    # Uses the shared service — triggers auto-computing the default the first
    # time the Settings page is opened, not just the first time an export runs.
    return await get_or_initialize_export_settings(db)


@router.put("/export", response_model=ExportSettingsResponse)
async def update_export_settings(
    body: UpdateExportSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await ExportSettingsRepository(db).update(body.default_export_path, body.content_char_limit)
    await db.commit()
    return result
