# Feature Context — Topic/entity filtering on the file list

Phase 3 of 3 for the hierarchical/list views feature. Depends on:
- **Phase 1** (`feature-context-entity-topic-index-tables.md`) — `file_entities`/`file_topics` flat
  index tables, must exist and be populated before this phase's queries work.
- **Phase 2** (`feature-context-list-view-file-listing.md`) — the recursive, paginated, sortable file
  listing this phase adds filtering on top of.

## What this adds

Phase 2 already supports filtering by document type/klasse (via `mime_type`/`generic_type`). This
phase adds two more filter sources — entity and topic — with combination rules (below) that apply
uniformly across all filter sources, including the existing metadata-column ones.

## Why not a plain dropdown, and why not the curated archive-level aggregate

- A flat list of all distinct entities/topics in an archive can run into the hundreds (e.g. ~500
  entities across a 3k-file archive) — unusable as a dropdown.
- The existing `get_ner_for_folder`/`get_topics_for_folder` aggregate endpoints were considered as a
  smaller candidate list, but confirmed to return a **curated, capped** set — fine for a
  "Samenvatting"-style overview, not sufficient for filtering, since it can't surface a less-prominent
  entity/topic that still exists in the archive.
- Solution: type-ahead autocomplete backed by phase 1's index tables, not a preloaded list and not the
  curated aggregate.

## Autocomplete — scope and matching

- **Scope: archive-level, not folder-subtree-level.** Autocomplete suggestions are drawn from the
  whole archive regardless of which folder the user is currently browsing when they open the filter.
  This is exactly why `archive_id` was denormalized onto `file_entities`/`file_topics` in phase 1 —
  `WHERE archive_id = :archive_id AND entity_text ILIKE :prefix || '%'` needs no other scoping.
- **Prefix matching only** (`ILIKE 'jan%'`), not substring/contains. Chosen deliberately: prefix is
  efficient against a plain B-tree index, whereas substring matching would need a trigram index for
  similar performance. Substring and semantic matching are explicitly out of scope here — they belong
  to the separate, planned full-text search feature; this is filtering, not search.
- **Case- and accent-insensitive.** Needs a case/accent-normalizing comparison (e.g. comparing against
  a normalized column or expression index) so "jan" also matches "Ján" — exact normalization approach
  (extension like `unaccent`, or a generated/normalized column) to be settled during implementation.
- **Entity autocomplete requires a type first.** Query is always scoped by `entity_type` in addition to
  the text prefix — e.g. `WHERE archive_id = :archive_id AND entity_type = 'PERSON' AND entity_text
  ILIKE 'jan%'`. This narrows the candidate set before text matching even runs, and avoids ambiguous
  matches across types (e.g. "Amsterdam" the city vs. an org literally named "Amsterdam Consulting").
  Composite index needed: `(archive_id, entity_type, entity_text)`, not separate single-column indexes
  — update phase 1's schema note to match once this is confirmed as final.
- **Topics have no type facet** (schema only has `topic_label`) — topic autocomplete is plain prefix
  search, no type step.
- Suggestion result: capped list (~10-15), ordered alphabetically.
- **Selection, not live filtering, drives the actual filter.** The prefix match only powers the
  autocomplete response. Once the user picks a specific suggestion (e.g. "Jan Peeters"), the filter
  applied to the file list is an *exact* match against that value — typing "jan" never causes files
  mentioning "Janus" to appear unless the user explicitly picks "Janus" as a separate, distinct
  selection.

## Filter combination rules

**OR within a facet, AND across facets** — the standard faceted-search convention, applied uniformly
across every filter source (entity, topic, and the metadata-column filters from phase 2):

- Selecting both "Jan Peeters" and "Marie Dubois" as PERSON filters → files mentioning either (or
  both) — not an intersection/co-occurrence search. (True co-occurrence — "documents where both
  appear together" — is a different, more specific feature, not built here.)
- Selecting a PERSON filter *and* a topic filter *and* a category filter → files must satisfy all
  three — each additional facet narrows the result further.

```sql
WHERE archive_id = :archive_id
  AND relative_path LIKE :prefix || '%'                              -- phase 2 scope
  AND mime_type IN (:selected_categories)                            -- metadata column filter
  AND language IN (:selected_languages)                              -- metadata column filter
  AND file_id IN (SELECT file_id FROM file_entities
                  WHERE archive_id = :archive_id AND entity_text IN (:selected_entities))
  AND file_id IN (SELECT file_id FROM file_topics
                  WHERE archive_id = :archive_id AND topic_label IN (:selected_topics))
ORDER BY content_created_at DESC NULLS LAST, id DESC
```

**Implementation note — must use `IN`/semi-join, not `JOIN`.** A plain `JOIN` against
`file_entities`/`file_topics` would produce duplicate rows for a file matching multiple selected
values in the same facet (e.g. a file mentioning both selected entities appears twice) — silently
breaking pagination (duplicate rows across pages, wrong apparent counts). The `IN (SELECT ...)` form is
a membership test and naturally dedupes.

## Pagination interaction

**Any filter change resets pagination to page 1.** A cursor is only valid against the exact query it
was generated for (per phase 2's cursor design) — adding, removing, or changing any filter (entity,
topic, or a metadata-column filter) changes the query, so the listing must restart from the beginning
rather than trying to resume the old cursor against a different result set. Applies uniformly to every
filter source, not just entity/topic.

## UI / interaction design

Deliberately not specified here — covered separately as a UI wireframe. This context covers the query
and data layer only: matching rules, combination logic, and the API surface needed to support whatever
the wireframe specifies.

## Open / to confirm during implementation

- Exact normalization approach for case/accent-insensitive matching (`unaccent` extension vs. a
  generated column vs. application-side normalization before the query).
- Autocomplete endpoint shape: one endpoint with a `kind=entity|topic` parameter, or two separate
  endpoints; exact suggestion cap (this doc assumes ~10-15).
- Whether entity suggestions need to surface their type in the response even when a type was
  pre-selected (not needed if type is always chosen first, per the current design).