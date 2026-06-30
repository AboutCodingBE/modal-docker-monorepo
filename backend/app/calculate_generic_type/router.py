import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.calculate_generic_type.calculate_generic_type import CalculateGenericType
from app.shared.database import _session_factory, get_db

_logger = logging.getLogger("app")

router = APIRouter(prefix="/api/generic-type", tags=["generic-type"])


class StartGenericTypeRequest(BaseModel):
    archiveId: uuid.UUID


@router.post("/start")
async def start_generic_type(
    body: StartGenericTypeRequest,
    db: AsyncSession = Depends(get_db),
):
    archive_id = body.archiveId

    task = await task_tracker.create_task(db, archive_id, total_files=0, task_type="generic_type")
    await db.commit()

    task_id = task.id
    asyncio.create_task(_run_generic_type(archive_id, task_id))

    return {"task_id": str(task_id)}


async def _run_generic_type(archive_id: uuid.UUID, task_id: uuid.UUID) -> None:
    try:
        await CalculateGenericType(_session_factory).execute(archive_id, task_id)
    except Exception as e:
        _logger.error(f"Background generic type calculation failed for task {task_id}: {e}")
        try:
            async with _session_factory() as session:
                await task_tracker.fail_task(session, task_id)
                await session.commit()
        except Exception:
            pass
