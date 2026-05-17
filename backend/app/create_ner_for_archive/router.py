import asyncio
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.create_ner_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
from app.create_ner_for_archive.create_ner_for_archive import CreateNerForArchive
from app.shared.database import _session_factory, get_db

router = APIRouter(prefix="/api/ner", tags=["ner"])

_NER_MODEL = "nl_core_news_lg"


@router.post("/{archive_id}")
async def start_ner(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    analysis_repo = ArchiveAnalysisRepository(db)
    archive_analysis = await analysis_repo.create(archive_id, "NER", _NER_MODEL)
    task = await task_tracker.create_task(db, archive_id, total_files=0)
    await db.flush()

    archive_analysis_id = archive_analysis.id
    task_id = task.id

    await db.commit()

    asyncio.create_task(_run_ner_background(archive_id, archive_analysis_id, task_id))

    return {"task_id": str(task_id), "archive_analysis_id": str(archive_analysis_id)}


async def _run_ner_background(
    archive_id: uuid.UUID,
    archive_analysis_id: uuid.UUID,
    task_id: uuid.UUID,
) -> None:
    async with _session_factory() as session:
        try:
            runner = CreateNerForArchive(session)
            await runner.execute(archive_id, archive_analysis_id, task_id, _NER_MODEL)
        except Exception as e:
            print(f"Background NER failed for task {task_id}: {e}")
            try:
                await task_tracker.fail_task(session, task_id)
                repo = ArchiveAnalysisRepository(session)
                await repo.update_status(archive_analysis_id, "FAILED")
                await session.commit()
            except Exception:
                pass
