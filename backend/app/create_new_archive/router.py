import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.create_new_archive.create_archive import CreateArchive
from app.shared.models import Archive

router = APIRouter()


class CreateArchiveRequest(BaseModel):
    name: str
    path: str


def _to_response(archive: Archive, task_id: uuid.UUID) -> dict:
    status_map = {
        "pending": "ingested",
        "in_progress": "in_progress",
        "completed": "analysed",
        "failed": "failed",
    }
    return {
        "id": str(archive.id),
        "name": archive.name,
        "date": archive.created_at.date().isoformat() if archive.created_at else "",
        "files": archive.file_count,
        "status": status_map.get(archive.analysis_status, "ingested"),
        "tika_task_id": str(task_id),
        "progress": 0,
    }


@router.post("/api/archives", status_code=201)
async def create_archive(body: CreateArchiveRequest, db: AsyncSession = Depends(get_db)):
    result = await CreateArchive(db).execute(body.name, body.path)
    if isinstance(result, str):
        raise HTTPException(status_code=400, detail=result)
    archive, task_id = result
    return _to_response(archive, task_id)
