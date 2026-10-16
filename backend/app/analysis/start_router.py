import asyncio
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_summaries_for_archive.create_summaries_for_archive import CreateSummariesForArchive
from app.create_ner_for_archive.create_ner_for_archive import CreateNerForArchive
from app.create_topic_detection_for_archive.create_topic_detection_for_archive import CreateTopicDetectionForArchive
from app.create_embeddings_for_archive.create_embeddings_for_archive import CreateEmbeddingsForArchive
from app.shared.database import _session_factory, get_db
from app.shared.file_repository import FileRepository, CATEGORY_NONE_SENTINEL
from app.shared.processing_settings_repository import ProcessingSettingsRepository

_logger = logging.getLogger("app")

router = APIRouter(prefix="/api/analysis", tags=["analysis"])

_SUPPORTED_TYPES = {"summary", "ner", "topic_detection", "embedding"}
_KNOWN_CATEGORIES = {"tekstbestand", "beeldbestand", "gegevensbestand", "andere", CATEGORY_NONE_SENTINEL}


class AnalysisItem(BaseModel):
    type: str
    model: str
    categories: list[str] | None = None


class StartAnalysisRequest(BaseModel):
    archiveId: uuid.UUID
    analysis: list[AnalysisItem]


@router.post("/start")
async def start_analysis(
    body: StartAnalysisRequest,
    db: AsyncSession = Depends(get_db),
):
    archive_id = body.archiveId

    # Validate categories for each analysis item
    for item in body.analysis:
        if item.categories is not None:
            if len(item.categories) == 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"categories cannot be empty for analysis type '{item.type}'",
                )
            unknown = set(item.categories) - _KNOWN_CATEGORIES
            if unknown:
                raise HTTPException(
                    status_code=422,
                    detail=f"unknown category values for '{item.type}': {', '.join(sorted(unknown))}",
                )

    # Pre-check: refuse a run that would process zero files
    processing_settings = await ProcessingSettingsRepository(db).get()
    file_repo = FileRepository(db)
    for item in body.analysis:
        if item.type.lower() in {"summary", "ner", "topic_detection"} and item.categories is not None:
            count = await file_repo.count_files_with_tika_content(
                archive_id,
                item.categories,
                processing_settings.minimum_text_length,
            )
            if count == 0:
                raise HTTPException(
                    status_code=422,
                    detail=f"no_analyzable_files_for_{item.type}",
                )

    analysis_repo = ArchiveAnalysisRepository(db)
    blocking_types = await analysis_repo.get_blocking_types(archive_id)

    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str, list[str] | None]] = []

    for item in body.analysis:
        normalized_type = item.type.upper()

        if normalized_type in blocking_types:
            _logger.warning(
                f"Skipped analysis type '{item.type}' for archive {archive_id}: "
                f"already completed or currently running."
            )
            continue

        await analysis_repo.delete_existing(archive_id, normalized_type)

        archive_analysis = await analysis_repo.create(archive_id, item.type, item.model)
        task = await task_tracker.create_task(db, archive_id, total_files=0)
        await db.flush()
        jobs.append((archive_id, archive_analysis.id, task.id, item.type, item.model, item.categories))

        blocking_types.add(normalized_type)

    await db.commit()

    task_ids = [str(job[2]) for job in jobs]

    if jobs:
        asyncio.create_task(_run_sequential(jobs))

    return {"task_ids": task_ids}


async def _run_sequential(
    jobs: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID, str, str, list[str] | None]],
) -> None:
    for archive_id, archive_analysis_id, task_id, analysis_type, model, categories in jobs:
        try:
            if analysis_type.lower() == "ner":
                runner = CreateNerForArchive(_session_factory)
                await runner.execute(archive_id, archive_analysis_id, task_id, model, categories)
            elif analysis_type.lower() == "topic_detection":
                runner = CreateTopicDetectionForArchive(_session_factory)
                await runner.execute(archive_id, archive_analysis_id, task_id, model, categories)
            elif analysis_type.lower() == "embedding":
                await CreateEmbeddingsForArchive(_session_factory).execute(archive_id, archive_analysis_id, task_id)
            else:
                runner = CreateSummariesForArchive(_session_factory)
                await runner.execute(archive_id, archive_analysis_id, task_id, model, categories)
        except Exception as e:
            _logger.error(f"Background analysis ({analysis_type}) failed for task {task_id}: {e}")
            try:
                async with _session_factory() as session:
                    await task_tracker.fail_task(session, task_id)
                    await ArchiveAnalysisRepository(session).update_status(archive_analysis_id, "FAILED")
                    await session.commit()
            except Exception:
                pass
