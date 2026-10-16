# Feature Context — Run analyses on selected file categories

Backend/data layer, plus frontend requirements. Visual design is done by another agent.

## Goal

Today every analysis (summary, NER, topic detection) runs on all files of an archive, except files
under the minimum text length. Let the user restrict each analysis to chosen file categories
(`tekstbestand`, `beeldbestand`, `gegevensbestand`, `andere`, and files without a category), for
example to skip images and data files that would only slow a run down.

## Decisions

- **"File type" means category.** The category is the `generic_type` value shown as "Categorie" in the
  file tables. Not MIME type, not extension.
- **The user chooses in the analysis modal, per run.** Not a global setting, not per archive.
- **One selection per analysis type (summary, NER, topics), except OCR.** Each of the three has its own
  category selection. OCR has no selection: its candidates are fixed (see the OCR context).
- **Default is all categories, all checked.** There is a control to select all.
- **Files without a category are their own option.** It is shown only when the archive has such files.
- **At least one category must be selected** for each analysis type. An empty selection is not allowed.
- **A run replaces the earlier results of that type** (the existing redo behaviour). Files outside the
  selection end up with no result for that type. Running again on other categories replaces the
  earlier results, it does not add to them.
- **The scope of a run is not stored.** Nothing records which categories a run covered. Files outside
  the selection simply have no result, the same as OCR. A user who is not happy with a result runs the
  analysis again. This is accepted, including that the UI and the export cannot say whether a file has
  no result because of the selection or because the analysis failed.
- **Folder and archive results only reflect the analyzed files.** Folder summaries, folder topics and
  folder NER aggregates are built from the files that have results. A folder whose files were all
  outside the selection has no result for that type.

## Backend

**Request.** Each analysis type in the start request carries its own list of selected categories (for
example a `categories` list per analysis item; exact field names follow the existing request shape).
OCR is not part of this request, it has its own flow.

- A request that omits the selection for a type means all categories, so existing clients keep
  working.
- Files without a category need an explicit representation in the request (not an empty string that
  could collide with a real value).
- Validate: an empty list for an analysis type is rejected with a clear error, and so are unknown
  category values.
- Also refuse a run where the selected categories leave no analyzable files at all (nothing passes the
  category filter and the minimum text length), with a clear message instead of an empty run.

**Building the file list.** Apply the category filter where the file list for a run is built, in the
same place the `minimum_text_length` filter is applied. Both filters are applied before `total_files`
is counted, so progress counts only the files that will actually be processed. Category filter first,
then the minimum text length.

**Redo.** Unchanged. Starting a type deletes the earlier `archive_analysis` rows for that
(archive, type) upfront, which cascades to the result rows, and then analyzes the selected files. A
narrower selection therefore removes the results of the files outside it.

**Category list for the modal (fetched per archive, not a fixed list).** The options in the modal are
built from the archive itself: one request when the modal opens returns the categories that exist in
this archive with their number of files (files only, not folders), plus the number of files without a
category when that is more than zero. A category with no files in the archive is not offered. The same
list serves all three analysis types, so it is fetched once, not per tool. The frontend must not
hardcode the four category names. Check what the existing archive stats and folder category
aggregation already return; the folder aggregation is folder-scoped, so an archive-level version
including the "no category" count is probably needed.

## Frontend requirements (no visual design here)

- For each of summary, NER and topics, a category selection in the analysis modal. In the wireframe it
  sits in the settings pane that opens from each tool's gear, below the model choice. OCR has none.
- Each tool keeps its own selection. Opening the pane for another tool must not show or change the
  first tool's selection (in the wireframe the checkboxes are shared between tools, which is only a
  simplification).
- The options come from the fetched category list (see Backend), not from a hardcoded set.
- All categories are checked by default. A control selects all of the listed categories.
- Each category shows its file count. Files without a category appear as their own option, only when
  such files exist.
- **The last remaining selected category cannot be unchecked (decided).** The selection can never be
  empty, so there is no empty state to start from. The select-all control follows the same rule: it can
  never leave the selection empty. Note that the wireframe implements this differently (when nothing
  is left it switches the first checkbox on again, so a different box than the one clicked can change).
  The intended behaviour is to block the uncheck of the last one. The backend still validates and
  rejects an empty selection as a safety net.
- When a selection is narrower than all categories, the tool row shows that in some way even while the
  pane is closed, because the run will replace the earlier results of that type.
- Make clear that running an analysis replaces the earlier results of that type, because a narrower
  selection removes the results of the other categories.

## Interaction with other features

- **Minimum text length:** still applies, after the category filter.
- **OCR:** images only get text after OCR. Analyzing `beeldbestand` before OCR runs on files without
  text. This feature gives users a way to leave those out.
- **Export:** unchanged. It exports whatever results exist.

## Testing

- Default selection (all categories) behaves exactly as before.
- A run on one category only: files in other categories get no result, and progress shows only the
  selected files.
- A second run on a different category replaces the first run's results.
- A selection that includes files without a category, and one that excludes them.
- Empty selection is rejected by the backend, and the UI never allows it (the last selected category
  cannot be unchecked).
- A selection that leaves no analyzable files is refused with a clear message.
- Folder results reflect only the analyzed files.
- Several analysis types in one run, each with a different selection.

## Out of scope

- Storing which categories a run covered.
- Selection by MIME type or extension.
- Saving a default selection per user or archive.
- Adding to earlier results instead of replacing them.