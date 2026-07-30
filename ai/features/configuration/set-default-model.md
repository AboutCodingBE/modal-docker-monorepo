# Use Case

Let a user change the default model for one or more analysis types in a single action — matching the wireframe's "Standaard modellen" section, which has three dropdowns (Summary/NER/Topics) sharing one "Opslaan" button. Rather than the frontend firing up to three separate requests, one batch request sets all changed defaults atomically.

Each target is identified by the `id` returned by `GET /api/settings/models` (`feature-context-list-analysis-models`) — no need to pass `type`/`model` separately, since the target row's `id` already implies both.

Input mechanism:
`PUT /api/settings/models/defaults`

Request body:
```json
{ "ids": ["70dacf9a-5b17-45cf-8734-1e761cc51422", "e251feb6-ed0c-4821-b66f-90d6464f9398"] }
```

One to three ids — the frontend only needs to include ids for dropdowns that actually changed; sending the current default's id again is a harmless no-op for that entry.

Output: the same grouped shape `GET /api/settings/models` returns (`{type: [{id, model, is_default}, ...]}`), reflecting all the changes — so the frontend can just overwrite its whole models-by-type state from the response, no follow-up `GET` needed.

This lives alongside `feature-context-list-analysis-models` — same resource, same router file, not a separate top-level feature folder (the existing `analysis/start_router.py` already bundles `GET /configuration` and `POST /start` under one file for the same reason: closely related endpoints on the same resource).

# Business Rules

- Look up every id in the request first, before changing anything. If **any** id doesn't exist, the whole request fails with `404` and nothing is changed — all-or-nothing, same philosophy as `add_ollama_model`'s "insert all 3 rows or none."
- If two or more ids in the same request resolve to rows sharing the same `type`, that's ambiguous (which one should actually become default?) — reject the whole request with `400` and change nothing. Each `type` may appear at most once per request.
- Once validated (all ids exist, no duplicate types among them), apply all changes within a single transaction: for each target row, clear `is_default` on every *other* row sharing that row's `type`, then set `is_default=True` on the target row itself. Must be atomic — never leave the table in a state with zero or multiple defaults for any type mid-operation.
- If a target row is already the default for its type, that entry is a no-op — still succeeds, not an error.
- As a side effect, this operation is self-healing per type: if the "exactly one default per type" invariant were ever violated some other way (shouldn't happen, but this fixes it if it did), including that type's id in a request corrects it back to exactly one.
- No validation beyond existence/uniqueness-of-type is needed — any row that exists in `analysis_configuration` is by definition a validly-added, successfully-downloaded model (per the success-only insertion rule from `feature-context-add-ollama-model`), so there's nothing else to check before allowing it to become the default.

# Component Overview

## AnalysisConfigurationRepository — add get_by_id() and set_defaults()

**File:** `backend/app/shared/analysis_configuration_repository.py` (already exists — extend it)

```python
import uuid

from sqlalchemy import select, update
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

    async def get_all_grouped_by_type(self) -> dict[str, list[AnalysisConfiguration]]:
        result = await self._session.execute(
            select(AnalysisConfiguration).order_by(AnalysisConfiguration.type, AnalysisConfiguration.model)
        )
        grouped: dict[str, list[AnalysisConfiguration]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.type, []).append(row)
        return grouped

    async def get_by_id(self, config_id: uuid.UUID) -> AnalysisConfiguration | None:
        return await self._session.get(AnalysisConfiguration, config_id)

    async def set_defaults(self, rows: list[AnalysisConfiguration]) -> None:
        """Sets each given row as default for its type, clearing any other
        default(s) sharing that type. Caller is responsible for having
        already validated that no two rows share a type. Does not commit.
        """
        for row in rows:
            await self._session.execute(
                update(AnalysisConfiguration)
                .where(
                    AnalysisConfiguration.type == row.type,
                    AnalysisConfiguration.id != row.id,
                )
                .values(is_default=False)
            )
            row.is_default = True
        await self._session.flush()
```

## SetDefaultModels (flow controller)

**New file:** `backend/app/list_analysis_models/set_default_models.py`

Reuses `ListAnalysisModels` for the response shape rather than duplicating the grouping/serialization logic.

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository


class DuplicateTypeError(Exception):
    """Raised when two or more ids in the same request share an analysis type."""


class SetDefaultModels:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = AnalysisConfigurationRepository(session)

    async def execute(self, config_ids: list[uuid.UUID]) -> dict[str, list[dict]] | None:
        """Returns the updated grouped models view, or None if any id doesn't exist.
        Raises DuplicateTypeError if two ids share a type.
        """
        rows = []
        for config_id in config_ids:
            row = await self._repo.get_by_id(config_id)
            if row is None:
                return None
            rows.append(row)

        seen_types = set()
        for row in rows:
            if row.type in seen_types:
                raise DuplicateTypeError(f"Multiple ids target the same analysis type: {row.type}")
            seen_types.add(row.type)

        await self._repo.set_defaults(rows)
        await self._session.commit()
        return await ListAnalysisModels(self._session).execute()
```

## Router — extend the existing one

**File:** `backend/app/list_analysis_models/router.py` (already exists — add the new route)

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.list_analysis_models.set_default_models import DuplicateTypeError, SetDefaultModels

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SetDefaultModelsRequest(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


@router.get("/models")
async def list_analysis_models(db: AsyncSession = Depends(get_db)):
    return await ListAnalysisModels(db).execute()


@router.put("/models/defaults")
async def set_default_models(body: SetDefaultModelsRequest, db: AsyncSession = Depends(get_db)):
    try:
        result = await SetDefaultModels(db).execute(body.ids)
    except DuplicateTypeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if result is None:
        raise HTTPException(status_code=404, detail="One or more configuration entries not found")
    return result
```

No change needed to `main.py` — the router is already registered from the previous context; this just adds a route to the same router instance.

Deliberately no `max_length` cap on `ids` in the request schema — there are 3 analysis types today, but hardcoding that number into the API contract would create a hidden coupling that breaks silently if a type is ever added (`AnalysisType.STT` already exists in the enum, unused). Uniqueness-of-type validation (business rules above) is what actually enforces "at most one id per type," not a count limit.

## No changes needed

- **`ListAnalysisModels`, `GET /api/settings/models`** — untouched, reused as-is for the response shape
- **`add_ollama_model`** — untouched; unrelated write path (inserting new rows, not changing which existing row is default)
- **`POST /api/analysis/start`, `GET /api/analysis/configuration`** — untouched; those endpoints don't currently read `is_default` at all (that's still a gap for the analysis-modal dropdown work, which is separate follow-up)
- **Frontend** — not implemented here