# Use Case

`ArchiveAnalysisRepository` currently exists as three separate, near-identical copies:

- `backend/app/create_summaries_for_archive/archive_analysis_repository.py`
- `backend/app/create_ner_for_archive/archive_analysis_repository.py`
- `backend/app/create_topic_detection_for_archive/archive_analysis_repository.py`

All three define the same class with `create()` and `update_status()`. The `create_summaries_for_archive` copy additionally gained a `get_blocking_types()` method (added to support preventing duplicate analysis runs — see `feature-context-prevent-duplicate-analysis-start`), which the other two copies don't have, even though `get_blocking_types()` isn't summary-specific at all — it applies to any analysis type. `POST /api/analysis/start` (`start_router.py`) already imports the `create_summaries_for_archive` copy for **all** analysis types (summary, NER, topic detection alike), not just summaries — the "summary" in the import path is historical, not meaningful.

This feature consolidates all three copies into a single shared repository, so there's one class, one place to add future methods (like `get_blocking_types()`), and no risk of the copies drifting out of sync again.

This is a pure refactor: no behavior, method signatures, or SQL should change. Only the location of the class and the import statements that reference it change.

# Business Rules

- Create one canonical `ArchiveAnalysisRepository` in `backend/app/shared/archive_analysis_repository.py`, containing the union of all methods currently spread across the three copies: `create()`, `update_status()`, and `get_blocking_types()`.
- Delete the three now-redundant per-feature copies entirely:
    - `backend/app/create_summaries_for_archive/archive_analysis_repository.py`
    - `backend/app/create_ner_for_archive/archive_analysis_repository.py`
    - `backend/app/create_topic_detection_for_archive/archive_analysis_repository.py`
- Update every import of `ArchiveAnalysisRepository` across the codebase to point at `app.shared.archive_analysis_repository` instead of the old per-feature paths. Known call sites to update:
    - `backend/app/create_summaries_for_archive/create_summaries_for_archive.py`
    - `backend/app/create_ner_for_archive/create_ner_for_archive.py`
    - `backend/app/create_topic_detection_for_archive/create_topic_detection_for_archive.py`
    - `backend/app/analysis/start_router.py` (or wherever `POST /api/analysis/start` actually lives — confirm the real path in this codebase; it was referenced as `start_router.py` in prior work but its exact package location wasn't confirmed)
- After deleting the three old files and updating known call sites, search the codebase for any remaining references to `archive_analysis_repository` under `create_summaries_for_archive`, `create_ner_for_archive`, or `create_topic_detection_for_archive` (e.g. `grep -rn "archive_analysis_repository" backend/app`) to catch any importer not listed above (tests, other feature folders, etc.). Update or remove anything found.
- Do not change `create()`'s or `update_status()`'s signatures, parameter types, or internal logic — copy them into the shared file verbatim.
- Do not change `get_blocking_types()`'s signature or logic — copy it into the shared file verbatim, including its `_BLOCKING_STATUSES` constant.
- After the move, run/verify existing tests (if any exist for `create_summaries_for_archive`, `create_ner_for_archive`, `create_topic_detection_for_archive`, or `start_router`) still pass, since their imports will have changed even though behavior hasn't.

# Component Overview

## Shared ArchiveAnalysisRepository (new canonical location)

**New file:** `backend/app/shared/archive_analysis_repository.py`

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

## Delete the old copies

Remove these three files entirely:

- `backend/app/create_summaries_for_archive/archive_analysis_repository.py`
- `backend/app/create_ner_for_archive/archive_analysis_repository.py`
- `backend/app/create_topic_detection_for_archive/archive_analysis_repository.py`

## Update importers

In each file below, change the import from the old per-feature path to the new shared path. No other changes needed in these files — `ArchiveAnalysisRepository` is used the same way as before, just imported from a different module.

**`backend/app/create_summaries_for_archive/create_summaries_for_archive.py`**
```python
# before
from app.create_summaries_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
# after
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
```

**`backend/app/create_ner_for_archive/create_ner_for_archive.py`**
```python
# before
from app.create_ner_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
# after
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
```

**`backend/app/create_topic_detection_for_archive/create_topic_detection_for_archive.py`**
```python
# before
from app.create_topic_detection_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
# after
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
```

**`backend/app/analysis/start_router.py`** *(confirm actual path/package)*
```python
# before
from app.create_summaries_for_archive.archive_analysis_repository import ArchiveAnalysisRepository
# after
from app.shared.archive_analysis_repository import ArchiveAnalysisRepository
```

## No changes needed

- **Migrations** — none; this is a code-only refactor, no schema involved
- **`ArchiveAnalysis` / `ArchiveAnalysisStatus` models** — untouched
- **Any business logic** — behavior is identical before and after; only import paths change
- **Frontend** — unaffected