# Feature Context — Wiring the archief-detail wireframe (hierarchical + list view)

A static HTML wireframe has been delivered (`document-list.html`, attached separately —
not reproduced here). It is **visual/interaction reference only**: every behavior in it is faked with
in-memory JS state and 5 hardcoded example rows — no real API calls exist anywhere in it. This context
describes what each part of the wireframe needs to become, backed by real endpoints, referencing the
element IDs/classes in the wireframe so the mapping is unambiguous.

Depends on:
- `feature-context-list-view-file-listing.md` (phase 2) — the recursive/paginated `list_files`
  endpoint, already implemented at `GET /api/archives/{archive_id}/files`.
- `fixes-list-files-endpoint.md` — originally 4 items; **fix #1 (missing mime_type sort) is retracted**
  (see "Sorting" below — "documenttype" and "klasse" turned out to be the same field, already
  supported). The remaining 3 (single-value instead of multi-value category filter, missing language
  filter, entity filter not scoped by type) still apply. **These should be fixed before or alongside
  this wiring work** — wiring real checkbox-style filters against the current single-value backend
  params won't work correctly otherwise.
- `feature-context-entity-topic-index-tables.md` (phase 1) — `file_entities`/`file_topics`.
- `feature-context-topic-entity-filtering.md` (phase 3) — describes the autocomplete matching rules
  (archive-scoped, prefix-only, type-required for entities) that the endpoints below must implement.

## Autocomplete endpoints — exist, need a review pass (not a build-from-scratch item)

Entity and topic autocomplete endpoints already exist (confirmed) — this is not a prerequisite gap the
way it was first assumed. Before wiring the frontend against them, review their implementation against
`feature-context-topic-entity-filtering.md`'s design (archive-scoped regardless of current folder,
prefix-only matching, `entity_type` required and part of the query for entity autocomplete, case/accent
normalization, suggestion cap ~10-15), the same way `list_files` was checked against phase 2 and
produced `fixes-list-files-endpoint.md`. Not reviewed yet as part of this context — worth doing before
or alongside this wiring work, since any mismatch (e.g. substring instead of prefix matching, missing
`entity_type` scoping) would affect how the frontend's suggestion dropdown should behave.

No autocomplete endpoint is needed for klasse/taal — those are a small, fixed, already-enumerable set
of values, which is exactly why they're designed as column-header checklists rather than search
inputs. Autocomplete only applies where the candidate set is large/unbounded (entities, topics).

## Tree view (hierarchical) — `#view-tree`

- `.search-input` and `.type-select` currently have no event listeners at all. These should filter the
  already-fetched folder contents (client-side, since a single folder's direct children is a small,
  already-loaded set — no new endpoint needed).
- Everything else in this panel (breadcrumb, folder chips, the table itself) reflects the existing,
  already-built hierarchical browser (`get_folder`, `get_folder_files`) — **the wireframe's breadcrumb
  JS is a hardcoded single-level demo (only handles one folder click, no real nested navigation) and
  should not be ported as-is.** Wire this panel to the real existing folder-browsing logic/endpoints
  already used elsewhere in the app, not to a reimplementation of the demo script.

## List view — `#view-list`

### Fetching and pagination

The table body (`#listTableBody`) is 5 static rows with no fetch logic and no scrolling behavior at
all. Needs to be replaced with:
- An initial call to `GET /api/archives/{archive_id}/files`, scoped by whichever folder is currently
  selected in the tree view (per `feature-context-list-view-file-listing.md` — root selected means no
  `folder_path`, i.e. whole archive).
- Infinite scroll: on nearing the bottom of the table, fetch the next page using `cursor_id`/
  `cursor_value` from the previous response, only while `has_next` is true.
- Virtualized/windowed rendering is not demonstrated in this wireframe (it's a 5-row demo) but is still
  required per the frontend spec, given the up-to-~10k-row ceiling — don't skip it just because the
  wireframe renders all rows directly into the DOM.

### Sorting — `.th-sortable` (`Pad`, `Klasse`, `Taal`, `Datum` in the latest wireframe)

- Currently the arrow only flips character client-side (`↑`/`↓`) with no refetch. Needs to actually
  set `sort_by`/`sort_dir` and refetch from page 1 (cursor reset).
- **"Documenttype" and "klasse" are the same field, not two** — resolved terminology. There is one
  category/`generic_type` sort field (already supported by the backend as `"category"`), not a
  separate `mime_type` sort. The earlier "gap" noted in `fixes-list-files-endpoint.md` around this has
  been retracted — no backend change needed for sortable fields count.
- **`Taal` (language) sorting is not required, despite this wireframe giving it a sort arrow.** The
  backend has no language sort field and doesn't need one — drop the sort arrow from the `Taal` header
  in the next iteration, or if kept for visual consistency with `Klasse`, it must not be wired to an
  actual `sort_by=language` request (there's nothing on the backend for it to do). `Taal` should remain
  **filterable only**, not sortable.
- Only one column should be the active sort at a time — real behavior should make clear which single
  column is currently driving the sort, since the backend only accepts one `sort_by` at a time.

### Metadata filters — `#klasseFilterBtn`/`#klassePopover`, `#taalFilterBtn`/`#taalPopover`

**The wireframe's current behavior must NOT be copied as-is — build the following instead, even
though no new wireframe shows it visually:**

- The wireframe demonstrates single-select (clicking one popover option immediately applies it,
  closes the popover, and overwrites any previous selection for that facet — `badgeState.klasse`/
  `badgeState.taal` each hold one value). **Real behavior needs multi-select**: the popover should be a
  list of checkboxes (one per distinct value, matching the existing options shown), with the user able
  to check multiple values before applying. Selected values within one facet combine with OR (e.g.
  `klasse = tekstbestand OR beeldbestand`), per the standing filter-combination rule.
    - Practically: give the popover explicit **Apply** and **Clear** actions (as in the earlier working
      mockup), rather than applying on the first click — this also avoids refetching the list on every
      single checkbox toggle.
    - `badgeState.klasse`/`badgeState.taal` need to become arrays, and the badge-rendering logic needs to
      render one badge per selected value within a facet (or one combined badge listing all selected
      values, either is fine) — not a single overwritable value.
- Depends on `fixes-list-files-endpoint.md` fix #2 (category/mime_type becoming `list[str]` params) and
  fix #3 (language filter added, also as `list[str]`) — the current backend can't serve a real
  multi-select version of these filters without those.
- Value counts (e.g. "tekstbestand 3") shown in the earlier mockup are not present in this wireframe's
  static popover options — worth adding back if the backend can cheaply compute them (same aggregation
  already used in `get_folder()`'s `mime_types`/`categories` grouping).

### Entity/topic filters — `#entityTypeSelect`, `#entitySearchInput`, `#topicSearchInput`

The latest wireframe correctly adds a real autocomplete-dropdown pattern (type, see suggestions, click
one) — this part matches the intended interaction well. Two things still need to be built beyond what
this wireframe demonstrates, again without needing a new visual iteration:

- **Autocomplete must actually be scoped by the selected type, and isn't yet — even in this demo.**
  `ENTITY_SUGGESTIONS` is a single flat list; changing `#entityTypeSelect` has no effect on what
  suggestions appear. Real behavior: the suggestion request must include the currently-selected type
  (`entity_type`), and results must be scoped to it — selecting "Locatie" and typing "gent" should only
  ever surface location entities, never a person or org that happens to share the text. When wiring
  this for real, the autocomplete call should be re-triggered (or at least re-filterable) whenever the
  type selector changes, not treated as a one-time list.
- **Multi-select is needed here too, and isn't in this wireframe.** `badgeState.persoon` and
  `badgeState.topic` each hold a single value — selecting a second entity or topic overwrites the
  first rather than adding to a list. Real behavior: selecting an entity suggestion should **add** to a
  list of active entity selections (which may span multiple types — e.g. one Persoon and one
  Organisatie active at once), and likewise for topics, each individually removable, all OR'd together
  within their own facet per the standing rule. This is the same underlying fix as the metadata-filter
  point above — badge state generally needs to move from "one value per facet key" to "a list of
  selections per facet."
- `#entityTypeSelect` options are `Persoon`, `Locatie`, `Organisatie`, `Overige` — confirm the
  "Overige"/other option actually corresponds to a real `entity_type` value produced by the NER
  pipeline and accepted by the autocomplete endpoint before wiring it 1:1.
- Type selection is always required before searching (matches the select always having a value, never
  blank) — confirm the existing autocomplete endpoint actually enforces/expects a required
  `entity_type` query param, per the review pass described above.

### Badge state generally — one underlying fix, not four separate ones

Both filter sections above point at the same root issue: `badgeState` (and the klasse/taal popover
logic) are built around "one active value per facet." The actual design needs "a list of active
selections per facet" everywhere — klasse, taal, entity (across types), and topic. Worth treating this
as a single refactor of the badge/filter-state data structure rather than four independent patches, so
klasse/taal/entity/topic all end up using the same underlying pattern for "add a selection," "remove a
selection," and "render all current selections as badges."

### Filter changes must reset pagination

Every filter change (any selection added or removed, in any facet) must reset pagination to page 1
per the cursor design — not shown in the wireframe since it never actually fetches anything.

## Side panel — file click behavior (applies to BOTH views)

**New requirement, not previously scoped:** clicking a file row must show the same content and
analysis results (Overzicht / Samenvatting / NER / Topics tabs) **whether the row was clicked in tree
view or list view.** This should be one shared component/logic path, not two separate implementations
— a file's detail view doesn't depend on which browsing view was used to find it.

- The wireframe's side panel only updates the filename text on row click (`#sideFilename`) — the tabs
  (`Overzicht`, `Samenvatting`, `NER`, `Topics`) are static markup with no data behind them.
- Wire these to the existing per-file endpoints already used elsewhere in the app (same ones the
  current hierarchical/archive-detail view uses) — this is not new backend work, just needs to be
  triggered from list-view row clicks too, using the clicked file's id:
    - **Overzicht** — basic file info (already available from the row data itself, or a details call).
    - **Samenvatting** — existing summary endpoint.
    - **NER** — `get_ner_for_file`.
    - **Topics** — `get_topics_for_file`.
    - Full content (per the earlier "full file text view" work, `GET /api/files/{id}/content`) should
      also be reachable from here if that's exposed in the current hierarchical view's side panel —
      confirm it's included, not just the four tabs shown in this wireframe.
- Practical implication: the list view's row data already includes the file `id` (per the `list_files`
  response) — use that directly rather than re-deriving it from `relative_path`/name.

## Not addressed by this context

- Exact visual/interaction polish (spacing, colors, etc.) — the wireframe's own styling is a starting
  point, not a spec to match pixel-for-pixel.
- The autocomplete endpoints' actual request/response shape — needs to be reviewed against
  `feature-context-topic-entity-filtering.md` (see the section above) so the frontend's suggestion
  dropdown is built against what the endpoints really return, not assumed from the design doc alone.