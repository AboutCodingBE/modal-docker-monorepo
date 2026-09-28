import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import AgentExportError
from app.export_archive.export_archive import ExportArchive
from app.shared.database import get_db

router = APIRouter(prefix="/api/archives", tags=["export"])


class ExportArchiveRequest(BaseModel):
    format: Literal["csv", "json"]


@router.post("/{archive_id}/export")
async def export_archive(
    archive_id: uuid.UUID,
    body: ExportArchiveRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        path = await ExportArchive(db).execute(archive_id, body.format)
    except AgentExportError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"path": path}
