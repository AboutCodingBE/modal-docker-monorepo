# Use Case

Move the three per-analysis-type character-length caps out of code (a bare `[:1000]` literal duplicated in both `create_summaries_for_archive.py` and `create_topic_detection_for_archive.py`, and `settings.ner_llm_char_limit` in `config.py`) into a single database row, so they become user-editable at runtime through a settings screen rather than requiring a code change and redeploy.

This is a **global, singleton** configuration — one value each, app-wide, not per-archive or per-run (confirmed earlier in this conversation). Values are fetched once per analysis run (in each flow controller's existing Phase 0, alongside the file/folder list and provider resolution), never re-queried per file.

Input mechanism:
- `GET /api/settings/processing` — returns the current values.
- `PUT /api/settings/processing` — updates them.

# Business Rules

- There is always exactly one `processing_settings` row, seeded by migration. Nothing in the app ever inserts a second row — `get()` and `update()` both operate on "the" row (no id needed in the API surface).
- Three fields:
    - `summary_char_limit` (default `1000`) — replaces the literal in `create_summaries_for_archive.py`'s file-summary step. Folder summaries (`_folder_prompt`, which concatenates already-short child summaries) are **not** affected — no cap applies there today, and this doesn't change that.
    - `topic_char_limit` (default `1000`) — replaces the literal in `create_topic_detection_for_archive.py`.
    - `ner_llm_char_limit` (default `6000`) — replaces `settings.ner_llm_char_limit`. Only applies when NER runs via an LLM (Ollama), not spaCy — spaCy continues processing the full document, unchanged.
- All three must be positive integers (`> 0`); validate this at the API layer (`PUT` request) rather than relying on the database alone to catch it.
- Each flow controller fetches the settings row exactly once, in its existing Phase 0 (same place `provider` is already resolved via `get_llm_provider(classify_llm_engine(model))`), and reuses that single fetched value for every file/folder in the loop — never fetched inside the per-file loop.
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
    )
    # Seed the single row the app always expects to exist.
    op.execute(
        "INSERT INTO processing_settings (id, summary_char_limit, topic_char_limit, ner_llm_char_limit) "
        "VALUES (gen_random_uuid(), 1000, 1000, 6000)"
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
    ) -> ProcessingSettings:
        settings_row = await self.get()
        settings_row.summary_char_limit = summary_char_limit
        settings_row.topic_char_limit = topic_char_limit
        settings_row.ner_llm_char_limit = ner_llm_char_limit
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


class UpdateProcessingSettingsRequest(BaseModel):
    summary_char_limit: int = Field(gt=0)
    topic_char_limit: int = Field(gt=0)
    ner_llm_char_limit: int = Field(gt=0)


@router.get("/processing", response_model=ProcessingSettingsResponse)
async def get_processing_settings(db: AsyncSession = Depends(get_db)):
    return await ProcessingSettingsRepository(db).get()


@router.put("/processing", response_model=ProcessingSettingsResponse)
async def update_processing_settings(
    body: UpdateProcessingSettingsRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await ProcessingSettingsRepository(db).update(
        body.summary_char_limit, body.topic_char_limit, body.ner_llm_char_limit
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

```python
# before (Phase 0 area, right after provider is resolved)
provider = get_llm_provider(classify_llm_engine(model))
```

```python
# after
provider = get_llm_provider(classify_llm_engine(model))

async with self._session_factory() as session:
    processing_settings = await ProcessingSettingsRepository(session).get()
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

Same pattern as above: add the `ProcessingSettingsRepository` import, fetch `processing_settings` once alongside `provider` resolution, and replace:

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

Same Phase-0 fetch pattern as the other two flow controllers — fetch `processing_settings` once, alongside `provider` resolution, reuse for every file in the loop. The `settings` import (from `app.config`) may become unused in this file after this change if `ner_llm_char_limit` was its only usage here — check and remove the import if so.

## config.py — remove the now-redundant setting

**File:** `backend/app/config.py`

Remove `ner_llm_char_limit: int = 6000` — this value now lives exclusively in `processing_settings`.

## No changes needed

- **`ner_llm_engine.py`, `_ner_prompt`, `_topic_prompt`, `_file_prompt`, `_folder_prompt`** — untouched; truncation happens before the prompt is built, not inside these functions
- **`LlmProvider`, `OllamaProvider`, `analysis_engine_registry.py`** — untouched, unrelated to this feature
- **`AnalysisConfiguration` / the Ollama-model-adding feature** — untouched; this is a separate table for a separate kind of setting (see earlier note distinguishing "a handful of singleton values" from "a growable table of rows")
- **Frontend** — not implemented here; the settings screen that calls `GET`/`PUT /api/settings/processing` is a follow-up