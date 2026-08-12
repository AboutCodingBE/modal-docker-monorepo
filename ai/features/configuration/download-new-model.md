# Deferred / Out of Scope

- **Changing which row is the default** — this context only guarantees a newly-added model is never marked default (`is_default=False`), and that existing defaults are untouched. An action to *change* the default (e.g. "set as default" button per row) is a separate, not-yet-scoped feature.
- **The analysis-configuration modal's per-type dropdown** — now that a type can have multiple model rows, the modal built in `feature-context-reflect-analysis-completion-state` (which shows one static model badge per type) needs to become a dropdown populated from all rows for that type, defaulting to whichever has `is_default=True`. That's a frontend-only follow-up context, not covered here.
- **Online/cloud LLM configuration** — still on hold, unrelated to this context.
- **spaCy or LFM2 models** — this context is Ollama-only. spaCy models are baked into the Docker image (never user-addable), and LFM2/`llama-cpp-python` is on hold entirely.

# Use Case

Let a user add a new Ollama model to the app by typing its exact model tag (e.g. `llama3.1:8b`, as it appears on `ollama.com/library` — Ollama has no API to browse its full catalog, so this must be free text, not a picker). This triggers an actual `ollama pull` via Ollama's API, with progress visible in the UI. Only on a **successful** pull does the model become usable: one row is inserted into `analysis_configuration` for each of the three analysis types (`SUMMARY`, `NER`, `TOPIC_DETECTION`), all with `is_default=False`. If the pull fails, nothing is written to the database — no status juggling, no cleanup step, no partial/failed rows to reconcile later.

This lives in a Settings/admin area, not the per-run analysis-configuration modal.

Input mechanism:
- `POST /api/models/ollama` — body `{ "model": "llama3.1:8b" }`. Starts the pull in the background, returns immediately with a `download_id`.
- `GET /api/models/ollama/{download_id}/progress` — SSE stream of pull progress for that download.

# Business Rules

- Before starting a pull, check whether `model` already has any row in `analysis_configuration`. If it does, treat this as a no-op success (`done: true, status: "already added"`) rather than re-pulling or erroring — a model is either fully present (all 3 rows) or fully absent, so existence of any one row implies all three already exist.
- The pull itself goes through Ollama's own `POST /api/pull` with `stream: true`, which returns newline-delimited JSON events. Each event may carry a `status` string (e.g. `"pulling manifest"`, `"downloading"`, `"verifying sha256 digest"`, `"success"`) and, during layer downloads, `completed`/`total` byte counts **for the current layer only** — there is no single upfront total across all layers, so don't attempt to compute one.
- If any pull event contains an `"error"` key, treat the whole operation as failed — stop, do not insert any rows, surface the error message via the progress stream.
- If the pull succeeds (`status: "success"` event received, no error), insert exactly 3 `AnalysisConfiguration` rows — one per `AnalysisType` (`SUMMARY`, `NER`, `TOPIC_DETECTION`) — all with `model=<the pulled model>` and `is_default=False`. Do this as a single DB transaction; either all 3 rows are created or none are (don't leave a partial set if something fails mid-insert).
- On any failure (Ollama unreachable, bad model name, network error, error event in the stream), no `AnalysisConfiguration` rows are created. The in-memory progress record is marked `done=True` with an `error` message; nothing needs to be cleaned up in the database, since nothing was written.
- `done=True` alone does **not** mean success — it only means the stream has ended. A consumer of the SSE endpoint must check `error` to distinguish a completed-successfully download from a completed-with-failure one, and must surface `error`'s message to the user rather than silently treating stream-closed as done. This applies to whatever frontend eventually calls this endpoint (out of scope here, but this contract must carry over into that context) — a failed download that just stops updating with no visible error message is a bad outcome to leave for later.
- Progress state lives in an **in-memory** store (a module-level dict keyed by `download_id`), not the database and not `AnalysisTask`. It does not need to survive a backend restart — an in-flight download would be interrupted by a restart regardless. Once a progress record reaches `done=True` and has been read by the SSE stream, it can be cleaned up from the in-memory store.
- The SSE endpoint polls the in-memory progress record roughly once per second (same cadence as the existing analysis-task SSE endpoint) and closes the stream once `done=True`.
- This is a fire-and-forget background operation from the API's point of view — `POST /api/models/ollama` must not block waiting for the pull to finish; it starts a background task and returns the `download_id` immediately.

# Component Overview

## Migration — add `is_default` to `analysis_configuration`

**New file:** `backend/migrations/versions/0012_add_is_default_to_analysis_configuration.py` *(adjust filename/revision numbers to whatever the actual next migration number is)*

```python
"""add is_default to analysis_configuration, drop per-type uniqueness

Revision ID: 0012
Revises: 0011
Create Date: ...
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"


def upgrade() -> None:
    # Confirmed in migration 0004: analysis_configuration.type has a named
    # unique constraint (single row per type today). Must be dropped —
    # this feature depends on multiple rows sharing the same type.
    op.drop_constraint("uq_analysis_configuration_type", "analysis_configuration", type_="unique")

    op.add_column(
        "analysis_configuration",
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Today there's exactly one row per type — that row becomes the initial default.
    op.execute("UPDATE analysis_configuration SET is_default = true")


def downgrade() -> None:
    op.drop_column("analysis_configuration", "is_default")
    op.create_unique_constraint("uq_analysis_configuration_type", "analysis_configuration", ["type"])
```

Note: `type` is a native Postgres enum column (`analysis_type_enum`, created in migration 0004) rather than a plain varchar — this doesn't affect the constraint drop above, but is worth knowing if any future migration needs to touch that column directly. Also worth independently confirming (not required for this migration, just a loose end noticed in passing): migration 0004 created the `analysis_type` enum with only `STT`, `NER`, `SUMMARY` — `TOPIC_DETECTION` must have been added to it by a later migration, since topic detection already works in the app today. Not this context's concern, just flagging it exists.

## Model — add `is_default` column

**File:** `backend/app/shared/models.py`

```python
class AnalysisConfiguration(Base):
    __tablename__ = "analysis_configuration"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    type: Mapped[str] = mapped_column(String(50), nullable=False)  # unique=True removed — multiple rows per type now
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)  # NEW
```


## GET /api/analysis/configuration — include is_default

**File:** wherever this currently lives (`analysis/start_router.py` per earlier work — confirm actual path)

```python
@router.get("/configuration")
async def get_configuration(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnalysisConfiguration))
    configs = result.scalars().all()
    return [{"type": c.type, "model": c.model, "is_default": c.is_default} for c in configs]
```

This naturally now returns multiple rows per type once models have been added — no filtering logic needed, the frontend is responsible for grouping by `type` and using `is_default` to pick which one pre-selects in its (future) dropdown.

## In-memory download progress store

**New file:** `backend/app/add_ollama_model/download_progress.py`

```python
import uuid
from dataclasses import dataclass


@dataclass
class DownloadProgress:
    status: str = "starting"
    completed_bytes: int | None = None
    total_bytes: int | None = None
    done: bool = False
    error: str | None = None


_downloads: dict[uuid.UUID, DownloadProgress] = {}


def create(download_id: uuid.UUID) -> None:
    _downloads[download_id] = DownloadProgress()


def update(download_id: uuid.UUID, **kwargs) -> None:
    progress = _downloads.get(download_id)
    if progress:
        for key, value in kwargs.items():
            setattr(progress, key, value)


def get(download_id: uuid.UUID) -> DownloadProgress | None:
    return _downloads.get(download_id)


def cleanup(download_id: uuid.UUID) -> None:
    _downloads.pop(download_id, None)
```

## Ollama pull client

**New file:** `backend/app/add_ollama_model/ollama_pull_client.py`

Uses the official `ollama` Python package rather than hand-rolled `httpx` + NDJSON parsing — it's maintained by the Ollama team itself (unlike the third-party `ollamadb.dev` catalog service discussed and deliberately not used), and its `AsyncClient` already returns parsed, dict-like progress events.

```python
from typing import Callable

from ollama import AsyncClient, ResponseError

from app.config import settings


class OllamaPullError(Exception):
    pass


async def pull_model(model: str, on_progress: Callable[[dict], None]) -> None:
    """Streams ollama-python's pull() progress events, calling on_progress(event) per event.

    Raises OllamaPullError if Ollama reports an error response or the request
    itself fails (unreachable, timeout, bad status).
    """
    try:
        client = AsyncClient(host=settings.ollama_url)
        async for progress in await client.pull(model, stream=True):
            on_progress({
                "status": progress.get("status", ""),
                "completed": progress.get("completed"),
                "total": progress.get("total"),
            })
    except ResponseError as e:
        raise OllamaPullError(e.error or str(e)) from e
    except Exception as e:
        raise OllamaPullError(f"Failed to reach Ollama: {e}") from e
```

Note: confirm the exact `AsyncClient(host=...)` constructor argument name and the precise shape of `ProgressResponse` (dict-like access vs. attribute access) against the actual installed `ollama` package version before finalizing — verified against current docs/guides as of this conversation, but pin a specific version in the dependency list rather than leaving it unpinned, since this is exactly the kind of third-party API surface that can shift between releases.

## New dependency

Add the official `ollama` package (e.g. `ollama>=0.4`, pin to a specific tested version) to the backend's dependency list (`requirements.txt`/`pyproject.toml`).

## AnalysisConfigurationRepository (new, scoped to this feature)

**New file:** `backend/app/add_ollama_model/analysis_configuration_repository.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import AnalysisConfiguration, AnalysisType


class AnalysisConfigurationRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def model_exists(self, model: str) -> bool:
        result = await self._session.execute(
            select(AnalysisConfiguration.id).where(AnalysisConfiguration.model == model)
        )
        return result.scalar_one_or_none() is not None

    async def create(self, analysis_type: AnalysisType, model: str, is_default: bool) -> None:
        config = AnalysisConfiguration(type=analysis_type.value, model=model, is_default=is_default)
        self._session.add(config)
        await self._session.flush()
```

## AddOllamaModel (flow controller)

**New file:** `backend/app/add_ollama_model/add_ollama_model.py`

```python
import logging
import uuid

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.add_ollama_model import download_progress
from app.add_ollama_model.analysis_configuration_repository import AnalysisConfigurationRepository
from app.add_ollama_model.ollama_pull_client import OllamaPullError, pull_model
from app.shared.models import AnalysisType

_logger = logging.getLogger("app")

_ALL_TYPES = (AnalysisType.SUMMARY, AnalysisType.NER, AnalysisType.TOPIC_DETECTION)


class AddOllamaModel:
    def __init__(self, session_factory: async_sessionmaker):
        self._session_factory = session_factory

    async def execute(self, download_id: uuid.UUID, model: str) -> None:
        download_progress.create(download_id)

        def _on_progress(event: dict) -> None:
            download_progress.update(
                download_id,
                status=event.get("status", ""),
                completed_bytes=event.get("completed"),
                total_bytes=event.get("total"),
            )

        try:
            async with self._session_factory() as session:
                if await AnalysisConfigurationRepository(session).model_exists(model):
                    download_progress.update(download_id, done=True, status="already added")
                    return

            await pull_model(model, _on_progress)

            async with self._session_factory() as session:
                repo = AnalysisConfigurationRepository(session)
                for analysis_type in _ALL_TYPES:
                    await repo.create(analysis_type, model, is_default=False)
                await session.commit()

            download_progress.update(download_id, done=True, status="success")

        except OllamaPullError as e:
            _logger.error(f"Failed to pull Ollama model '{model}': {e}")
            download_progress.update(download_id, done=True, error=str(e))
        except Exception as e:
            _logger.error(f"Unexpected error adding Ollama model '{model}': {e}")
            download_progress.update(download_id, done=True, error="Unexpected error, check logs")
```

## Router

**New file:** `backend/app/add_ollama_model/router.py`

```python
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
```

## Register the router

**File:** `backend/app/main.py`

```python
from app.add_ollama_model.router import router as add_ollama_model_router

app.include_router(add_ollama_model_router)
```

## No changes needed

- **`AnalysisType` enum, `classify_llm_engine`/`classify_ner_engine`** — untouched; the registry's existing fallback-to-`"ollama"` behavior already handles any new model name correctly with zero code changes
- **`CreateSummariesForArchive`, `CreateTopicDetectionForArchive`, `CreateNerForArchive`** — untouched; they already resolve providers via the registry, not via `analysis_configuration`
- **`POST /api/analysis/start`** — untouched; it already accepts any `model` string per item, and duplicate-prevention logic is unrelated to this feature
- **Frontend** — not implemented here; both the "add a model" Settings UI and the analysis-modal dropdown upgrade are follow-up work. That follow-up context must implement error display for a failed download (see the `done` vs. `error` business rule above) — don't let that requirement get lost between contexts.