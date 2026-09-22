# Fixes needed — `list_files_for_archive` / `ListFilesRepository.list_files()`

Reviewed against the phase 2/3 feature contexts (`feature-context-list-view-file-listing.md`,
`feature-context-topic-entity-filtering.md`). Root-scope handling (`folder_path is None` → no filter)
is correct and doesn't need changes — flagging that explicitly so it isn't "fixed" unnecessarily.

## 1. RETRACTED — "documenttype" and "klasse" are the same field, not two

Originally flagged as a missing `mime_type` sort field, based on reading the source spec's "datum,
pad, documenttype, klasse" as four *distinct* sortable fields. **Resolved: "documenttype" and "klasse"
refer to the same thing — the category/`generic_type` field ("tekstbestand", "beeldbestand", etc.), not
the granular `mime_type` value.** `_VALID_SORT_FIELDS` already includes `"category"` — nothing needs to
be added here. No change needed to this endpoint for this point.

## 2. Metadata filters need to be multi-value, not single-value

Current:

```python
mime_type_filter: str | None
category_filter: str | None
...
if mime_type_filter is not None:
    conditions.append(TikaAnalysis.mime_type == mime_type_filter)
if category_filter is not None:
    conditions.append(GenericType.generic_type == category_filter)
```

The designed UI (column-header checklist, multi-select checkboxes) needs OR-within-facet behavior —
e.g. filter by "tekstbestand" AND "beeldbestand" together, matching either. Current single-value `==`
filters can't express that. Change both to `list[str] | None` with `.in_(...)`, matching the pattern
already used correctly for `entities`/`topics`:

```python
mime_type_filter: list[str] | None
category_filter: list[str] | None
...
if mime_type_filter:
    conditions.append(TikaAnalysis.mime_type.in_(mime_type_filter))
if category_filter:
    conditions.append(GenericType.generic_type.in_(category_filter))
```

Router side: change `mime_type: str | None = Query(...)` and `category: str | None = Query(...)` to
`list[str] = Query(default=[])`, same style already used for `entities`/`topics`.

## 3. No `language` filter

`TikaAnalysis.language` is already selected and returned in the response, and the designed column-
header filter includes Taal alongside Categorie. There's currently no `language_filter` parameter or
condition at all. Add it the same way as fix #2 (multi-value, `.in_(...)`):

```python
language_filter: list[str] | None
...
if language_filter:
    conditions.append(TikaAnalysis.language.in_(language_filter))
```

Plus the corresponding `language: list[str] = Query(default=[])` in the router and pass-through in the
`list_files(...)` call.

## 4. Entity filter isn't scoped by `entity_type`

Current:

```python
entity_subq = (
    select(FileEntity.file_id)
    .where(
        FileEntity.archive_id == archive_id,
        FileEntity.entity_text.in_(entities),
    )
)
```

Only matches on `entity_text`. Per the designed autocomplete flow, the user always selects a type
(PERSON/ORG/LOCATION/etc.) before searching, so the selection they end up filtering on is really a
(type, text) pair, not text alone. If the same text string could ever exist as more than one
`entity_type` (e.g. a place name that also appears as part of an org name), filtering on text alone
would incorrectly match both. Needs either:
- a parallel `entity_types: list[str] | None` param, zipped with `entities` pairwise (only really
  correct if the frontend always sends both lists in lock-step for exact pairs), or
- restructure `entities` to a list of `{type, text}` pairs / a single delimited param, filtered with an
  explicit `and_(FileEntity.entity_type == ..., FileEntity.entity_text == ...)` per selection, OR'd
  together across selections.

Second approach is more robust (doesn't rely on positional list alignment between two separate query
params) — worth deciding the exact request shape before implementing, since it changes the API
contract, not just the internal filter logic.