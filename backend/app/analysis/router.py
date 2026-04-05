import asyncio
import json
import uuid

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.analysis import task_tracker

router = APIRouter(prefix="/api/analysis/tasks", tags=["analysis"])

_TERMINAL_STATUSES = {"completed", "failed"}
_POLL_INTERVAL = 1.0  # seconds


def _task_to_event(task) -> str:
    percentage = 0
    if task.total_files and task.total_files > 0:
        percentage = round((task.processed / task.total_files) * 100)

    payload = {
        "task_id": str(task.id),
        "status": task.status,
        "total_files": task.total_files,
        "processed": task.processed,
        "failed_count": task.failed_count,
        "current_file": task.current_file,
        "percentage": percentage,
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _progress_stream(task_id: uuid.UUID, db: AsyncSession):
    try:
        while True:
            task = await task_tracker.get_task(db, task_id)
            if task is None:
                yield f"data: {json.dumps({'error': 'task not found'})}\n\n"
                return

            yield _task_to_event(task)

            if task.status in _TERMINAL_STATUSES:
                return

            await asyncio.sleep(_POLL_INTERVAL)
    except asyncio.CancelledError:
        pass


@router.get("/{task_id}/progress")
async def task_progress(task_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    task = await task_tracker.get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return StreamingResponse(
        _progress_stream(task_id, db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/archive/{archive_id}")
async def tasks_for_archive(archive_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    tasks = await task_tracker.get_tasks_for_archive(db, archive_id)

    def _shape(task):
        percentage = 0
        if task.total_files and task.total_files > 0:
            percentage = round((task.processed / task.total_files) * 100)
        return {
            "task_id": str(task.id),
            "status": task.status,
            "total_files": task.total_files,
            "processed": task.processed,
            "failed_count": task.failed_count,
            "percentage": percentage,
            "started_at": task.started_at.isoformat() if task.started_at else None,
            "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        }

    return [_shape(t) for t in tasks]
