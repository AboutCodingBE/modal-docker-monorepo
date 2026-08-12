import asyncio
import json
import uuid

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.add_ollama_model import download_progress
from app.add_ollama_model.add_ollama_model import AddOllamaModel
from app.shared.database import _session_factory

router = APIRouter(prefix="/api/models", tags=["models"])


class AddOllamaModelRequest(BaseModel):
    model: str


@router.post("/ollama")
async def add_ollama_model(body: AddOllamaModelRequest):
    download_id = uuid.uuid4()
    asyncio.create_task(AddOllamaModel(_session_factory).execute(download_id, body.model))
    return {"download_id": str(download_id)}


@router.get("/ollama/{download_id}/progress")
async def ollama_download_progress(download_id: uuid.UUID):
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
