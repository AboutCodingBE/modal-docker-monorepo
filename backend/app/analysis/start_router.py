import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.create_summaries_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_summaries_for_archive.create_summaries_for_archive import CreateSummariesForArchive
from app.create_ner_for_archive.create_ner_for_archive import CreateNerForArchive
from app.create_topic_detection_for_archive.create_topic_detection_for_archive import CreateTopicDetectionForArchive
from app.shared.database import _session_factory, get_db
from app.shared.models import AnalysisConfiguration

_logger = logging.getLogger("app")

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_SUPPORTED_TYPES = {"summary", "ner", "topic_detection"}


class AnalysisItem(BaseModel):
    type: str
    model: str


class StartAnalysisRequest(BaseModel):
    archiveId: uuid.UUID
    analysis: list[AnalysisItem]


@router.get("/configuration")
async def get_configuration(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnalysisConfiguration))
    configs = result.scalars().all()
    return [{"type": c.type, "model": c.model} for c in configs]


@router.post("/start")
async def start_analysis(
    body: StartAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    archive_id = body.archiveId
    analysis_repo = ArchiveAnalysisRepository(db)

    blocking_types = await analysis_repo.get_blocking_types(archive_id)

    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str]] = []

    for item in body.analysis:
        normalized_type = item.type.upper()

        if normalized_type in blocking_types:
            _logger.warning(
                f"Skipped analysis type '{item.type}' for archive {archive_id}: "
                f"already completed or currently running."
            )
            continue

        archive_analysis = await analysis_repo.create(archive_id, item.type, item.model)
        task = await task_tracker.create_task(db, archive_id, total_files=0)
        await db.flush()
        jobs.append((archive_id, archive_analysis.id, task.id, item.type, item.model))

        # Prevent duplicate types within the same request from both being started
        blocking_types.add(normalized_type)

    # Commit all records before handing off to background
    await db.commit()

    task_ids = [str(job[2]) for job in jobs]

    if jobs:
        # Run analyses sequentially in a single background task
        asyncio.create_task(_run_sequential(jobs))

    return {"task_ids": task_ids}


async def _run_sequential(
    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str]],
) -> None:
    for archive_id, archive_analysis_id, task_id, analysis_type, model in jobs:
        try:
            if analysis_type.lower() == "ner":
                runner = CreateNerForArchive(_session_factory)
            elif analysis_type.lower() == "topic_detection":
                runner = CreateTopicDetectionForArchive(_session_factory)
            else:
                runner = CreateSummariesForArchive(_session_factory)
            await runner.execute(archive_id, archive_analysis_id, task_id, model)
        except Exception as e:
            _logger.error(f"Background analysis ({analysis_type}) failed for task {task_id}: {e}")
            try:
                async with _session_factory() as session:
                    await task_tracker.fail_task(session, task_id)
                    await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
                    await session.commit()
            except Exception:
                pass
