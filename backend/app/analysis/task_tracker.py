import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import AnalysisTask


async def create_task(
    session: AsyncSession,
    archive_id: uuid.UUID,
    task_type: str,
    total_files: int,
) -> AnalysisTask:
    task = AnalysisTask(
        archive_id=archive_id,
        task_type=task_type,
        status="pending",
        total_files=total_files,
    )
    session.add(task)
    await session.flush()
    await session.refresh(task)
    return task


async def start_task(session: AsyncSession, task_id: uuid.UUID) -> None:
    task = await _get(session, task_id)
    if task:
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)
        await session.flush()


async def update_progress(
    session: AsyncSession,
    task_id: uuid.UUID,
    processed: int,
    failed_count: int,
    current_file: str | None = None,
) -> None:
    task = await _get(session, task_id)
    if task:
        task.processed = processed
        task.failed_count = failed_count
        task.current_file = current_file
        await session.flush()


async def complete_task(session: AsyncSession, task_id: uuid.UUID) -> None:
    task = await _get(session, task_id)
    if task:
        task.status = "completed"
        task.completed_at = datetime.now(timezone.utc)
        await session.flush()


async def fail_task(session: AsyncSession, task_id: uuid.UUID) -> None:
    task = await _get(session, task_id)
    if task:
        task.status = "failed"
        task.completed_at = datetime.now(timezone.utc)
        await session.flush()


async def get_task(session: AsyncSession, task_id: uuid.UUID) -> AnalysisTask | None:
    return await _get(session, task_id)


async def get_tasks_for_archive(
    session: AsyncSession, archive_id: uuid.UUID
) -> list[AnalysisTask]:
    result = await session.execute(
        select(AnalysisTask)
        .where(AnalysisTask.archive_id == archive_id)
        .order_by(AnalysisTask.started_at.desc().nullslast())
    )
    return list(result.scalars().all())


async def _get(session: AsyncSession, task_id: uuid.UUID) -> AnalysisTask | None:
    result = await session.execute(
        select(AnalysisTask).where(AnalysisTask.id == task_id)
    )
    return result.scalar_one_or_none()
