# Feature Context — Recursive file listing with cursor pagination ("list view")

Phase 2 of 3 for the hierarchical/list views feature. Source requirement (Dutch, as given):

> Een gebruiker kan bestanden in een archief visualiseren wisselen tussen hierarchische weergave en
> lijstweergave. in de lijstweergave ziet hij alle documenten (ook uit subfolders), met volgende
> functies: sorteren op datum, pad, documenttype, klasse; filteren op documenttype, topic, NE. Deze
> lijst kan worden verkregen voor de inhoud van een specifieke folder (incl. subfolder) of van het
> gehele archief.

## Where this fits in the overall plan

1. **Phase 1 (separate feature, not this one):** `file_entities`/`file_topics` flat index tables,
   populated as a side effect of NER/topic analysis. Independently useful, ships on its own.
2. **Phase 2 (this context):** the recursive, sortable, filterable-by-metadata file listing itself —
   fetch + pagination + frontend rendering. Filtering here is limited to document type/klasse.
3. **Phase 3 (future, depends on 1 and 2):** extend phase 2's filtering to topic/NER, using phase 1's
   index tables as the query backend.

**Dashboard as a third "view"** was considered and explicitly deferred — dashboard is archive-scoped
aggregated content, not another way of looking at folder contents the way hierarchical/list are. Not
part of this or any current phase; the view switcher only toggles hierarchical ⇄ list.

## What "list view" needs to do

Unlike the existing `get_folder`/`get_folder_files` (direct children of one folder only), list view
must return **all files recursively** under a given folder, or under the whole archive — flat, not
nested — with server-side sort and filter.

## Fetching — recursive query

Existing folder endpoints filter by `File.parent_id == folder_id` (direct children only). List view
instead filters by a `relative_path` prefix match:

- Whole archive: `WHERE archive_id = :archive_id`
- Folder + subtree: `WHERE archive_id = :archive_id AND relative_path LIKE :prefix || '%'`

Still outer-joined to `TikaAnalysis` (mime_type, language, author, content_created_at) and
`GenericType` (category), same pattern as `get_folder_files`. Requires an index on `relative_path`
(or a btree that supports prefix search efficiently) to keep the scan cheap — archives up to ~10k
files are the expected ceiling (largest seen so far is ~3k), so this doesn't need to be engineered for
extreme scale, just needs to avoid a full table scan per request.

## Pagination — cursor-based, not offset

Offset pagination degrades at depth and can skip/duplicate rows if data changes mid-scroll (e.g. an
archive still being ingested). Cursor (keyset) pagination is used instead: stable, and stays fast
regardless of how far a user has scrolled.

### Sort field (this phase): `content_created_at`

- Chosen over `analyzed_at` deliberately — `analyzed_at` is uniform across an entire archive (batch
  analysis timestamp), making it useless as a per-file sort key, unlike `content_created_at` which at
  least reflects something file-specific, even if incomplete.
- **Known limitation, accepted as-is:** `content_created_at` is NULL for a large share of files —
  reliable extraction from many document types is a hard, currently-unsolved problem (see the earlier
  "known data gap" work on KAN-84/87/74 — this is the same underlying gap, now surfacing in a new
  place). Not something this phase fixes.
- NULLs sort **last** (`ORDER BY content_created_at DESC NULLS LAST` / equivalent for ascending) —
  open question, needs explicit confirmation: should NULLs go last ("unknown, push to the bottom") or
  first ("unknown, needs attention")? This doc assumes last; flag if that's wrong before building.
- Expected UX consequence, not a bug: a large chunk of any real archive's files will have no date and
  will clump together at one end of the sort with no meaningful order within that clump.

### Cursor shape: composite `(content_created_at, file.id)`

`content_created_at` alone isn't a valid cursor key — it's neither unique (many files can share a
date) nor always present (many are NULL). Pairing it with `file.id` (always unique) as a tiebreaker
gives a stable, gap-free cursor: `WHERE (content_created_at, id) < (:last_date, :last_id)` (direction
flipped for ascending), correctly handling both duplicate dates and runs of NULLs. This mirrors the
same lesson already learned from the `archive_analysis.date → analyzed_at` fix — a sort/comparison key
needs enough resolution to break ties, or "most recent"/pagination breaks in exactly the cases that
matter (lots of same-day or same-null rows).

## Filtering (this phase)

- **Document type / klasse**: via existing `mime_type` (from `TikaAnalysis`) and `generic_type` (from
  `GenericType`) — same fields already shown as columns, just added as `WHERE` filters.
- **Topic / NE filtering**: explicitly out of scope for this phase — deferred to phase 3, pending
  phase 1's index tables.
- **Sort by path/klasse**: also requested in the source spec (`sorteren op ... pad, documenttype,
  klasse`) — straightforward `ORDER BY` on existing columns, no cursor complexity beyond what's
  described above for date (path and type are far more likely to have usable tiebreakers or not need
  one, given typical low duplication, but should still pair with `file.id` for consistency and safety).

## Frontend

- **View switcher**: toggle between hierarchical (existing tree/browser) and list (this feature) —
  no dashboard tab, per the decision above.
- **Infinite scroll**, backed by the paginated cursor fetches described above — not "fetch everything,
  scroll client-side." Each scroll-near-bottom triggers the next page fetch.
- **Virtualized rendering** (windowing): only the currently-visible rows are actually in the DOM,
  recycled as the user scrolls. This is what prevents the browser from choking regardless of how many
  files have been fetched so far — necessary even with pagination, since infinite scroll can still
  accumulate thousands of fetched rows in memory/DOM over a long scroll session.
- Column set: filename, path, type/klasse, size, plus the metadata columns already added in the
  hierarchical view (language, creator, date) — consistent with what's already shown there.
- Filter controls: type/klasse (dropdown or facet, backed by existing category values — small,
  bounded set, no autocomplete needed here unlike the future topic/NER filters).

## Open questions

- NULLs-last vs. NULLs-first for date sort — needs an explicit product decision, not just an
  engineering default.
- Exact page size for cursor fetches (not yet specified — needs a reasonable default, e.g. 50–100).
- Whether this is a new endpoint under `archive_detail` or its own feature folder, matching the
  monorepo's per-feature-folder convention.
- Confirm path/klasse sorting doesn't have its own hidden tie-breaking edge cases before assuming it's
  as simple as it looks (e.g. duplicate filenames across different subfolders sorted by path — should
  be fine since full `relative_path` is used, not just filename, but worth a sanity check).