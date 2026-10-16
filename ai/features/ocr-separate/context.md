# Feature Context — OCR as a preprocessing analysis

**Status: ready for implementation.** One detail (how OCR runs are tracked) is left to the
implementation, see "Left to settle during implementation". Frontend requirements are listed near the
end; visual design is done by another agent.

## Goal

OCR can be switched on or off per archive at ingestion (default off, to keep ingestion fast). Make OCR
available again afterwards, as a preprocessing analysis in the analysis menu, so users can run it on an
archive that was ingested without it.

## Background (existing behaviour this builds on)

- `archives.ocr_enabled` (Boolean, default false) is set at ingestion and read once by
  `PerformTikaAnalysis`. It decides whether the `X-Tika-OCRskipOcr: true` header is sent to Tika, via
  tika-python's `requestOptions={'headers': {...}}`. Tested empirically against a real image: OCR'd text
  without the header, none with it.
- Tika's OCR language defaults to English (`eng`). It has not been changed to Dutch yet.
- Extracted text lives in `tika_analyses.content` (one row per file, `UNIQUE(file_id)`), together with
  `word_count`, `language`, `mime_type` and `tika_parser`. Summary, NER, topic detection, text search
  and the full-text view all read from that one text source.
- Analyses (summary, NER, topics) are tracked in `archive_analysis` with a type and status, and have
  progress tracking. Redo works by deleting the existing `archive_analysis` rows for an
  (archive, type) and creating a new one; result tables cascade on `analysis_id`. A STARTED analysis
  blocks a new one of the same type.
- `processing_settings.minimum_text_length` (default 0 = disabled): files with less text are skipped by
  all three analysis types before `total_files` is counted.
- The backend has no access to the host filesystem. The separate agent (runs on the host, knows its own
  OS) does the filesystem work, for example writing exports.
- Background analyses run via bare `asyncio.create_task` with no registry, so a running analysis
  cannot be cancelled. This was parked as a separate feature.
- A vision-model OCR engine through Ollama (the `capabilities` field of `POST /api/show` includes
  `"vision"`), mirroring the spaCy-versus-LLM split in NER, was researched earlier. Parked.

## How OCR differs from the existing analyses

1. **The result is better text, not a new result row.** OCR should update `tika_analyses.content`
   (and `word_count`, `language`), because everything downstream reads that column. There are no
   result rows to cascade-delete, so "redo" means overwrite, not delete-and-recreate.
2. **It is the first analysis that needs the original files again.** Everything so far worked from the
   database alone. This is the main difficulty, see "Source verification".
3. **It must run before the other analyses**, and it changes what they would see.
4. **It only matters for some files**, mostly images and scanned PDFs.

## Separate flow (Decided)

OCR does not go through the existing analysis start. It has its own invocation, its own endpoint(s) and
its own feature folder (monorepo convention). Classes and helpers may be reused (for example progress
tracking), but the entry points are separate.

Why it cannot share the existing path:

- The existing start takes a list of analysis types and runs them as model-based analyses. Redo deletes
  the `archive_analysis` rows for that type and cascades to the result rows. OCR has no result rows to
  delete and overwrites text instead, so that delete-and-recreate logic must never run for OCR.
- OCR needs an interactive step (folder selection and verification) before it can start. The other
  analyses do not.
- OCR has no model. The other analyses always have one.

Consequence: OCR is not part of `analysis_configuration` (the model catalog with one default per
type). It has no row there and does not appear in `GET /api/settings/models`, so its entry in the
analysis menu is not driven by that catalog.

Decided:

- **OCR cannot be combined with other analyses.** A user cannot start OCR together with summary, NER
  or topics. Starting OCR and starting the other analyses are two completely separate actions, each
  with its own start.
- **The agent carries the verified folder.** After a successful verification the agent holds the
  verified root for that archive. No root path is sent from or to the client at start time. Details
  under "Agent changes".
- **Two steps, verify and then start.** The folder picker waits for a person, so it should not sit
  inside one blocking request.

## Source verification

Many archives live on USB drives, and the database stores no drive name. The files may be unreachable,
or a different drive may be mounted at the same path. OCR overwrites stored text, so running it
against the wrong files would silently corrupt the data. Verification therefore comes first:

1. The user starts OCR for an archive.
2. The backend picks a sample of up to 10 files from the OCR candidates (below), using the
   `relative_path` and `size_bytes` already in the database. Fewer than 10 candidates: use all of them.
3. The agent opens a native folder picker on the host. The user selects where the archive root is now.
4. The agent checks each sample file: does `<selected root>/<relative_path>` exist, and does its size
   equal `size_bytes`?
5. All samples match: the agent holds that root, and OCR can start. Otherwise nothing starts and the user gets a report
   (see "Error handling").

Details:

- **Spread the sample.** Do not take the first 10 files by path (they would all sit in one folder, so a
  partial copy could pass). Pick evenly spaced files across the candidates.
- **Candidates, from the database, by type only (decided):** files whose category is `beeldbestand`
  (images), plus PDFs (by mime type). There is no check on the extracted text. A PDF that already has
  text, or was OCR'd before, is simply processed again.
- **The agent joins paths.** The backend sends the root and the relative path separately, never a
  joined path (same rule as the export path fix). Try both Unicode forms of accented filenames (NFC and
  NFD), since a drive passed between macOS and Windows can store them differently.
- **The verified root is held by the agent, only for the duration of the run.** The user is asked again
  next time. Remembering it across runs can be added later.
- **Folder picker (decided):** reuse the mechanism ingestion already uses to let the user choose a
  folder. It has been working in daily use, so the concern about native dialogs failing in a
  background process does not apply.

## Agent changes (confirm against the agent code)

The agent codebase is separate from the FastAPI backend, and its endpoints are backend-facing only (the
frontend never calls them). New needs:

- A way to let the user pick a folder and return the selected path: reuse what ingestion already does.
- A verify call: given a root and a list of `{relative_path, size_bytes}`, report per file whether it
  exists and whether the size matches.
- **Fetching file bytes (decided: reuse the ingestion pattern).** Ingestion already works like this:
  the backend calls the agent (`GET {agent_url}/file-content` with a `path` parameter, 300 second
  timeout), receives the bytes and sends them to Tika. The backend never holds the files itself. OCR
  does the same, one file at a time, with one adjustment: the stored `root_path` may no longer be valid
  (the drive can be mounted elsewhere), so OCR must not rely on a full path built from it. The OCR
  variant takes the `archive_id` and the `relative_path`, and the agent resolves the file under the
  root it holds. It must not accept a free `path`. Check how the full path is built for ingestion
  today, and do not copy that if the backend joins the root and the relative path itself.
- **The agent holds the verified root (decided).** After a successful verify the agent keeps the root
  in memory, keyed by `archive_id`. Later calls from the backend carry only the `archive_id` and a
  `relative_path` (plus the expected size). The agent resolves the file under the root it holds. No
  root path is accepted from the client or the backend at start time, so the file-reading endpoint
  cannot be pointed at another location.
- **Path safety.** Resolve the joined path and check that the real path (symlinks followed) is still
  inside the held root. Reject `..`, absolute paths and anything that escapes the root. Without this
  the endpoint is an arbitrary file reader on the host.
- **Agent restarts lose the held root** (it is in memory, and the agent can be restarted). A run in
  progress can then no longer read files. It must stop with a clear "verification lost, verify again"
  outcome, not record a failure for every remaining file.
- **One verified root per archive.** A new verification for an archive replaces the old one, unless a
  run for that archive is STARTED, in which case it is refused.
- **Verification expires after about 20 seconds (decided).** The start is expected right after a
  successful verification. If OCR has not started by then, something is wrong and the held root is
  cleared. So the flow must not put a confirmation step between "verified" and "start": if the user has
  to read and confirm a result first, 20 seconds can run out. The held root is also cleared when the
  run finishes, fails or is aborted.

## During the run

- Before saving an OCR result, verify that file's size against `size_bytes` again. A missing or
  mismatching file is skipped, with the reason recorded. The existing text is never overwritten for a
  skipped file.
- If several files in a row fail (the drive was probably pulled), stop the run with a clear message
  instead of working through thousands of misses.
- A file that fails in Tika (including the existing 300 second timeout) is recorded and the run
  continues.
- Only candidate files are OCR'd. Do not re-parse plain text files.

## Tika call

- Send the request without the `X-Tika-OCRskipOcr: true` header. The existing
  `TIKA_text_extract(file_content, ocr_enabled=True)` already does this, so the OCR run reuses it:
  select the candidate files, fetch each one from the agent, send it to Tika with OCR enabled, and
  update the stored text.
- **Language:** send `X-Tika-OCRLanguage` with Dutch plus English (for example `nld+eng`) instead of
  the English default. Verify that the Tika image actually has the Dutch Tesseract language data
  installed, otherwise the setting may not take effect.
- **Scanned PDFs (decided):** no explicit PDF OCR setting is needed. Sending the file without the skip
  header is enough.
- After OCR, update `content`, `word_count` and `language`. Language detection runs on the new text.

## Ordering and staleness

- OCR should finish before the other analyses start. The `minimum_text_length` filter must be evaluated
  after OCR: an image that was skipped for having no text can become eligible once it has some.
- OCR is optional. Analyses that already ran on a file are incomplete once its text changes: entities,
  topics and summaries will be missing or based on the old text. Decided: the user is warned before
  starting OCR when the archive already has completed analyses, and nothing is redone automatically.
  Whether a hint to redo them is also shown after OCR completes is left to the design.
- **OCR in the menu (decided):** OCR is always shown in the analysis menu and is always selectable,
  because it can be run again. The `archives.ocr_enabled` flag, stored on the archive, tells whether
  OCR has been done. If it is false, the menu shows a statement that OCR has not been done yet. If it
  is true, OCR is just an option like the others, with no extra statement. Example: an archive
  ingested without OCR shows the statement. After an OCR run completes the flag becomes true, and the
  next time the analysis modal is opened OCR is a plain option.
- **Changing the flag:** the flag is set at ingestion today. When an OCR run started from the menu
  completes, it is set to true as well. A run that fails, is aborted, or is stopped (agent restarted,
  drive gone) leaves it unchanged. Running OCR again leaves it true. A run that completes with some files skipped still sets it to true.
- **Decided:** one boolean is enough. The flag means "an OCR run has completed". Skipped files do not
  keep it false. They are reported in the run's outcome ("completed, N skipped" with reasons), and that
  outcome is where to look if it ever matters which files were missed. A separate last-run record is
  not needed now.
- **Decided:** `ocr_enabled` keeps its name and is not renamed. It now also means "OCR was done", and
  that is accepted.
- A run that ends with skipped files needs a defined outcome, something like "completed, 12 skipped"
  with reasons, not a plain COMPLETED.

## Error handling

Each of these needs an explicit, user-readable outcome:

- The agent is not running or not reachable.
- The user cancels the folder picker.
- The chosen folder is not readable.
- The archive has no OCR candidate files (OCR does not apply).
- Sample mismatch: show how many of the samples matched, up to 3 example filenames that did not, and the
  archive's original `root_path` as a hint when asking for the folder. State that this looks like a
  different archive or the wrong folder.
- The drive disappears during the run.
- A single file fails or times out in Tika.
- OCR started while another OCR run for this archive is already STARTED (blocked, as with other types).
- OCR start requested for an archive that has no verified root held by the agent (refuse, ask for
  verification first).
- The agent was restarted during a run and lost the verified root (stop, ask to verify again).

## Known related issues

- **Cancelling a running analysis does not exist.** OCR on a large archive can run for a long time, so
  this parked feature becomes more important.
- **Progress counts:** an analysis card showed `62 / 145 bestanden` for an archive with 133 files and 18
  folders, so the numbers did not reconcile. Handled separately. It does not block OCR, whose
  progress counts only its own candidate files.

## Engine (Decided)

Tesseract through Tika only, fixed. No model choice for OCR: no model is shown, there is no model
settings control, and no alternative is offered. If another OCR engine is ever wanted, it needs its
own design, because the options are not interchangeable the way models within one analysis type are:
Tesseract (classical OCR inside Tika), a vision model through Ollama (prompted, one call per image,
needs the vision capability) and spaCy for NER (a library, no prompts) differ in how they are invoked,
configured and what they cost. The earlier research on an Ollama vision engine stays parked.

## Frontend requirements (no visual design here; another agent designs it)

- OCR is its own entry at the top of the analysis configuration modal, visibly distinct from the three
  model-based analyses, to signal that it is preprocessing and not just another analysis.
- It shows no model name and has no model settings control.
- It is optional. The user may skip it.
- OCR can never be started together with other analyses. How that is presented (mutually exclusive
  selection in the same modal, or fully separated) is left to the design, the requirement is only that
  the two are separate actions.
- The UI must make clear that running OCR after the other analyses leaves their results incomplete:
  entities, topics and summaries of the OCR'd files will be missing or based on the old text. When the
  archive already has completed analyses, show this before OCR starts. The backend need is which analysis
  types are already completed for the archive. The existing completed-types information used for the
  archive overview probably covers it; confirm.
- OCR is always shown in the menu and is always selectable (it can be run again). When the archive's
  `ocr_enabled` flag is false, show a small statement that OCR has not been done yet. When it is true,
  OCR is a plain option like the others, with no extra statement. The backend needs to expose
  `ocr_enabled` to the UI; check whether the archive overview or list response already includes it.
- OCR has its own start action that calls its own endpoint(s), separate from "Start Analyse".
- Still to be discussed: the folder-selection step and its prompt, the verification result (match or
  mismatch report), the error outcomes, progress display, the "completed with skipped files" outcome,
  and whether a hint to redo the other analyses is shown after OCR completes.

## Left to settle during implementation

One detail is intentionally not decided here:

- **How OCR runs are tracked.** Tika does the OCR itself. Tracking is the app's own bookkeeping around
  it: knowing that a run is in progress (so the progress card works and a second start is blocked),
  knowing when it finished (so `ocr_enabled` can be set), and storing the outcome (files processed,
  files skipped with reasons) so the UI can show it. Reuse the existing mechanism that does this for
  the other analyses where useful. Whether OCR gets an `archive_analysis` row with its own type or
  separate tracking is up to the implementation, as long as the delete-by-type redo logic is never
  applied to OCR.

## Out of scope for now

- Any alternative OCR engine, including the vision-model (Ollama) one.
- Storing a volume ID or label at ingestion, and remembering verified roots.
- Re-pointing an archive to a new permanent location.
- OCR of embedded images inside documents, beyond what Tika does by itself.