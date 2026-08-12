# Use Case

Move four processing settings out of code and into a single database row, so they become user-editable at runtime through one settings block (one save action) rather than requiring a code change and redeploy:

- The three per-analysis-type character-length caps (previously a bare `[:1000]` literal duplicated in both `create_summaries_for_archive.py` and `create_topic_detection_for_archive.py`, and `settings.ner_llm_char_limit` in `config.py`).
- A minimum text-length filter: files whose extracted Tika content is shorter than this many characters are skipped entirely, for all three analysis types — never attempted, not counted as processed or failed.

These four values are deliberately kept in **one** table and **one** save action, even though they're conceptually two different kinds of setting (a filter vs. three caps) — the product decision is one configuration block, one `PUT`, not split across multiple resources.

This is a **global, singleton** configuration — one value each, app-wide, not per-archive or per-run. Values are fetched once per analysis run (in each flow controller's existing Phase 0, alongside the file/folder list and provider resolution), never re-queried per file.

Input mechanism:
- `GET /api/settings/processing` — returns the current values.
- `PUT /api/settings/processing` — updates them, all four together.

# Business Rules

- There is always exactly one `processing_settings` row, seeded by migration. Nothing in the app ever inserts a second row — `get()` and `update()` both operate on "the" row (no id needed in the API surface).
- Four fields:
    - `summary_char_limit` (default `1000`) — replaces the literal in `create_summaries_for_archive.py`'s file-summary step. Folder summaries (`_folder_prompt`, which concatenates already-short child summaries) are **not** affected — no cap applies there today, and this doesn't change that.
    - `topic_char_limit` (default `1000`) — replaces the literal in `create_topic_detection_for_archive.py`.
    - `ner_llm_char_limit` (default `6000`) — replaces `settings.ner_llm_char_limit`. Only applies when NER runs via an LLM (Ollama), not spaCy — spaCy continues processing the full document, unchanged.
    - `minimum_text_length` (default `0`) — files whose extracted content is shorter than this are skipped entirely, for all three analysis types. `0` means "no filtering" (default on migration, so shipping this doesn't silently change behavior for existing installs until a user explicitly sets a threshold).
- `summary_char_limit`, `topic_char_limit`, `ner_llm_char_limit` must be positive integers (`> 0`). `minimum_text_length` must be a non-negative integer (`>= 0` — `0` is a valid, meaningful value here, unlike the other three). Validate this at the API layer (`PUT` request) rather than relying on the database alone to catch it.
- Each flow controller fetches the settings row exactly once, in its existing Phase 0 (same place `provider` is already resolved via `get_llm_provider(classify_llm_engine(model))`), and reuses that single fetched row for every file/folder in the loop — never fetched inside the per-file loop.
- `minimum_text_length` filtering happens in that same Phase 0, right after fetching the file list and before `task_tracker.update_total_files(...)` is called: drop any file where `len(file["content"] or "") < minimum_text_length`, so `total_files` only counts files that will actually be attempted. This filter only applies to files, not folders — folder-level aggregation operates on already-produced file-level results, not raw extracted text length.
- The existing `total_files`/progress-count accuracy has a known pre-existing issue unrelated to this feature — out of scope here, not something to investigate or fix as part of this change. Keep the filtering logic simple (just don't include filtered-out files in the count going in) rather than trying to reconcile it with that separate issue.
- `config.py`'s `ner_llm_char_limit` setting becomes redundant once this ships and should be removed, so there's exactly one source of truth for this value (same reasoning as the earlier `ArchiveAnalysisRepository`/`ollama_client` de-duplication work this session — don't leave a second, now-unused copy lying around).

# Component Overview

## Migration — new `processing_settings` table

**New file:** `backend/migrations/versions/0013_add_processing_settings.py` *(adjust filename/revision to the actual next migration number)*

```python
"""add processing_settings table

Revision ID: 0013
Revises: 0012
Create Date: ...
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0013"
down_revision: str | None = "0012"


def upgrade() -> None:
    op.create_table(
        "processing_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("summary_char_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("topic_char_limit", sa.Integer(), nullable=False, server_default="1000"),
        sa.Column("ner_llm_char_limit", sa.Integer(), nullable=False, server_default="6000"),
        sa.Column("minimum_text_length", sa.Integer(), nullable=False, server_default="0"),
    )
    # Seed the single row the app always expects to exist.
    op.execute(
        "INSERT INTO processing_settings "
        "(id, summary_char_limit, topic_char_limit, ner_llm_char_limit, minimum_text_length) "
        "VALUES (gen_random_uuid(), 1000, 1000, 6000, 0)"
    )


def downgrade() -> None:
    op.drop_table("processing_settings")
```

## Model

**File:** `backend/app/shared/models.py`

```python
class ProcessingSettings(Base):
    __tablename__ = "processing_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    summary_char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    topic_char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    ner_llm_char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=6000)
    minimum_text_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
```

## Repository

**New file:** `backend/app/shared/processing_settings_repository.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ProcessingSettings


class ProcessingSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self) -> ProcessingSettings:
        """Returns the single processing_settings row. Always exists (seeded by migration)."""
        result = await self._session.execute(select(ProcessingSettings).limit(1))
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            raise RuntimeError("processing_settings row missing — expected exactly one row, seeded by migration")
        return settings_row

    async def update(
        self,
        summary_char_limit: int,
        topic_char_limit: int,
        ner_llm_char_limit: int,
        minimum_text_length: int,
    ) -> ProcessingSettings:
        settings_row = await self.get()
        settings_row.summary_char_limit = summary_char_limit
        settings_row.topic_char_limit = topic_char_limit
        settings_row.ner_llm_char_limit = ner_llm_char_limit
        settings_row.minimum_text_length = minimum_text_length
        await self._session.flush()
        return settings_row
```

## Router

**New file:** `backend/app/processing_settings/router.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.processing_settings_repository import ProcessingSettingsRepository

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ProcessingSettingsResponse(BaseModel):
    summary_char_limit: int
    topic_char_limit: int
    ner_llm_char_limit: int
    minimum_text_length: int


class UpdateProcessingSettingsRequest(BaseModel):
    summary_char_limit: int = Field(gt=0)
    topic_char_limit: int = Field(gt=0)
    ner_llm_char_limit: int = Field(gt=0)
    minimum_text_length: int = Field(ge=0)  # 0 is valid here — means "no filtering"


@router.get("/processing", response_model=ProcessingSettingsResponse)
async def get_processing_settings(db: AsyncSession = Depends(get_db)):
    return await ProcessingSettingsRepository(db).get()


@router.put("/processing", response_model=ProcessingSettingsResponse)
async def update_processing_settings(
    body: UpdateProcessingSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await ProcessingSettingsRepository(db).update(
        body.summary_char_limit,
        body.topic_char_limit,
        body.ner_llm_char_limit,
        body.minimum_text_length,
    )
    await db.commit()
    return result
```

## Register the router

**File:** `backend/app/main.py`

```python
from app.processing_settings.router import router as processing_settings_router

app.include_router(processing_settings_router)
```

## CreateSummariesForArchive — use the DB value

**File:** `backend/app/create_summaries_for_archive/create_summaries_for_archive.py`

```python
# add import
from app.shared.processing_settings_repository import ProcessingSettingsRepository
```

Rewrite the whole Phase 0 block as one coherent unit — fetch `processing_settings` first (needed for the filter), then filter `files` before `update_total_files` is called:

```python
# before — full Phase 0
async with self._session_factory() as session:
    await task_tracker.start_task(session, task_id)
    file_repo = FileRepository(session)
    files = await file_repo.get_files_with_tika_content(archive_id)
    folders = await file_repo.get_all_folders(archive_id)
    await task_tracker.update_total_files(session, task_id, len(files) + len(folders))
    await session.commit()

processed = 0
failed_count = 0
consecutive_failures = 0

provider = get_llm_provider(classify_llm_engine(model))
```

```python
# after — full Phase 0
async with self._session_factory() as session:
    await task_tracker.start_task(session, task_id)
    processing_settings = await ProcessingSettingsRepository(session).get()

    file_repo = FileRepository(session)
    files = await file_repo.get_files_with_tika_content(archive_id)
    folders = await file_repo.get_all_folders(archive_id)

    if processing_settings.minimum_text_length > 0:
        files = [
            f for f in files
            if len(f["content"] or "") >= processing_settings.minimum_text_length
        ]

    await task_tracker.update_total_files(session, task_id, len(files) + len(folders))
    await session.commit()

processed = 0
failed_count = 0
consecutive_failures = 0

provider = get_llm_provider(classify_llm_engine(model))
```

```python
# before, inside the file loop
text = (file["content"] or "")[:1000]
```

```python
# after
text = (file["content"] or "")[:processing_settings.summary_char_limit]
```

Folder summaries (`_folder_prompt(concatenated)`) are unchanged — no cap applied there, as noted in Business Rules.

## CreateTopicDetectionForArchive — use the DB value

**File:** `backend/app/create_topic_detection_for_archive/create_topic_detection_for_archive.py`

Same pattern as above: rewrite Phase 0 to fetch `processing_settings` first, filter `files` by `minimum_text_length` before `update_total_files`, then replace:

```python
# before
text = (file["content"] or "")[:1000]
```

```python
# after
text = (file["content"] or "")[:processing_settings.topic_char_limit]
```

## CreateNerForArchive — use the DB value

**File:** `backend/app/create_ner_for_archive/create_ner_for_archive.py`

```python
# before
ner_result = await run_ner_llm(text[:settings.ner_llm_char_limit], model, provider)
```

```python
# after
ner_result = await run_ner_llm(text[:processing_settings.ner_llm_char_limit], model, provider)
```

Same Phase-0 rewrite as the other two flow controllers — fetch `processing_settings` first, filter `files` by `minimum_text_length` before `update_total_files`, reuse `processing_settings` for every file in the loop. The `settings` import (from `app.config`) may become unused in this file after this change if `ner_llm_char_limit` was its only usage here — check and remove the import if so.

## config.py — remove the now-redundant setting

**File:** `backend/app/config.py`

Remove `ner_llm_char_limit: int = 6000` — this value now lives exclusively in `processing_settings`.

## No changes needed

- **`ner_llm_engine.py`, `_ner_prompt`, `_topic_prompt`, `_file_prompt`, `_folder_prompt`** — untouched; truncation happens before the prompt is built, not inside these functions
- **`LlmProvider`, `OllamaProvider`, `analysis_engine_registry.py`** — untouched, unrelated to this feature
- **`AnalysisConfiguration` / the Ollama-model-adding feature** — untouched; this is a separate table for a separate kind of setting (see earlier note distinguishing "a handful of singleton values" from "a growable table of rows")
- **Frontend** — not implemented here; the settings screen that calls `GET`/`PUT /api/settings/processing` is a follow-up