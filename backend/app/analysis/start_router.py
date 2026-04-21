import asyncio
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.create_summaries_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_summaries_for_archive.create_summaries_for_archive import CreateSummariesForArchive
from app.shared.database import _session_factory, get_db

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_SUPPORTED_TYPES = {"summary"}


class AnalysisItem(BaseModel):
    type: str
    model: str


class StartAnalysisRequest(BaseModel):
    archiveId: uuid.UUID
    analysis: list[AnalysisItem]


@router.post("/start")
async def start_analysis(
    body: StartAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    archive_id = body.archiveId
    analysis_repo = ArchiveAnalysisRepository(db)

    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]] = []

    for item in body.analysis:
        archive_analysis = await analysis_repo.create(archive_id, item.type, item.model)
        task = await task_tracker.create_task(db, archive_id, total_files=0)
        await db.flush()
        jobs.append((archive_id, archive_analysis.id, task.id, item.model))

    # Commit all records before handing off to background
    await db.commit()

    task_ids = [str(job[2]) for job in jobs]

    # Run analyses sequentially in a single background task
    asyncio.create_task(_run_sequential(jobs))

    return {"task_ids": task_ids}


async def _run_sequential(
    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str]],
) -> None:
    for archive_id, archive_analysis_id, task_id, model in jobs:
        async with _session_factory() as session:
            try:
                runner = CreateSummariesForArchive(session)
                await runner.execute(archive_id, archive_analysis_id, task_id, model)
            except Exception as e:
                print(f"Background summarization failed for task {task_id}: {e}")
                try:
                    await task_tracker.fail_task(session, task_id)
                    repo = ArchiveAnalysisRepository(session)
                    await repo.update_status(archive_analysis_id, "FAILED")
                    await session.commit()
                except Exception:
                    pass
