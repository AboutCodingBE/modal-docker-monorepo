# Use Case

Show, per analysis type, which models are available and which one is currently the default — so a user can see the full picture and (in a follow-up feature) change the default. One query, grouped server-side by type, so the frontend receives data it can render directly without doing any grouping/parsing itself.

Input mechanism:
`GET /api/settings/models`

Output — a dict keyed by analysis type, each value a list of `{id, model, is_default}`:

```json
{
  "SUMMARY": [
    {"id": "c8477c50-3ac9-41c9-9173-25c5671e7775", "model": "gemma3:1b", "is_default": true},
    {"id": "a1b2c3d4-...", "model": "llama3.1:8b", "is_default": false}
  ],
  "NER": [
    {"id": "70dacf9a-5b17-45cf-8734-1e761cc51422", "model": "nl_core_news_lg", "is_default": true},
    {"id": "e5f6a7b8-...", "model": "gemma3:1b", "is_default": false}
  ],
  "TOPIC_DETECTION": [
    {"id": "e251feb6-ed0c-4821-b66f-90d6464f9398", "model": "gemma3:1b", "is_default": true}
  ]
}
```

Including each row's own `id` (rather than identifying a row by `(type, model)`) is deliberate — it's what a future "set default" `PUT` should use to unambiguously target a specific row, since nothing currently guarantees `(type, model)` pairs are unique at the database level (only `add_ollama_model`'s own existence check prevents duplicates in practice, not a DB constraint).

# Business Rules

- One query fetches every `analysis_configuration` row, ordered by `type`. Grouping into the per-type dict happens in Python immediately after — this is a partition, not a SQL aggregate, since no values are being summed/counted, just organized by key.
- Each type's list is in the order the query returns (ordering by `type` then `model` is enough for stable, predictable output — no specific sort requirement beyond "consistent").
- Exactly one entry per type should have `is_default: true` in practice (enforced by the "set default" feature, not by this endpoint — this endpoint only reads and reports, it doesn't validate or repair the invariant).
- If a type somehow has zero rows, it simply doesn't appear as a key in the response — don't fabricate an empty list for a type with nothing configured. In practice this shouldn't currently happen, since all three types (`SUMMARY`, `NER`, `TOPIC_DETECTION`) already have at least one seeded row.

# Component Overview

## Move AnalysisConfigurationRepository to a shared location

**Move:** `backend/app/add_ollama_model/analysis_configuration_repository.py` → `backend/app/shared/analysis_configuration_repository.py`

This repository already exists (added in `feature-context-add-ollama-model`) with `model_exists()` and `create()`. Rather than create a second copy for this feature, move it to `app/shared/` and add a new method there. Update the import in `backend/app/add_ollama_model/add_ollama_model.py` accordingly (`from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository`) — no behavioral change to the existing methods, just relocating the file and adding one more method to it.

**File after the move:** `backend/app/shared/analysis_configuration_repository.py`

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

    async def get_all_grouped_by_type(self) -> dict[str, list[AnalysisConfiguration]]:
        """One query, all rows, ordered by type — grouping happens in Python below."""
        result = await self._session.execute(
            select(AnalysisConfiguration).order_by(AnalysisConfiguration.type, AnalysisConfiguration.model)
        )
        grouped: dict[str, list[AnalysisConfiguration]] = {}
        for row in result.scalars().all():
            grouped.setdefault(row.type, []).append(row)
        return grouped
```

## ListAnalysisModels (flow controller)

**New file:** `backend/app/list_analysis_models/list_analysis_models.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.analysis_configuration_repository import AnalysisConfigurationRepository


class ListAnalysisModels:
    def __init__(self, session: AsyncSession):
        self._repo = AnalysisConfigurationRepository(session)

    async def execute(self) -> dict[str, list[dict]]:
        grouped = await self._repo.get_all_grouped_by_type()
        return {
            analysis_type: [
                {"id": str(row.id), "model": row.model, "is_default": row.is_default} for row in rows
            ]
            for analysis_type, rows in grouped.items()
        }
```

## Router

**New file:** `backend/app/list_analysis_models/router.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.list_analysis_models.list_analysis_models import ListAnalysisModels

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("/models")
async def list_analysis_models(db: AsyncSession = Depends(get_db)):
    return await ListAnalysisModels(db).execute()
```

## Register the router

**File:** `backend/app/main.py`

```python
from app.list_analysis_models.router import router as list_analysis_models_router

app.include_router(list_analysis_models_router)
```

## No changes needed

- **`AnalysisConfiguration` model, migrations** — untouched; this is a read-only feature over existing data
- **`add_ollama_model`'s flow controller/router** — untouched, only its repository import path changes
- **`GET /api/analysis/configuration`** — untouched; that endpoint still returns a flat list (used by the analysis-start flow), this new endpoint is a different, grouped shape for a different purpose (the settings screen)
- **"Set default" action** — not implemented here; this feature only reads and displays, changing the default is separate follow-up work. That follow-up should target rows by `id` (as returned here), not by `(type, model)` — keep that contract consistent between the two contexts.
- **Frontend** — not implemented here