# Tag Search — Feature Plan

## Context

Two branches developed in parallel:

- **`main`** gained: `file_entities`/`file_topics` flat index tables, entity/topic autocomplete, document list filtering
- **`dieter/tagsearch`** built: `tag_index` table, `CreateTagIndexForArchive` flow, `TagIndexRepository` with prefix search and AND/OR multi-tag filtering

The goal is to unify these: keep `tag_index` as the single source of truth, remove `file_entities`/`file_topics`, and make all features that used those tables work on `tag_index` instead.

---

## What tag_index provides beyond the document list

| Feature | Document list (main) | Tag index (this branch) |
|---|---|---|
| Prefix/typeahead autocomplete | Yes | Yes (`search()`) |
| Filter files by tag | Yes (OR only) | Yes, AND or OR (`search_by_tags()`) |
| List all available tags without prefix | No | Yes (`get_all_tags()`) — not wired to an endpoint yet, possible future use for visualizations |
| Tag frequency per file | No | Yes (`count` column) |
| Per-analysis traceability | No | Yes (`analysis_id` per row) |

---

## Implementation Plan

### Step 1 — Merge main into `dieter/tagsearch`

Rebase or merge `main` into this branch to pull in:
- `entity_topic_autocomplete/repository.py` and its router
- `list_files_for_archive/repository.py` with entity/topic filtering
- Migrations `0019` through `0021` (`file_entities`, `file_topics`, unaccent indexes)

This will bring in code that still uses `FileEntity`/`FileTopic` — that is intentional, it gets replaced in the steps below.

---

### Step 2 — Adapt `TagIndexRepository.search()` for autocomplete

Add two things currently missing:
- **`unaccent` support**: change plain `ilike` to `func.unaccent(TagIndex.value).ilike(func.concat(func.unaccent(prefix), "%"))` — same pattern as the existing autocomplete
- **`category` filter**: optional parameter so the caller can ask for only "persons", or only topics (`source="topic_detection"`)

---

### Step 3 — Rewrite `entity_topic_autocomplete/repository.py`

Replace the two methods:
- `autocomplete_entities(archive_id, entity_type, prefix)` → calls `TagIndexRepository.search(archive_id, prefix, source="ner", category=entity_type)`
- `autocomplete_topics(archive_id, prefix)` → calls `TagIndexRepository.search(archive_id, prefix, source="topic_detection")`

The router and the API contract stay identical — the frontend sees no change.

---

### Step 4 — Adapt `TagIndexRepository.search_by_tags()` for case-insensitive matching

Change `TagIndex.value.in_(values)` to `func.lower(TagIndex.value).in_([v.lower() for v in values])`. This matches the behaviour the document list filter currently has.

---

### Step 5 — Rewrite entity/topic filtering in `list_files_for_archive/repository.py`

Replace the two subqueries:
- Entity subquery on `FileEntity` → subquery on `tag_index` with `source="ner"`, match on `(category, lower(value))`
- Topic subquery on `FileTopic` → subquery on `tag_index` with `source="topic_detection"`, match on `lower(value)`

The `"type:text"` API format stays — parsing is unchanged, `type` maps to `category`.

---

### Step 6 — Write a new migration (`0023`)

This migration does two things:
1. **Drop** `file_entities` and `file_topics` (and their indexes from `0019`/`0021`)
2. **Add** a `unaccent` functional index on `tag_index.value` to support fast prefix search

Note: the `unaccent` extension itself was already created in `0021`, no need to create it again.

---

### Step 7 — Clean up `shared/models.py`

Remove `FileEntity` and `FileTopic` model classes. Already done on this branch — verify after the merge in Step 1 does not reintroduce them.

---

### Step 8 — Remove the old write paths

After the merge, `ner_repository.py` and `topic_detection_repository.py` from main will write to `file_entities`/`file_topics` again. Remove those writes — the `tag_index` is already populated by `CreateTagIndexForArchive` which is triggered at the end of both flows.

---

## What does NOT change

- The router for autocomplete — same endpoints, same response shape
- The document list API — same query parameters, same response shape
- `create_tag_index_for_archive` — works as-is
- All existing `tag_index` tests — still valid
