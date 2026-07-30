# Use Case

Let a user change which model is the default for a given analysis type, using the `id` returned by `GET /api/settings/models` (`feature-context-list-analysis-models`) to unambiguously target a specific row — no need to pass `type`/`model` separately, since the target row's `id` already implies both.

Input mechanism:
`PUT /api/settings/models/{config_id}/default`

Output: the same grouped shape `GET /api/settings/models` returns (`{type: [{id, model, is_default}, ...]}`), reflecting the change — so the frontend can just overwrite its whole models-by-type state from the response, no follow-up `GET` needed.

This lives alongside `feature-context-list-analysis-models` — same resource, same router file, not a separate top-level feature folder (the existing `analysis/start_router.py` already bundles `GET /configuration` and `POST /start` under one file for the same reason: closely related endpoints on the same resource).

# Business Rules

- Look up the target row by `id` alone. Its `type` is read from the row itself — never passed in by the client — so there's no way for a mismatched `type` to be supplied by mistake.
- If no row with that `id` exists, return `404`.
- Within a single transaction: clear `is_default` on every *other* row sharing that row's `type`, then set `is_default=True` on the target row. Must happen atomically — never leave the table in a state with zero or multiple defaults for a type mid-operation.
- If the target row is already the default, this is a no-op that still returns success (same response shape) — not an error.
- As a side effect, this operation is self-healing: if the "exactly one default per type" invariant were ever violated some other way (shouldn't happen, but this fixes it if it did), calling this endpoint for that type corrects it back to exactly one.
- No validation beyond existence is needed — any row that exists in `analysis_configuration` is by definition a validly-added, successfully-downloaded model (per the success-only insertion rule from `feature-context-add-ollama-model`), so there's nothing else to check before allowing it to become the default.

# Component Overview

## AnalysisConfigurationRepository — add set_default()

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

    async def set_default(self, config_id: uuid.UUID) -> AnalysisConfiguration | None:
        """Sets config_id as the default for its type, clearing any other
        default(s) sharing that type. Returns the target row, or None if
        config_id doesn't exist. Does not commit — caller's responsibility.
        """
        target = await self._session.get(AnalysisConfiguration, config_id)
        if target is None:
            return None

        await self._session.execute(
            update(AnalysisConfiguration)
            .where(
                AnalysisConfiguration.type == target.type,
                AnalysisConfiguration.id != target.id,
            )
            .values(is_default=False)
        )
        target.is_default = True
        await self._session.flush()
        return target
```

## SetDefaultModel (flow controller)

**New file:** `backend/app/list_analysis_models/set_default_model.py`

Reuses `ListAnalysisModels` for the response shape rather than duplicating the grouping/serialization logic.

```python
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository


class SetDefaultModel:
    def __init__(self, session: AsyncSession):
        self._session = session
        self._repo = AnalysisConfigurationRepository(session)

    async def execute(self, config_id: uuid.UUID) -> dict[str, list[dict]] | None:
        target = await self._repo.set_default(config_id)
        if target is None:
            return None

        await self._session.commit()
        return await ListAnalysisModels(self._session).execute()
```

## Router — extend the existing one

**File:** `backend/app/list_analysis_models/router.py` (already exists — add the new route)

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_analysis_models.list_analysis_models import ListAnalysisModels
from app.list_analysis_models.set_default_model import SetDefaultModel

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/models")
async def list_analysis_models(db: AsyncSession = Depends(get_db)):
    return await ListAnalysisModels(db).execute()


@router.put("/models/{config_id}/default")
async def set_default_model(config_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await SetDefaultModel(db).execute(config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Configuration entry not found")
    return result
```

No change needed to `main.py` — the router is already registered from the previous context; this just adds a route to the same router instance.

## No changes needed

- **`ListAnalysisModels`, `GET /api/settings/models`** — untouched, reused as-is for the response shape
- **`add_ollama_model`** — untouched; unrelated write path (inserting new rows, not changing which existing row is default)
- **`POST /api/analysis/start`, `GET /api/analysis/configuration`** — untouched; those endpoints don't currently read `is_default` at all (that's still a gap for the analysis-modal dropdown work, which is separate follow-up)
- **Frontend** — not implemented here