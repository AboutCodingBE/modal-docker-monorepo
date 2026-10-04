import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.config import settings
from app.create_embeddings_for_archive.create_embeddings_for_archive import CreateEmbeddingsForArchive
from app.create_embeddings_for_archive.embedding_repository import EmbeddingRepository
from app.search_archive.search_archive import SearchArchive
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
from app.shared.database import _session_factory, get_db
from app.shared.models import Archive

router = APIRouter(prefix="/api/archives", tags=["search"])


@router.post("/{archive_id}/embeddings/reindex")
async def reindex_embeddings(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Archive.id).where(Archive.id == archive_id))
    if result.scalar_one_or_none() is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    analysis_repo = ArchiveAnalysisRepository(db)
    blocking = await analysis_repo.get_blocking_types(archive_id)
    if "EMBEDDING" in blocking:
        raise HTTPException(status_code=409, detail="Embedding analysis already running")

    await EmbeddingRepository(db).delete_for_archive(archive_id)
    await analysis_repo.delete_existing(archive_id, "EMBEDDING")

    archive_analysis = await analysis_repo.create(archive_id, "EMBEDDING", settings.embedding_model)
    task = await task_tracker.create_task(db, archive_id, total_files=0)
    await db.flush()
    task_id = task.id
    archive_analysis_id = archive_analysis.id
    await db.commit()

    asyncio.create_task(
        CreateEmbeddingsForArchive(_session_factory).execute(archive_id, archive_analysis_id, task_id)
    )

    return {"task_id": str(task_id)}


@router.get("/{archive_id}/search")
async def search_archive(
    archive_id: uuid.UUID,
    q: str = Query(..., min_length=1),
    top_n: int | None = Query(default=None, ge=1),
    db: AsyncSession = Depends(get_db),
):
    result = await SearchArchive(db).execute(archive_id, q, top_n)
    if result is None:
        raise HTTPException(status_code=404, detail="Archive not found")
    return result
