# Bugfix — Entity/topic filter is case-sensitive, silently excludes matching files

## Symptom

A file's NER results show entity `"Karl Vermaercke"`. Filtering the list view by that same person
(selected via the entity autocomplete, applied as badge `Persoon: Karl VERMAERCKE`) returns **zero
files**, including the file that visibly has that entity in its own NER panel.

## Root cause

The badge value and the entity as extracted for this specific file differ in casing (`Karl VERMAERCKE`
vs. `Karl Vermaercke`). The applied filter does an exact string match:

```python
entity_subq = (
    select(FileEntity.file_id)
    .where(
        FileEntity.archive_id == archive_id,
        FileEntity.entity_text.in_(entities),
    )
)
```

`.in_(entities)` is case-sensitive. If the same real-world entity was extracted with different
capitalization across different documents (plausible — NER run across many files, some possibly
ALL-CAPS source material), a filter value picked from one document's casing won't match another
document's differently-cased version of the same name, even though a human reading both would
immediately recognize them as the same entity.

**Same pattern likely affects the topic filter** (`FileTopic.topic_label.in_(topics)`) — not confirmed
with a concrete example yet, but it's the identical code shape and should be fixed the same way as a
precaution.

## Fix

Make the filter comparison case-insensitive rather than a literal `=`/`IN`. For Postgres, the simplest
change is comparing on `func.lower(...)` on both sides:

```python
from sqlalchemy import func

if entities:
    lowered_entities = [e.lower() for e in entities]
    entity_subq = (
        select(FileEntity.file_id)
        .where(
            FileEntity.archive_id == archive_id,
            func.lower(FileEntity.entity_text).in_(lowered_entities),
        )
    )
    conditions.append(File.id.in_(entity_subq))
```

Same change for `FileTopic.topic_label`/`topics`. (An expression index on `lower(entity_text)` /
`lower(topic_label)` is worth adding if this is queried often, to avoid a function-based scan — minor,
can be done alongside or slightly after the correctness fix.)

## Also worth checking while in this code: autocomplete suggestions

If `"Karl Vermaercke"` and `"Karl VERMAERCKE"` exist as two distinct rows in `file_entities` (which a
plain `SELECT DISTINCT entity_text` would treat as two different values), the autocomplete dropdown may
currently be offering **both** as separate suggestions for what is really one person — meaning even
after this filter fix, a user picking only one of the two casings would still miss files using the
other casing. Worth a quick check against real data: does autocomplete currently return both
"Karl Vermaercke" and "Karl VERMAERCKE" as separate suggestions? If so, this fix should also make the
suggestion query case-insensitively deduplicated (e.g. `DISTINCT ON (lower(entity_text))`, picking one
casing to display per group) — not just fix the filter's matching.

This is the narrow, immediate fix. See `feature-context-entity-casing-at-write-time.md` for the
separate, larger question of whether this should instead be solved by canonicalizing entity text when
it's first written (phase 1's NER write path), rather than patched at query time everywhere it's read.