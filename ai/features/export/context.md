# Use Case

Export everything the database knows about an archive — file/folder metadata, Tika-extracted text, and every completed analysis result (summary, NER, topics) along with which model produced each — as either **CSV** or **JSON**, chosen per export request, written to a folder on the user's own machine.

This is a strict either/or, not "both": each export produces exactly one file (`export.csv` or `export.json`, never both), and the choice is made fresh on every request — not a stored default in `export_settings`.

**Sequencing note:** this ships *before* `bugfix-context-archive-analysis-analyzed-at`, not after — reads from `archive_analysis.date` as it exists today. Since no "redo analysis" capability exists yet, there's currently never more than one `archive_analysis` row per `(archive, type)`, so ordering by `date` is unambiguous in practice right now (see the discussion that led to this sequencing decision). Once the `analyzed_at` migration lands, swap `.date` → `.analyzed_at` in `ExportDataRepository` — that's the only change this feature will need at that point. Flagged explicitly below at the exact spot to change, so it isn't missed or forgotten.

This is a pure database export, not a file-copy operation: original document bytes are never touched, never fetched, never re-exported. "The files" in scope here means the `files` **table** (names, paths, sizes, timestamps) — metadata, not content. Only the (Tika-extracted, capped) text content and the analysis results are text data that gets exported.

Since the backend container has no access to arbitrary host paths (same reason the agent exists for filesystem access generally), the actual disk-write happens through a new, small agent endpoint. The backend does all the real work (querying, joining, building the requested format), then hands the agent one small text payload to write.

This is a synchronous operation, not a background task: without any per-file agent calls or file I/O, even a large archive's export is a handful of joined SQL queries — fast enough that `AnalysisTask`/SSE progress tracking (used for analysis runs, and would have been used for an earlier file-copying design that was scrapped) isn't needed here.

Input mechanism:
- `GET /api/settings/export` / `PUT /api/settings/export` — the export destination folder and content-length cap, a new small settings block (deliberately **not** added to `processing_settings`, which is a separate, already-shipped concern — how much text goes *into* analysis prompts vs. how much appears *in* an export are different questions).
- `POST /api/archives/{archive_id}/export` — body `{"format": "csv" | "json"}`, runs the export in the requested format, returns the final file path on success.

# Business Rules

## What gets exported

One row/node per **file or folder** in the archive (both included, distinguished by `is_directory`):

- From `files`: `relative_path`, `name`, `is_directory`, `extension`, `size_bytes` (files only).
- From `tika_analyses` (files only — folders have no Tika row): `mime_type`, `language`, `word_count`, `author`, and `content` **capped to `export_settings.content_char_limit`** — never the full extracted text. This is the "don't export a 500-page PDF's full text" concern raised directly — cap it, don't filter it out.
- From `generic_types` (files only): `generic_type`.
- Summary: `result` text, plus the model that produced it (joined via `analysis_id` → `archive_analysis.model`). Available for both files and folders (folder summaries already exist — "summary of summaries").
- NER: the four category lists (`persons`, `locations`, `organisations`, `misc`) — **entity names only**, reusing the exact extraction helpers already built for `get_ner_for_file`/`get_ner_for_folder` (pulling `entity` out of each JSONB object, ignoring `count`) — plus the model used. Available for both files and folders (folder-level aggregation already exists).
- Topics: the topic name list — same reuse principle (`get_topics_for_file`/`get_topics_for_folder`'s extraction logic), plus the model used.
- If a type has multiple completed runs, use the **most recent** (ordered by `archive_analysis.date` — the column this project has today. **TODO once `bugfix-context-archive-analysis-analyzed-at` lands**: change this to order by `archive_analysis.analyzed_at` instead, which will exist by then and correctly break ties between same-day runs; `date` cannot). This lookup happens **once per type for the whole archive**, not once per file — one analysis run covers every file/folder at once, so there are at most 3 relevant `archive_analysis` rows (one per type) for the entire export, not one per file. Find those 3 (or fewer) ids first, then join `summary`/`ner`/`topic_detection` against them by `file_id` — don't write this as a per-row correlated "most recent" subquery, it's unnecessary and more expensive than the data actually requires.
- Alongside `model`, also export **when** each type's analysis was run: `summary_analyzed_at`, `ner_analyzed_at`, `topics_analyzed_at`, sourced from the same 3 looked-up `archive_analysis` rows' `date` column (for now — will read from `analyzed_at` once that column exists, same TODO as above). Note the value exported today is date-only (no time-of-day), since that's genuinely all the current `date` column stores — the field will start carrying real time precision automatically once the source column swap happens, with no other change needed on the export side. Like `model`, these are constant across every row/node in a given export for that type (same analysis run produced every result) — not a per-file timestamp.
- If a type has never been run at all, both its `_model` and `_analyzed_at` fields follow the same missing-result rule as everything else (empty cell in CSV, `null` in JSON — see below).
- If a type has **never been run at all** for a given file/folder, its columns/fields still appear in the output schema — never omitted, never a dropped key. In CSV this means an empty cell (not `"N/A"`, not `"null"` as literal text — just nothing between the delimiters). In JSON this means the key is present with a `null` value (e.g. `"summary": null`, not the key missing entirely) — so a consumer parsing the export can always rely on every node having the same shape, whether or not that analysis type was ever run on this archive.
- Tables explicitly **not** exported: `analysis_tasks`, `processing_settings`, `analysis_configuration`, `archive_analysis` (its `model`/`date` are joined in per-result, but the table itself isn't dumped separately) — these are configuration/task-management, not archive content.

## Format selection

- `POST /api/archives/{archive_id}/export` requires a `format` field in the request body: `"csv"` or `"json"`, no other values accepted, no default — the client must choose explicitly every time.
- Only the requested format is generated and written. The unused format's builder is never even called for that request — this isn't "build both, write one," it's "build exactly what was asked for."
- The written filename matches the format (`export.csv` or `export.json`), and only that single file is sent to the agent's `/export/write` endpoint.

## CSV format (when `format: "csv"`)

- Built with Python's `csv` module (`csv.writer` over an `io.StringIO`), never manual string concatenation — this is what correctly handles a cell whose text contains a comma, quote, or newline (summaries and entity names are free text and can contain any of these). `csv.writer` automatically quotes any cell containing the delimiter/quote/newline per RFC 4180 (doubling internal quote characters), so this needs no extra handling beyond just using it for every column — `summary_result`, `content_excerpt`, and the joined NER/topics strings alike.
- One row per file/folder. Multi-value fields (the four NER categories, the topics list) are flattened into a single semicolon-joined string per cell — this is the "special format" concern raised directly: JSONB arrays-of-objects don't belong in a spreadsheet cell, plain delimited text does. Semicolon is used deliberately, not comma: `csv.writer`'s auto-quoting protects the *cell boundary* (comma inside a cell is fine, the whole cell still parses as one field), but does nothing to protect the *meaning* of a list-of-values packed into one cell — if a single location were `"Antwerpen, België"` and NER's location list were joined with commas, it'd be indistinguishable from two separate locations once flattened. Semicolon avoids that ambiguity since it's a genuinely different character from the CSV delimiter.
- **Known, accepted limitation, not solved here**: if a single extracted entity or topic name itself contains a literal semicolon, the same ambiguity resurfaces one level down (indistinguishable from two separate entities once joined). Not worth building a nested-escaping scheme for — semicolons inside short extracted entity/topic names are rare — but documented here rather than silently unhandled.
- Column order: `relative_path, name, is_directory, extension, size_bytes, mime_type, language, word_count, author, content_excerpt, generic_type, summary_result, summary_model, summary_analyzed_at, ner_persons, ner_locations, ner_organisations, ner_misc, ner_model, ner_analyzed_at, topics, topics_model, topics_analyzed_at`.
- Folder rows leave the file-only columns (`extension` through `generic_type`) blank — not `null`, not `"N/A"`, just empty cells. Same treatment applies to any analysis-result column when that type was never run, per the missing-result rule above — an empty cell either way, no special-casing between "not applicable to this row type" and "never analyzed."

## JSON format (when `format: "json"`)

- A nested tree mirroring the folder hierarchy (root → children), each node carrying the same fields as a CSV row, but structured (e.g. `summary: {result, model, analyzed_at}` as a sub-object, not flattened) rather than flattened into single values. `content` is capped the same way as in CSV. Per the missing-result rule above, a node's `summary`/`ner`/`topics` key is always present — its value is `null` when that type was never run, never an omitted key.
- A small header with the archive's own identity (`id`, `name`, `root_path`, `created_at`) precedes the tree.

## Settings

- New singleton table `export_settings` (same "always exactly one row, seeded by migration" convention as `processing_settings`): `default_export_path` (nullable string — starts unset), `content_char_limit` (integer, default e.g. `2000`).
- `default_export_path` starts `NULL` in the migration, but is **auto-computed and persisted on first use** — no manual setup required for export to work. The first time anything needs `default_export_path` and finds it `NULL` (either `GET /api/settings/export` or `POST /api/archives/{archive_id}/export`), the backend asks the agent for a cross-platform default location, saves it to the database, and proceeds using that value. This logic must live in **one shared place**, not duplicated across the two endpoints — see `ExportSettingsService` below.
- The agent computes the default as the OS's standard Documents folder plus an app-specific subfolder (e.g. `modal_exports`), so exports don't get dumped loose among the user's actual documents:
    - **Windows**: the *proper* Documents location, not a hardcoded `%USERPROFILE%\Documents` — Windows lets users redirect Documents elsewhere (OneDrive, Group Policy, a different drive), so a naive path can be wrong. Use the platform's real known-folder resolution.
    - **macOS**: `~/Documents`.
    - **Linux**: `$XDG_DOCUMENTS_DIR` if set, falling back to `~/Documents` — `xdg-user-dirs` isn't guaranteed present on every distro, same caveat class as `zenity` already noted in this project's troubleshooting docs.
    - Recommend the `platformdirs` package (successor to `appdirs`) for this — it has `user_documents_dir` built in and already handles the Windows redirection case correctly, avoiding hand-rolled per-OS branching.
- This computed path is not eagerly created on disk by the default-computation step itself — the folder gets created naturally when `/export/write` first writes into it (that endpoint already creates `export_root` if missing).
- Once auto-computed and saved, `default_export_path` behaves exactly like a manually-set one — the user can still change it later via `PUT /api/settings/export`, same as before.
- The user is still free to override it at any time via the existing `PUT /api/settings/export` (no picker-per-export, per the earlier decision — this remains a single stored default).
- If `POST /api/archives/{archive_id}/export` is called and even the agent can't be reached to compute a default (agent down), surface a clear error — this is now a much rarer failure mode than the old "not configured" case, but still needs handling.

## Writing to disk (via the agent)

- The backend computes the target folder name itself — `{archive.name}_{YYYYMMDD_HHMMSS}` under `default_export_path` — so repeated exports of the same archive don't silently overwrite each other. The agent does not invent naming; it's a thin filesystem executor, consistent with how it's used everywhere else in this app (no business logic in the agent).
- New agent endpoint (implemented in the `agent/` codebase, not the backend — flagged explicitly since this is a different part of the monorepo): `POST /export/write`, body `{export_root: str, files: [{filename: str, content: str}, ...]}`. Creates `export_root` if it doesn't exist, writes each file as UTF-8 text inside it, returns the final path.
- If the agent is unreachable, or reports a write failure (permission denied, disk full, path no longer exists), the backend surfaces that error directly to the caller — never silently reports success when nothing was actually written.
- No export-history/audit table is created here — not asked for, easy to add later if wanted, deliberately left out to keep this contained.

# Component Overview

## Migration — new `export_settings` table

**New file:** `backend/migrations/versions/0015_add_export_settings.py` *(adjust filename/revision to the actual next migration number)*

```python
"""add export_settings table

Revision ID: 0015
Revises: 0014
Create Date: ...
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0015"
down_revision: str | None = "0014"


def upgrade() -> None:
    op.create_table(
        "export_settings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("default_export_path", sa.String(2000), nullable=True),
        sa.Column("content_char_limit", sa.Integer(), nullable=False, server_default="2000"),
    )
    op.execute(
        "INSERT INTO export_settings (id, default_export_path, content_char_limit) "
        "VALUES (gen_random_uuid(), NULL, 2000)"
    )


def downgrade() -> None:
    op.drop_table("export_settings")
```

## Model

**File:** `backend/app/shared/models.py`

```python
class ExportSettings(Base):
    __tablename__ = "export_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    default_export_path: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    content_char_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=2000)
```

## Repository

**New file:** `backend/app/shared/export_settings_repository.py`

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.models import ExportSettings


class ExportSettingsRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get(self) -> ExportSettings:
        result = await self._session.execute(select(ExportSettings).limit(1))
        settings_row = result.scalar_one_or_none()
        if settings_row is None:
            raise RuntimeError("export_settings row missing — expected exactly one row, seeded by migration")
        return settings_row

    async def update(self, default_export_path: str | None, content_char_limit: int) -> ExportSettings:
        settings_row = await self.get()
        settings_row.default_export_path = default_export_path
        settings_row.content_char_limit = content_char_limit
        await self._session.flush()
        return settings_row
```

## ExportSettingsService — shared "get or auto-initialize" logic

**New file:** `backend/app/shared/export_settings_service.py`

This is the one place that knows how to fall back to an agent-computed default — both `GET /api/settings/export` and `ExportArchive` call this instead of `ExportSettingsRepository.get()` directly, so the "compute if missing" logic exists exactly once.

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import get_default_export_path
from app.shared.export_settings_repository import ExportSettingsRepository
from app.shared.models import ExportSettings


async def get_or_initialize_export_settings(session: AsyncSession) -> ExportSettings:
    """Returns the export_settings row, auto-computing and persisting
    default_export_path via the agent if it's still unset. Callers should
    use this instead of ExportSettingsRepository.get() directly whenever
    default_export_path is actually needed for something (not just displayed).
    """
    repo = ExportSettingsRepository(session)
    export_settings = await repo.get()

    if not export_settings.default_export_path:
        computed_default = await get_default_export_path()
        export_settings = await repo.update(computed_default, export_settings.content_char_limit)
        await session.commit()

    return export_settings
```

## Settings router

**New file:** `backend/app/export_settings/router.py`

```python
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.database import get_db
from app.shared.export_settings_repository import ExportSettingsRepository
from app.shared.export_settings_service import get_or_initialize_export_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


class ExportSettingsResponse(BaseModel):
    default_export_path: str | None
    content_char_limit: int


class UpdateExportSettingsRequest(BaseModel):
    default_export_path: str | None = None
    content_char_limit: int = Field(gt=0)


@router.get("/export", response_model=ExportSettingsResponse)
async def get_export_settings(db: AsyncSession = Depends(get_db)):
    # Uses the shared service, not the repository directly — this is what
    # triggers auto-computing the default the first time Settings is opened
    # too, not just the first time an export actually runs.
    return await get_or_initialize_export_settings(db)


@router.put("/export", response_model=ExportSettingsResponse)
async def update_export_settings(body: UpdateExportSettingsRequest, db: AsyncSession = Depends(get_db)):
    result = await ExportSettingsRepository(db).update(body.default_export_path, body.content_char_limit)
    await db.commit()
    return result
```

## Agent client — write export files + compute default path

**New file:** `backend/app/export_archive/agent_export_client.py`

```python
import httpx

from app.config import settings


class AgentExportError(Exception):
    """Raised for any failure talking to the agent's export endpoints —
    covers both writing files and computing the default export path."""


async def write_export_files(export_root: str, files: list[dict]) -> str:
    """files: [{"filename": str, "content": str}, ...]. Returns the final written path."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.agent_url}/export/write",
                json={"export_root": export_root, "files": files},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["path"]
    except httpx.HTTPError as e:
        raise AgentExportError(f"Agent failed to write export: {e}") from e


async def get_default_export_path() -> str:
    """Asks the agent for the OS-appropriate default export folder
    (Documents-based, cross-platform). Pure read, no filesystem side effects
    on the agent side — the folder is created later, on first write.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{settings.agent_url}/export/default-path", timeout=10.0)
            resp.raise_for_status()
            return resp.json()["path"]
    except httpx.HTTPError as e:
        raise AgentExportError(f"Agent failed to compute default export path: {e}") from e
```

**Agent-side (not this repo's backend — flagging for the `agent/` codebase):** two new routes:
- `POST /export/write` — as described above.
- `GET /export/default-path` — returns `{"path": <computed default>}`. Compute via the OS's real Documents-folder resolution plus a `modal_exports` subfolder (recommend the `platformdirs` package's `user_documents_dir` rather than hand-rolled per-OS branching — it already handles Windows' Documents-redirection case correctly). No folder creation here; that happens naturally the first time `/export/write` targets a path under it.

Follow whatever request/response conventions the agent's existing endpoints (`/pick-folder`, `/file-content`) already use rather than inventing a new style.

## Export data gathering + builders

**New file:** `backend/app/export_archive/export_data_repository.py`

```python
# Query shape (currently reads archive_analysis.date — TODO: swap to
# .analyzed_at once bugfix-context-archive-analysis-analyzed-at lands,
# this is the only line in this file that migration will require changing):
#
# 1. For each of the 3 types (SUMMARY, NER, TOPIC_DETECTION), find the
#    single most-recent COMPLETED archive_analysis.id for this archive_id
#    (ORDER BY date DESC LIMIT 1) — at most 3 lookups total, not
#    one per file. Also grab that row's `model` and `date` — these
#    are reused as-is for every row/node of that type in the output.
# 2. Join `summary`/`ner`/`topic_detection` against those (at most 3)
#    analysis_ids, keyed by file_id, to get one result per file/folder.
# 3. Combine with files/tika_analyses/generic_types (reuse FileRepository's
#    existing file/folder listing, NerRepository/TopicDetectionRepository's
#    existing entity/topic extraction logic, and SummaryRepository — don't
#    re-implement queries where equivalents already exist elsewhere in the
#    codebase, same de-duplication principle applied throughout this session).
# 4. If a type has no completed run at all, its 3 lookups return nothing —
#    every row/node gets null/empty for that type's fields (model,
#    analyzed_at, and the result itself), per the missing-result rule above.

class ExportDataRepository:
    def __init__(self, session):
        self._session = session

    async def get_export_rows(self, archive_id, content_char_limit: int) -> list[dict]:
        ...  # returns flat list of dicts, one per file/folder, per the CSV column shape
```

**New file:** `backend/app/export_archive/csv_builder.py`

```python
import csv
import io

_COLUMNS = [
    "relative_path", "name", "is_directory", "extension", "size_bytes",
    "mime_type", "language", "word_count", "author", "content_excerpt",
    "generic_type",
    "summary_result", "summary_model", "summary_analyzed_at",
    "ner_persons", "ner_locations", "ner_organisations", "ner_misc", "ner_model", "ner_analyzed_at",
    "topics", "topics_model", "topics_analyzed_at",
]


def build_export_csv(rows: list[dict]) -> str:
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(_COLUMNS)
    for row in rows:
        writer.writerow([row.get(col, "") for col in _COLUMNS])
    return output.getvalue()
```

**New file:** `backend/app/export_archive/json_builder.py`

```python
import json

def build_export_json(archive_header: dict, rows: list[dict]) -> str:
    # Nest `rows` (flat, with parent_id/relative_path already available from
    # ExportDataRepository) into a tree keyed by folder structure, then:
    return json.dumps({"archive": archive_header, "tree": ...}, ensure_ascii=False, indent=2, default=str)
```

## ExportArchive (flow controller — synchronous, no task tracking)

**New file:** `backend/app/export_archive/export_archive.py`

```python
import uuid
from datetime import datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import AgentExportError, write_export_files
from app.export_archive.csv_builder import build_export_csv
from app.export_archive.export_data_repository import ExportDataRepository
from app.export_archive.json_builder import build_export_json
from app.shared.export_settings_service import get_or_initialize_export_settings

ExportFormat = Literal["csv", "json"]


class ExportArchive:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def execute(self, archive_id: uuid.UUID, archive_name: str, export_format: ExportFormat) -> str:
        # Auto-computes and persists default_export_path via the agent if
        # this is the first export ever run — no "not configured" error path
        # for the common case anymore.
        export_settings = await get_or_initialize_export_settings(self._session)

        rows = await ExportDataRepository(self._session).get_export_rows(
            archive_id, export_settings.content_char_limit
        )

        # Only the requested format is built — the other builder is never called.
        if export_format == "csv":
            filename = "export.csv"
            content = build_export_csv(rows)
        else:
            filename = "export.json"
            content = build_export_json({"id": str(archive_id), "name": archive_name}, rows)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        export_root = f"{export_settings.default_export_path}/{archive_name}_{timestamp}"

        return await write_export_files(export_root, [{"filename": filename, "content": content}])
```

## Router

**New file:** `backend/app/export_archive/router.py`

```python
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.export_archive.agent_export_client import AgentExportError
from app.export_archive.export_archive import ExportArchive
from app.shared.database import get_db
from app.shared.models import Archive

router = APIRouter(prefix="/api/archives", tags=["export"])


class ExportArchiveRequest(BaseModel):
    format: Literal["csv", "json"]


@router.post("/{archive_id}/export")
async def export_archive(archive_id: uuid.UUID, body: ExportArchiveRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Archive).where(Archive.id == archive_id))
    archive = result.scalar_one_or_none()
    if archive is None:
        raise HTTPException(status_code=404, detail="Archive not found")

    try:
        path = await ExportArchive(db).execute(archive_id, archive.name, body.format)
    except AgentExportError as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {"path": path}
```

## Register the routers

**File:** `backend/app/main.py`

```python
from app.export_settings.router import router as export_settings_router
from app.export_archive.router import router as export_archive_router

app.include_router(export_settings_router)
app.include_router(export_archive_router)
```

## No changes needed

- **`AnalysisTask`, `task_tracker`, SSE progress** — not used here at all; this is a synchronous request
- **`get_ner_for_file`/`get_ner_for_folder`/`get_topics_for_file`/`get_topics_for_folder` extraction logic** — reused, not duplicated
- **`processing_settings`** — untouched; export's content cap is a separate, new setting
- **Agent's existing `/file-content`** — untouched, not used by this feature. `/pick-folder` remains available for a user who wants to manually override the auto-computed default via `PUT /api/settings/export`, but is no longer required for export to work at all
- **Frontend** — out of scope, as throughout this conversation