import asyncio
import logging
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.analysis import task_tracker
from app.config import settings
from app.perform_ocr.file_repository import OcrFileRepository
from app.perform_ocr.perform_ocr import PerformOcr
from app.shared.database import _session_factory, get_db

_logger = logging.getLogger("app.ocr")

router = APIRouter(prefix="/api/ocr", tags=["ocr"])

_SAMPLE_SIZE = 10


def _pick_sample(candidates: list[dict], n: int) -> list[dict]:
    """Pick n evenly-spaced items from candidates (spread across the full list)."""
    if len(candidates) <= n:
        return candidates
    step = len(candidates) / n
    return [candidates[int(i * step)] for i in range(n)]


@router.post("/{archive_id}/verify")
async def verify_ocr_source(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Open a native folder picker via the agent, check a sample of OCR candidate
    files against the database's expected sizes, and hold the verified root in
    the agent's memory for a short window (~20 s) so a /start call can follow.

    Returns the agent's verification response: {ok, matched, total,
    mismatches, root_path} or an error payload.
    """
    file_repo = OcrFileRepository(db)
    archive = await file_repo.get_archive(archive_id)
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    candidates = await file_repo.get_candidates(archive_id)
    if not candidates:
        raise HTTPException(status_code=422, detail="no_candidates")

    sample = _pick_sample(candidates, _SAMPLE_SIZE)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.agent_url}/ocr/verify",
                json={
                    "archive_id": str(archive_id),
                    "samples": [
                        {
                            "relative_path": f["relative_path"],
                            "size_bytes": f["size_bytes"],
                        }
                        for f in sample
                    ],
                    "root_hint": archive.root_path,
                },
                timeout=120.0,  # folder picker requires user interaction
            )
            if resp.status_code == 400:
                return resp.json()
            resp.raise_for_status()
            return resp.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="agent_timeout")
    except httpx.HTTPStatusError as e:
        _logger.error(f"Agent verify error for archive {archive_id}: {e}")
        raise HTTPException(status_code=502, detail="agent_error")
    except Exception as e:
        _logger.error(f"OCR verify failed for archive {archive_id}: {e}")
        raise HTTPException(status_code=502, detail="agent_unavailable")


@router.post("/{archive_id}/start")
async def start_ocr(
    archive_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """
    Start an OCR run for an archive. The agent must already hold a verified root
    (from a recent /verify call). Refuses if an OCR task is already running.
    """
    existing = await task_tracker.get_running_ocr_task(db, archive_id)
    if existing:
        raise HTTPException(status_code=409, detail="ocr_already_running")

    file_repo = OcrFileRepository(db)
    candidates = await file_repo.get_candidates(archive_id)
    if not candidates:
        raise HTTPException(status_code=422, detail="no_candidates")

    task = await task_tracker.create_task(
        db, archive_id, total_files=len(candidates), task_type="ocr"
    )
    await db.commit()

    # Extend the agent's verified-root TTL to cover the full run duration
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{settings.agent_url}/ocr/activate",
                json={"archive_id": str(archive_id)},
                timeout=5.0,
            )
    except Exception as e:
        _logger.warning(f"Could not activate OCR root on agent for {archive_id}: {e}")

    asyncio.create_task(PerformOcr(_session_factory).execute(archive_id, task.id))

    return {"task_id": str(task.id)}
