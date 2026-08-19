# Use Case

Extend the existing archive overview endpoint so each archive in the list reports which analysis types have already completed for it. The frontend needs this to render the per-archive analysis badges on the archive card (done vs. pending, per type) and, combined with `GET /api/analysis/configuration`, to decide whether to show the "Analyse" button at all (hidden once every available type is done).

This context only covers the backend data. No new endpoint is introduced — the existing `GET /api/archives` response is extended with one new field per archive.

The input of this use case: none (no new parameters; same endpoint, same call).

Input mechanism of this use case:
`GET /api/archives` (unchanged)

The output of this feature:
Each archive object in the existing response array gains a `completed_analysis_types` field: a deduplicated list of analysis type strings that have a `COMPLETED` `ArchiveAnalysis` record for that archive.

Example response (one archive):
```json
{
  "id": "...",
  "name": "karltest3",
  "date": "2026-06-14",
  "files": 62,
  "status": "analysed",
  "completed_analysis_types": ["SUMMARY", "NER", "TOPIC_DETECTION"]
}
```

Archive with only a subset done:
```json
{
  "id": "...",
  "name": "summary-test7",
  "date": "2026-07-06",
  "files": 90,
  "status": "in_progress",
  "completed_analysis_types": ["SUMMARY"]
}
```

Freshly ingested archive with nothing analysed yet:
```json
{
  "id": "...",
  "name": "specific-test5",
  "date": "2026-06-30",
  "files": 5,
  "status": "ingested",
  "completed_analysis_types": []
}
```

# Business Rules

- A type counts as "completed" for an archive only if there is an `ArchiveAnalysis` row for that `archive_id` and `type` with `status == COMPLETED`. `STARTED`, `FAILED`, and `CANCELLED` do not count — a currently running, failed, or cancelled analysis must not show as done on the card.
- If a type has completed more than once (re-analysis), it must appear only once in `completed_analysis_types` (deduplicated).
- `completed_analysis_types` values are uppercase strings taken directly from the `AnalysisType` enum value (e.g. `AnalysisType.NER.value` → `"NER"`). This has been confirmed to match the casing `analysis_configuration.type` uses in the database (`"SUMMARY"`, `"NER"`, `"TOPIC_DETECTION"`), so the frontend can compare the two lists directly without any case normalization.
- Archives with zero completed analyses must still return `completed_analysis_types: []`, not `null` and not an omitted field.
- Do not change any of the existing fields (`id`, `name`, `date`, `files`, `status`) or their meaning.
- Fetch this in a single additional query (or a join), not one query per archive — avoid N+1 queries when building the list.

# Component Overview

## ArchiveRepository (extend existing)

**File:** `backend/app/get_archive_overview/archive_repository.py`

Add a method to fetch completed analysis types for all archives in one query, and use it in `get_all()`.

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import Archive, ArchiveAnalysis, ArchiveAnalysisStatus

_STATUS_MAP = {
    "pending": "ingested",
    "in_progress": "in_progress",
    "completed": "analysed",
    "failed": "failed",
}


class ArchiveRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_all(self) -> list[dict]:
        result = await self._session.execute(
            select(Archive).order_by(Archive.created_at.desc())
        )
        archives = result.scalars().all()

        completed_by_archive = await self._get_completed_types_by_archive()

        return [
            {
                "id": str(a.id),
                "name": a.name,
                "date": a.created_at.date().isoformat() if a.created_at else "",
                "files": a.file_count,
                "status": _STATUS_MAP.get(a.analysis_status, "ingested"),
                "completed_analysis_types": sorted(completed_by_archive.get(a.id, set())),
            }
            for a in archives
        ]

    async def _get_completed_types_by_archive(self) -> dict:
        """One query for all archives: archive_id -> set of completed type strings.

        Values stay uppercase (AnalysisType enum value), matching the casing
        used by analysis_configuration.type, so the frontend can compare the
        two lists directly.
        """
        result = await self._session.execute(
            select(ArchiveAnalysis.archive_id, ArchiveAnalysis.type)
            .where(ArchiveAnalysis.status == ArchiveAnalysisStatus.COMPLETED)
            .distinct()
        )
        completed_by_archive: dict = {}
        for archive_id, analysis_type in result.all():
            completed_by_archive.setdefault(archive_id, set()).add(analysis_type.value)
        return completed_by_archive
```

This component depends on:
- `Archive`, `ArchiveAnalysis`, `ArchiveAnalysisStatus` from `app.shared.models`

## GetArchives / router

No changes needed — `GetArchives.execute()` already just delegates to `ArchiveRepository.get_all()`, and `router.py`'s `GET /api/archives` handler already returns whatever `GetArchives` produces. The new field flows through automatically once `ArchiveRepository.get_all()` is updated.

## No changes needed

- **`GET /api/analysis/configuration`** — untouched; still the source of truth for which analysis types exist at all
- **Migrations** — no schema changes; this only reads existing `archive_analysis` rows
- **`POST /api/analysis/start`** — handled in a separate feature context (preventing re-running completed/active analysis types)
- **Frontend** — not wired up in this context; badge rendering and button-hiding logic happen later