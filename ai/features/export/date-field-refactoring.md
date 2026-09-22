# Use Case

`archive_analysis.date` is a plain `Date` column (no time component), used across several already-shipped endpoints as the tiebreaker for "which analysis run is the most recent for this (archive, type)." Two runs completed on the same calendar day — entirely plausible once "redo an analysis" ships, and easy to hit even just during testing/iteration — cannot be distinguished by `date` alone, so `ORDER BY date DESC` becomes ambiguous exactly when it matters most.

Fix: replace `date` with `analyzed_at` (`DateTime(timezone=True)`), matching the naming convention already used elsewhere in this schema (`tika_analyses.analyzed_at`, `generic_types.analyzed_at`). This also makes the value directly useful as export-visible "when was this analysis done" data (see `feature-context-export-archive`, which depends on this).

# Business Rules

- Rename `archive_analysis.date` (`Date`) to `archive_analysis.analyzed_at` (`DateTime(timezone=True)`, `nullable=False`, `server_default=func.now()`).
- Existing rows: backfill `analyzed_at` from the old `date` value (midnight UTC on that date) rather than leaving them null — there's no better information available for historical rows, but they still need a valid, non-null timestamp.
- `ArchiveAnalysisRepository.create()` currently sets `date=date.today()` explicitly — remove that explicit assignment entirely and rely on the column's `server_default=func.now()`, consistent with how `tika_analyses.analyzed_at`/`generic_types.analyzed_at` are already populated (not set explicitly in application code).
- Every existing query ordering by `ArchiveAnalysis.date` must be updated to order by `ArchiveAnalysis.analyzed_at` instead. Known call sites (search for more — this list is from what's been built earlier in this project, not guaranteed exhaustive):
    - `get_ner_for_file` (`NerForFileRepository`)
    - `get_ner_for_folder` (`NerForFolderRepository`)
    - `get_topics_for_file` (`TopicsForFileRepository`)
    - `get_topics_for_folder` (`TopicsForFolderRepository`)
    - Any summary-fetching equivalent, if one exists with the same "most recent" pattern — not directly confirmed in this conversation, check for it.
    - `feature-context-export-archive`'s `ExportDataRepository` — ships *before* this fix, deliberately reading `archive_analysis.date` for now (sequencing decision — no redo capability exists yet, so `date` is unambiguous in practice today). That file has an explicit `TODO` comment marking the one line to change (`.date` → `.analyzed_at`) once this migration lands.
- After making the rename, search the codebase for any remaining reference to `ArchiveAnalysis.date` or `archive_analysis.date` (e.g. `grep -rn "\.date\b" backend/app | grep -i archive_analysis` and a broader `grep -rn "ArchiveAnalysis" backend/app`) to catch anything not listed above.

# Component Overview

## Migration

**New file:** `backend/migrations/versions/0016_archive_analysis_analyzed_at.py` *(adjust filename/revision to the actual next migration number — this assumes the export-related migrations landed as 0014/0015)*

```python
"""rename archive_analysis.date to analyzed_at (DateTime, not Date)

Revision ID: 0016
Revises: 0015
Create Date: ...
"""
import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"


def upgrade() -> None:
    op.add_column(
        "archive_analysis",
        sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Backfill from the old date column — midnight UTC on that date, the
    # best available information for historical rows.
    op.execute("UPDATE archive_analysis SET analyzed_at = date::timestamptz")
    op.alter_column("archive_analysis", "analyzed_at", nullable=False, server_default=sa.func.now())
    op.drop_column("archive_analysis", "date")


def downgrade() -> None:
    op.add_column(
        "archive_analysis",
        sa.Column("date", sa.Date(), nullable=True, server_default=sa.func.current_date()),
    )
    op.execute("UPDATE archive_analysis SET date = analyzed_at::date")
    op.alter_column("archive_analysis", "date", nullable=False)
    op.drop_column("archive_analysis", "analyzed_at")
```

## Model

**File:** `backend/app/shared/models.py`

```python
class ArchiveAnalysis(Base):
    __tablename__ = "archive_analysis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    archive_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("archives.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[AnalysisType] = mapped_column(Enum(AnalysisType, name="analysis_type"), nullable=False)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())  # was: date: Mapped[date]
    model: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[ArchiveAnalysisStatus] = mapped_column(Enum(ArchiveAnalysisStatus, name="archive_analysis_status"), nullable=False)
```

## ArchiveAnalysisRepository — drop the explicit date assignment

**File:** `backend/app/shared/archive_analysis_repository.py`

```python
# before
async def create(self, archive_id: uuid.UUID, analysis_type: str, model: str) -> ArchiveAnalysis:
    analysis = ArchiveAnalysis(
        archive_id=archive_id,
        type=analysis_type.upper(),
        date=date.today(),
        model=model,
        status="STARTED",
    )
    ...
```

```python
# after
async def create(self, archive_id: uuid.UUID, analysis_type: str, model: str) -> ArchiveAnalysis:
    analysis = ArchiveAnalysis(
        archive_id=archive_id,
        type=analysis_type.upper(),
        model=model,
        status="STARTED",
    )
    # analyzed_at is populated by the column's server_default, not set here.
    ...
```

The now-unused `from datetime import date` import (if `date` isn't used elsewhere in this file) should be removed.

## Update all "most recent" ordering call sites

In each of the following, replace `.order_by(ArchiveAnalysis.date.desc())` with `.order_by(ArchiveAnalysis.analyzed_at.desc())`. No other logic changes in these files.

- `backend/app/get_ner_for_file/repository.py` (`NerForFileRepository`)
- `backend/app/get_ner_for_folder/repository.py` (`NerForFolderRepository`)
- `backend/app/get_topics_for_file/repository.py` (`TopicsForFileRepository`)
- `backend/app/get_topics_for_folder/repository.py` (`TopicsForFolderRepository`)
- Any equivalent summary-fetching repository — verify whether one exists with the same pattern; not confirmed in this conversation.

## No changes needed

- **`Summary`, `Ner`, `TopicDetection` models/tables** — untouched, this only affects `archive_analysis`
- **`AnalysisTask`, `analysis_tasks` table** — a separate table entirely, already has proper `DateTime` columns (`created_at`, `started_at`, `completed_at`), not affected by this
- **Frontend** — not affected; `analyzed_at` isn't currently surfaced anywhere in the UI (only used internally for ordering, until the export feature exposes it)