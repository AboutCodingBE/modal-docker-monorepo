# Feature Context — Extend folder-files metadata (KAN-84, KAN-87, KAN-74)

Covers: KAN-84 (Bepaal taal van elk document), KAN-87 (Extraheer Creator), KAN-74 (Date created toevoegen).
KAN-85 (email recipients/sender) is explicitly **out of scope** here — see "Not covered" below.

## Current state

`ArchiveDetailRepository.get_folder_files()` (in `archive_detail/repository.py`), exposed via
`GET /api/archives/{archive_id}/folder/{folder_id}/files`, already outer-joins `TikaAnalysis`:

```python
files_result = await self._session.execute(
    select(File, TikaAnalysis.mime_type, GenericType.generic_type)
    .outerjoin(TikaAnalysis, TikaAnalysis.file_id == File.id)
    .outerjoin(GenericType, GenericType.file_id == File.id)
    .where(
        and_(
            File.archive_id == archive_id,
            File.parent_id == folder_id,
            File.is_directory == False,
        )
    )
    .order_by(File.name)
)

return {
    "folder_id": str(folder.id),
    "folder_name": folder.name,
    "files": [
        {
            "id": str(f.id),
            "name": f.name,
            "relative_path": f.relative_path,
            "extension": f.extension,
            "size_bytes": f.size_bytes,
            "mime_type": mime_type,
            "category": generic_type,
        }
        for f, mime_type, generic_type in files_result.all()
    ],
}
```

`tika_analyses` already has `language`, `author`, `content_created_at` columns — the join is already
in place, the select and the response dict just stop one step short. **No migration needed** for
KAN-84/87/74; this is a pure query + serialization extension.

## Change required

1. Widen the select to pull the three extra columns:

```python
select(
    File,
    TikaAnalysis.mime_type,
    GenericType.generic_type,
    TikaAnalysis.language,
    TikaAnalysis.author,
    TikaAnalysis.content_created_at,
)
```

2. Update the unpacking and the per-file dict:

```python
for f, mime_type, generic_type, language, author, content_created_at in files_result.all()
```

```python
{
    "id": str(f.id),
    "name": f.name,
    "relative_path": f.relative_path,
    "extension": f.extension,
    "size_bytes": f.size_bytes,
    "mime_type": mime_type,
    "category": generic_type,
    "language": language,
    "creator": author,
    "content_created_at": content_created_at.isoformat() if content_created_at else None,
}
```

Naming: response key is `creator` (matches KAN-87 wording and avoids confusion with `Archive`/model
"author" concepts elsewhere), backed by the `author` column — same pattern already used for
`generic_type` column → `category` response key, so this isn't a new convention.

3. No router change needed — `archive_folder_files` in `archive_detail/router.py` just passes through
   whatever the repository returns.

## Addendum — frontend: show these fields in the file table

The "Archief browser" left pane (file table under "BESTANDEN IN DEZE MAP") currently shows 3 columns:
**BESTANDSNAAM**, **CATEGORIE**, **GROOTTE**. There is enough horizontal room in that table to add 3
more columns for the fields this context adds to the API response:

- **TAAL** (`language`)
- **CREATOR** (`creator`)
- **DATUM AANGEMAAKT** (`content_created_at`)

Notes for implementation:
- These values are frequently `NULL` today (see "Known data gap" below) — the table needs a sensible
  empty-state display (e.g. `–` or "Onbekend") rather than showing blank cells or the literal string
  `None`/`null`.
- `content_created_at` should be formatted as a date (not a full ISO timestamp) for display, consistent
  with how `created_at` is already formatted elsewhere (see `get_stats()`'s
  `archive.created_at.date().isoformat()`).
- This is a backend + frontend change together, not two separate passes — since both sides of this are
  small and directly coupled (3 new response fields, 3 new table columns), Claude Code should do the
  repository change, the response shape, and the table column additions in one go rather than as
  separate tickets.

## Known data gap (confirmed, not fixable — no follow-up needed)

These 3 columns are **not reliably populated** — many `tika_analyses` rows have NULL today, and the
endpoint change surfaces whatever is there without fixing extraction itself. This was initially flagged
as possibly needing a follow-up (fallback/enhancement scripts to backfill missing values), but that's
been confirmed closed: the fallback scripts (from the 2 external repos referenced earlier) are
**already wired into the current ingestion pipeline** — they run, and a large share of files still come
back with nothing for these fields even so. This is the actual ceiling on extraction quality for now,
not a gap waiting on unwired code. No further action item here; the frontend null-handling in the
addendum above is the correct (and only) response to this.

## Not covered: KAN-85 (email sender/recipients)

No column exists for this on `tika_analyses` (or anywhere). Sender is single-valued and could follow
the same column pattern as `author`; recipients (To/CC/BCC) are multi-valued per file and don't fit a
plain column the same way — needs a JSONB/array column or a child table. Storage shape is still
undecided pending a look at what Tika actually returns for `.eml`/`.msg` files in this pipeline
(currently unknown/unverified). Separate feature context once that's resolved.

## Related, not in scope here

`get_root_files()` (same file, serves `GET /api/archives/{archive_id}/folder/root/files`) has the
identical shape and the identical gap — joins `TikaAnalysis` for `mime_type` only, doesn't pull
`language`/`author`/`content_created_at` either, and doesn't join `GenericType` at all. Not touched by
this context since it wasn't asked for, but worth extending the same way for consistency — root-level
files would otherwise be the one place in the archive that doesn't show this metadata. Flagging so it
doesn't get forgotten, not blocking this change.

## Files affected

- `app/archive_detail/repository.py` — `get_folder_files()`

## Open questions

- Confirm `creator` vs `author` as the response field name (this doc assumes `creator`, matching the ticket).
- Should `get_root_files()` get the same treatment in this same change, or as a fast-follow? 