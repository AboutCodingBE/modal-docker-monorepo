import asyncio
import json
import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.add_ollama_model import download_progress
from app.add_ollama_model.ollama_pull_client import OllamaPullError, pull_model
from app.config import settings
from app.shared.database import _session_factory, get_db
from app.shared.embedding_settings_repository import EmbeddingSettingsRepository

router = APIRouter(prefix="/api/settings/embedding", tags=["embedding-settings"])


class EmbeddingSettingsResponse(BaseModel):
    embedding_chunk_size: int
    embedding_max_chunks_per_file: int | None
    search_max_distance: float
    search_top_n: int
    embedding_model_downloaded: bool


class UpdateEmbeddingSettingsRequest(BaseModel):
    embedding_chunk_size: int = Field(gt=0)
    embedding_max_chunks_per_file: int | None = Field(default=None, gt=0)
    search_max_distance: float = Field(gt=0.0, le=1.0)
    search_top_n: int = Field(gt=0)


@router.get("", response_model=EmbeddingSettingsResponse)
async def get_embedding_settings(db: AsyncSession = Depends(get_db)):
    return await EmbeddingSettingsRepository(db).get()


@router.put("", response_model=EmbeddingSettingsResponse)
async def update_embedding_settings(
    body: UpdateEmbeddingSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await EmbeddingSettingsRepository(db).update(
        body.embedding_chunk_size,
        body.embedding_max_chunks_per_file,
        body.search_max_distance,
        body.search_top_n,
    )
    await db.commit()
    return result


@router.post("/download-model")
async def download_embedding_model():
    """Pulls the embedding model from Ollama and sets embedding_model_downloaded = true on success."""
    download_id = uuid.uuid4()
    asyncio.create_task(_run_download(download_id))
    return {"download_id": str(download_id)}


@router.get("/download-model/{download_id}/progress")
async def embedding_model_download_progress(download_id: uuid.UUID):
    async def _stream():
        while True:
            progress = download_progress.get(download_id)
            if progress is None:
                yield f"data: {json.dumps({'error': 'download not found'})}\n\n"
                return

            payload = {
                "status": progress.status,
                "completed_bytes": progress.completed_bytes,
                "total_bytes": progress.total_bytes,
                "done": progress.done,
                "error": progress.error,
            }
            yield f"data: {json.dumps(payload)}\n\n"

            if progress.done:
                download_progress.cleanup(download_id)
                return

            await asyncio.sleep(1.0)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _run_download(download_id: uuid.UUID) -> None:
    download_progress.create(download_id)

    def _on_progress(event: dict) -> None:
        download_progress.update(
            download_id,
            status=event.get("status", ""),
            completed_bytes=event.get("completed"),
            total_bytes=event.get("total"),
        )

    try:
        await pull_model(settings.embedding_model, _on_progress)

        async with _session_factory() as session:
            await EmbeddingSettingsRepository(session).set_model_downloaded()
            await session.commit()

        download_progress.update(download_id, done=True, status="success")

    except OllamaPullError as e:
        download_progress.update(download_id, done=True, error=str(e))
    except Exception as e:
        download_progress.update(download_id, done=True, error="Unexpected error, check logs")
