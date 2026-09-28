# Assumptions / Open Items

- **This supersedes the earlier, simpler version of this context** (which avoided touching `archive_analysis` at all and relied on old rows just being superseded). That approach was correct but left a real gap: during the window between a redo starting and finishing, "most recent completed" queries would still report the old (now-deleted-results) run as done. This version fixes that by deleting the old `archive_analysis` row outright, which cascades to wipe its results automatically.
- Sequencing dependency **still applies**: `bugfix-context-archive-analysis-analyzed-at` should be in place. With this delete-based design there's normally only ever one `COMPLETED` row per `(archive, type)` at rest, so the same-day-tiebreak scenario the fix addresses is now much less likely to matter in practice — but it's still correct to have, cheap insurance, not something to un-ship.
- Frontend component files weren't shared in this conversation — same caveat as every prior frontend context: names/paths below are illustrative, reconcile against the real codebase. No wireframe was provided for this one (unlike the OCR toggle); the behavior described comes directly from the conversation, so the *behavior* is authoritative even though the *exact markup* is a guess.

# Use Case

Let a user re-run ("redo") any analysis type for an archive, regardless of whether it has already completed. Selecting a type that has a previous result wipes that previous result entirely (not just superseding it) before the new run starts — a genuinely fresh run, not an additional historical record sitting alongside the old one.

Concretely:
- The "Analyse" button on an archive card is **always visible**, even when every type is already done (reversing the earlier `allCompleted` → hide-the-button rule).
- The done/pending badges on the card remain purely informational — they show the current state (most recent `COMPLETED` result per type, exactly as today) and are **not** interactive themselves; they're not what triggers a redo.
- Opening the analysis-configuration modal now offers **every** type as selectable, whether or not it's already been run — there's no more "Reeds uitgevoerd, not offered" split. Selecting an already-completed type and submitting deletes its previous result and starts fresh.
- All selected items in one request are wiped and recreated **together, upfront**, in the request handler — not staggered as each one's turn comes up during sequential background processing. If a user redoes NER + Topics together, both badges go non-green immediately upon submission, even though the two types then process one after another in the background (matches how `archive_analysis`/`AnalysisTask` rows are already all created upfront today, before `_run_sequential` does anything).

# Business Rules

- `get_blocking_types()` still only blocks on `STARTED` (from the earlier, simpler version of this context) — `COMPLETED`, `FAILED`, and `CANCELLED` are all redo-able. This part is unchanged.
- For every accepted (non-blocked) item in a `POST /api/analysis/start` request, **before** creating the new `archive_analysis` row: delete every existing `archive_analysis` row for that `(archive_id, type)`, regardless of its status. This is safe to do unconditionally at this point — any `STARTED` row for this type would already have caused the item to be skipped by the blocking check, so nothing still-running is ever deleted here.
- Deleting the old `archive_analysis` row(s) must be a real, DB-level `DELETE` statement (SQLAlchemy Core `delete(...)`, not fetching ORM objects and calling `session.delete()` on each) — this is what lets the existing `ON DELETE CASCADE` foreign keys on `summary.analysis_id`, `ner.analysis_id`, and `topic_detection.analysis_id` do the actual result-wiping automatically. No separate `DELETE FROM ner WHERE archive_id = ...` (etc.) is needed — one delete on `archive_analysis` cascades to all three result tables for free.
- This delete-then-create sequence happens **once per item, in the existing upfront loop** in `start_analysis()` — not moved into `_run_sequential`. All selected items' old data is wiped and their new `STARTED` rows created before the background task even begins, exactly matching how row creation already works today for a first-time run.
- No changes to `CreateSummariesForArchive`/`CreateNerForArchive`/`CreateTopicDetectionForArchive` — they already do the right thing given a fresh `analysis_id` with no existing rows against it (per the earlier version of this context).
- The fetch endpoints (`get_ner_for_file`/`folder`, `get_topics_for_file`/`folder`) and export need **no changes** — if anything, this design makes their existing "most recent `COMPLETED`" query safer than before, since there's normally only one `COMPLETED` row per `(archive, type)` to find at any settled moment, rather than potentially several historical ones.
- Card badges (`feature-context-archive-overview-completed-analysis-types`) need no backend changes — the query already reflects whatever `archive_analysis` rows currently exist, and now there's simply one fewer historical row to filter past.

# Component Overview

## ArchiveAnalysisRepository — add delete_existing()

**File:** `backend/app/shared/archive_analysis_repository.py`

```python
from sqlalchemy import delete
# ...existing imports...

class ArchiveAnalysisRepository:
    # ...existing methods (create, update_status, get_blocking_types) unchanged...

    async def delete_existing(self, archive_id: uuid.UUID, analysis_type: str) -> None:
        """Deletes all archive_analysis rows for this (archive_id, type),
        regardless of status. ON DELETE CASCADE on summary/ner/topic_detection's
        analysis_id automatically wipes their rows too — no separate deletes
        needed. Caller must ensure no STARTED row exists for this type first
        (already guaranteed by the blocking_types check in start_analysis).
        """
        await self._session.execute(
            delete(ArchiveAnalysis).where(
                ArchiveAnalysis.archive_id == archive_id,
                ArchiveAnalysis.type == analysis_type,
            )
        )
```

## start_analysis — wipe before create

**File:** `backend/app/analysis/start_router.py` *(confirm actual path)*

```python
# before (inside the existing loop)
for item in body.analysis:
    normalized_type = item.type.upper()

    if normalized_type in blocking_types:
        _logger.warning(
            f"Skipped analysis type '{item.type}' for archive {archive_id}: "
            f"already completed or currently running."
        )
        continue

    archive_analysis = await analysis_repo.create(archive_id, item.type, item.model)
    task = await task_tracker.create_task(db, archive_id, total_files=0)
    await db.flush()
    jobs.append((archive_id, archive_analysis.id, task.id, item.type, item.model))

    blocking_types.add(normalized_type)
```

```python
# after
for item in body.analysis:
    normalized_type = item.type.upper()

    if normalized_type in blocking_types:
        _logger.warning(
            f"Skipped analysis type '{item.type}' for archive {archive_id}: "
            f"already completed or currently running."
        )
        continue

    # Redo: wipe any previous run(s) of this type for this archive before
    # creating the new one. Cascades to summary/ner/topic_detection automatically.
    await analysis_repo.delete_existing(archive_id, normalized_type)

    archive_analysis = await analysis_repo.create(archive_id, item.type, item.model)
    task = await task_tracker.create_task(db, archive_id, total_files=0)
    await db.flush()
    jobs.append((archive_id, archive_analysis.id, task.id, item.type, item.model))

    blocking_types.add(normalized_type)
```

Only the one new line (`delete_existing(...)`) — everything else in this loop is unchanged.

## Frontend — archive card: always show the Analyse button

**File:** the archive card component touched by `feature-context-reflect-analysis-completion-state` and `bugfix-context-duplicate-analysis-type-badges`

```html
<!-- before -->
@if (!analysisSplit().allCompleted) {
  <button class="btn-analyse-remaining" (click)="onOpenAnalysisModal()">
    Analyse
  </button>
}

<!-- after -->
<button class="btn-analyse-remaining" (click)="onOpenAnalysisModal()">
  Analyse
</button>
```

The `allCompleted` computation itself can stay (it may still be used elsewhere, e.g. for other display logic) — this only removes the `@if` guard hiding the button. Badges rendering (`analysisSplit()`'s `done`/`pending` split, used for the chip styling) is otherwise unaffected — badges keep showing state exactly as today, purely informational, not click targets.

## Frontend — analysis-configuration modal: every type is selectable

**File:** the modal component touched by `bugfix-context-duplicate-analysis-type-badges`

The modal currently renders completed types as a static, non-interactive "Reeds uitgevoerd" chip section, and only offers *pending* types as checkboxes. That split goes away — every type, done or not, is now offered as a normal selectable tool-row:

```html
<!-- before -->
@if (split().done.length > 0) {
  <div class="done-section">
    <div class="done-label">Reeds uitgevoerd</div>
    <div class="done-chips">
      @for (config of split().done; track config.type) {
        <span class="done-chip">{{ meta[config.type]?.label ?? config.type }}</span>
      }
    </div>
  </div>
  <div class="modal-section-label">Beschikbare analyses</div>
}

<div class="modal-body">
  @for (config of split().pending; track config.type) {
    <div class="tool-row"> ... </div>
  }
</div>
```

Default checkbox state on open: **pending types start checked, already-completed types start unchecked** — same rule as before this change (`pending` types defaulted to checked), just now applied while *also* rendering completed types as checkboxes rather than omitting them. Nothing else about the visual treatment of a completed type is special-cased for now (no "last ran on X" hint, no distinct styling) — flagged as a possible future improvement, not built here.

```html
<!-- after -->
<div class="modal-body">
  @for (config of allTypes(); track config.type) {
    <div class="tool-row">
      <input
        type="checkbox"
        class="tool-checkbox"
        [checked]="selectedTypes().has(config.type)"
        (change)="toggle(config.type, $any($event.target).checked)"
      >
      <div class="tool-icon">{{ meta[config.type]?.icon ?? '' }}</div>
      <div class="tool-info">
        <div class="tool-name">{{ meta[config.type]?.label ?? config.type }}</div>
        <div class="tool-desc">{{ meta[config.type]?.description ?? '' }}</div>
      </div>
      <div class="tool-model-area">
        <select class="form-select" [(ngModel)]="selectedModelByType[config.type]">
          @for (option of modelsByType[config.type]; track option.id) {
            <option [value]="option.model" [selected]="option.is_default">{{ option.model }}</option>
          }
        </select>
      </div>
    </div>
  }
</div>
```

```typescript
// selectedTypes' initialization is unchanged from before this feature —
// it already only included pending (not-yet-completed) types by default.
// What changes is that completed types are now also rendered as rows
// (via allTypes()), just starting outside this set, i.e. unchecked.
selectedTypes = computed(() => new Set(this.split().pending.map((c) => c.type)));
allTypes = computed(() => [...this.split().done, ...this.split().pending]);
```

Whether the modal should still visually hint "this one already ran, on this date, with this model" near a completed type's row is left out for now — noted as a possible future improvement, not a requirement here.

`onSubmit()`/`onStartAnalysis()` logic itself needs no change — it already just sends whatever's currently checked to `POST /api/analysis/start`; the backend now happily accepts a completed type in that list instead of silently dropping it.

## No changes needed

- **`CreateSummariesForArchive`, `CreateNerForArchive`, `CreateTopicDetectionForArchive`** — unaffected, as established
- **`get_ner_for_file`/`folder`, `get_topics_for_file`/`folder`, export** — unaffected, arguably simpler in practice now
- **`feature-context-archive-overview-completed-analysis-types`** — unaffected
- **`AnalysisTask`/`task_tracker`** — unaffected; still append-only, never touched by this change