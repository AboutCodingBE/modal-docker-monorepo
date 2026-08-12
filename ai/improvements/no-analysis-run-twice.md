# Use Case

Prevent `POST /api/analysis/start` from starting an analysis type that is already completed, or currently running, for the given archive. The frontend already prevents users from selecting these types in the modal (they're shown as "Reeds uitgevoerd" / not offered as checkboxes), so this is a server-side safety net, not a user-facing validation flow — if a conflicting type does arrive in a request, it means either a stale frontend state or someone bypassing the UI, not a normal user error.

The input of this use case:
- `archiveId` (UUID)
- `analysis` — list of `{ type: str, model: str }` items to start

Input mechanism of this use case:
`POST /api/analysis/start` (existing endpoint, request body unchanged)

The output of this feature:
Same response shape as today — `{ "task_ids": [...] }` — but `task_ids` only contains tasks for the analysis types that were actually started. Conflicting types are silently dropped from processing; they are not included in the response and no error is raised because of them.

If every requested type conflicts, the endpoint still returns `200` with `{ "task_ids": [] }` — this is not treated as an error case.

# Business Rules

- Before creating an `ArchiveAnalysis` + `AnalysisTask` for a requested item, check whether that `(archive_id, type)` combination already has an `ArchiveAnalysis` row with `status` in `{STARTED, COMPLETED}`.
    - `STARTED` — an analysis of this type is currently running for this archive; don't start a second one concurrently.
    - `COMPLETED` — this type has already been analysed for this archive; don't silently duplicate it.
    - `FAILED` and `CANCELLED` do **not** block a retry — a previously failed or cancelled analysis of that type may be started again.
- Matching is case-insensitive: normalize both the incoming `item.type` and the stored `ArchiveAnalysis.type` (an `AnalysisType` enum) to uppercase before comparing, consistent with the existing `analysis_type.upper()` call already used when creating `ArchiveAnalysis` rows.
- If the same type appears more than once within a single request's `analysis` list, only the first occurrence may be started; treat subsequent occurrences in the same request as conflicting too (don't create duplicate jobs from one request).
- Conflicting items are dropped silently: no `HTTPException`, no error field in the response, no partial-failure signaling. Log a warning (not an error) noting the archive id and the skipped type(s), since this indicates either stale frontend state or direct API misuse, and may be worth noticing without treating it as a genuine failure.
- Non-conflicting items in the same request must still be processed exactly as today (job created, background task kicked off).
- Do not change the response shape beyond `task_ids` naturally reflecting fewer (or zero) entries when items were skipped.

# Component Overview

## ArchiveAnalysisRepository (extend existing)

**File:** `backend/app/create_summaries_for_archive/archive_analysis_repository.py`

Add a method to fetch which types are currently blocking (started or completed) for an archive.

```python
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ArchiveAnalysis, ArchiveAnalysisStatus

_BLOCKING_STATUSES = (ArchiveAnalysisStatus.STARTED, ArchiveAnalysisStatus.COMPLETED)


class ArchiveAnalysisRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def create(
        self,
        archive_id: uuid.UUID,
        analysis_type: str,
        model: str,
    ) -> ArchiveAnalysis:
        analysis = ArchiveAnalysis(
            archive_id=archive_id,
            type=analysis_type.upper(),
            date=date.today(),
            model=model,
            status="STARTED",
        )
        self._session.add(analysis)
        await self._session.flush()
        await self._session.refresh(analysis)
        return analysis

    async def update_status(self, analysis_id: uuid.UUID, status: str) -> None:
        result = await self._session.execute(
            select(ArchiveAnalysis).where(ArchiveAnalysis.id == analysis_id)
        )
        analysis = result.scalar_one_or_none()
        if analysis:
            analysis.status = status
            await self._session.flush()

    async def get_blocking_types(self, archive_id: uuid.UUID) -> set[str]:
        """Types with a STARTED or COMPLETED ArchiveAnalysis for this archive.

        Values are uppercase (matching AnalysisType enum values), for
        case-normalized comparison against incoming request types.
        """
        result = await self._session.execute(
            select(ArchiveAnalysis.type).where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.status.in_(_BLOCKING_STATUSES),
            )
        )
        return {t.value for t in result.scalars().all()}
```

This component depends on:
- `ArchiveAnalysis`, `ArchiveAnalysisStatus` from `app.shared.models`

## start_analysis (extend existing)

**File:** `backend/app/analysis/start_router.py` *(adjust path to wherever this actually lives — shown here as `start_router.py` per the file you shared)*

Filter `body.analysis` against the blocking types before creating any jobs. Track types accepted within this request too, so duplicate types inside a single request don't both get created.

```python
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
```

Changes from the existing version, summarized:
- Fetch `blocking_types` once up front via the new repository method.
- Skip (and log) any requested item whose normalized type is already in `blocking_types`, instead of unconditionally creating a job for it.
- Add the just-accepted type to `blocking_types` inside the loop, so a second occurrence of the same type later in the same request is also skipped.
- Guard `asyncio.create_task(_run_sequential(jobs))` behind `if jobs:` so an all-skipped request doesn't spawn a no-op background task.

This component depends on:
- `ArchiveAnalysisRepository.get_blocking_types` (new)

## No changes needed

- **`GET /api/analysis/configuration`** — untouched
- **Migrations** — no schema changes
- **Frontend** — not wired up in this context; it already avoids offering completed/running types, this is the backend-side enforcement of the same rule
- **`GET /api/archives` completed-types field** — handled in a separate feature context; unrelated to this endpoint