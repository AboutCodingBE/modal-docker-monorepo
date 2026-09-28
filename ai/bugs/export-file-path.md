# Use Case

Fix a cross-platform path-joining bug in the already-implemented export feature (`feature-context-export-archive`). `ExportArchive.execute()` currently builds the per-export subfolder path like this:

```python
export_root = f"{export_settings.default_export_path}/{archive_name}_{timestamp}"
```

This runs in the **backend**, which is a Linux Docker container with no idea what OS the agent/host actually is. `default_export_path` may be a Windows-native path (e.g. `C:\Users\chloevg\Documents\modal_exports`), and hardcoding a forward slash onto it produces a mixed-separator string (`C:\Users\chloevg\Documents\modal_exports/archive_20260829_143012`). Windows APIs usually tolerate forward slashes, so this likely "works" in most cases — but it's not correct, and it's exactly the kind of path-handling smell that tends to surface later as a hard-to-reproduce edge case.

Fix: the backend never constructs or concatenates filesystem paths itself. It sends the stored `default_export_path` (opaque, untouched) and the computed subfolder **name** as two separate fields to the agent, which — since it genuinely knows its own OS — joins them correctly via `pathlib.Path(base_path) / subfolder_name`.

# Business Rules

- `ExportArchive.execute()` must not concatenate `default_export_path` with the subfolder name into a single string. It computes the subfolder name only (`{archive_name}_{YYYYMMDD_HHMMSS}`) and passes it to `write_export_files()` as a separate argument from the base path.
- `write_export_files()`'s signature changes from `(export_root: str, files: list[dict])` to `(base_path: str, subfolder_name: str, files: list[dict])`. It sends both fields separately in the request body — never pre-joined.
- The agent's `POST /export/write` endpoint (in the `agent/` codebase — flagging again since it's a different part of the monorepo, not the FastAPI backend) changes its accepted body from `{export_root, files}` to `{base_path, subfolder_name, files}`. It performs the join itself via `pathlib.Path(base_path) / subfolder_name`, creates that directory if it doesn't exist, writes each file as UTF-8 text inside it, and returns `{"path": <the joined, final path as a string>}`.
- No other behavior changes — same file contents, same folder-per-export structure, same response shape from `POST /api/archives/{archive_id}/export`. This is purely a path-construction fix, not a feature change.

# Component Overview

## agent_export_client.py — signature change

**File:** `backend/app/export_archive/agent_export_client.py`

```python
# before
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
```

```python
# after
async def write_export_files(base_path: str, subfolder_name: str, files: list[dict]) -> str:
    """files: [{"filename": str, "content": str}, ...]. Returns the final written path.

    base_path and subfolder_name are sent separately, never pre-joined here —
    the backend doesn't know the host OS, so path joining happens agent-side
    via pathlib.Path(base_path) / subfolder_name.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.agent_url}/export/write",
                json={"base_path": base_path, "subfolder_name": subfolder_name, "files": files},
                timeout=30.0,
            )
            resp.raise_for_status()
            return resp.json()["path"]
    except httpx.HTTPError as e:
        raise AgentExportError(f"Agent failed to write export: {e}") from e
```

## export_archive.py — stop concatenating, pass fields separately

**File:** `backend/app/export_archive/export_archive.py`

```python
# before
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
export_root = f"{export_settings.default_export_path}/{archive_name}_{timestamp}"

return await write_export_files(export_root, [{"filename": filename, "content": content}])
```

```python
# after
subfolder_name = f"{archive_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

return await write_export_files(
    export_settings.default_export_path,
    subfolder_name,
    [{"filename": filename, "content": content}],
)
```

## Agent-side — update the endpoint contract

**Not this repo's backend — the `agent/` codebase.** `POST /export/write` changes:

- **Before:** body `{export_root: str, files: [...]}` — the full target directory pre-joined by the caller.
- **After:** body `{base_path: str, subfolder_name: str, files: [...]}` — join them with `pathlib.Path(base_path) / subfolder_name` inside the agent (correct regardless of whether `base_path` uses `/` or `\`), create that directory if missing, write files, return `{"path": <str(joined_path)>}`.

Follow whatever request/response conventions the agent's existing endpoints already use rather than inventing a new style.

## No changes needed

- `GET /export/default-path` — unaffected, still just computes and returns the base default path as a string
- `export_settings` table, `ExportSettingsService`, `PUT`/`GET /api/settings/export` — unaffected
- CSV/JSON builders, format selection, the missing-result null/empty rules — unaffected
- Frontend — out of scope, as with the rest of this feature