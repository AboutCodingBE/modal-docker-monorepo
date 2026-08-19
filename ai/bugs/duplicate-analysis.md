# Use Case

Fix duplicate `NER` badges on archive cards and duplicate `Entiteitsherkenning` tool-rows in the analysis-configuration modal, which appear as soon as a type has more than one model configured (e.g. after adding a second NER model via `add_ollama_model`).

Root cause: the frontend still reads from `GET /api/analysis/configuration`, an older endpoint that returns every `analysis_configuration` row **flat and unfiltered**:

```python
return [{"type": c.type, "model": c.model} for c in configs]
```

This was harmless back when there was exactly one row per type, but it was never updated after `feature-context-list-analysis-models` introduced `GET /api/settings/models`, which returns the same underlying data **already grouped by type** specifically so consumers never do their own grouping. The frontend's card-badge loop and modal tool-row loop both iterate the flat array directly — one badge/row per *row*, not per *type* — so two `NER` rows now render as two `NER` badges and two `Entiteitsherkenning` checkboxes.

Fix: delete `GET /api/analysis/configuration` entirely (not deprecate — remove), and repoint both frontend consumers at `GET /api/settings/models`. Keeping both endpoints around risks the exact same "two sources of truth for the same concept" drift that's already caused three separate cleanups this session (`ArchiveAnalysisRepository`, `ollama_client`, LFM2 removal).

# Business Rules

- `GET /api/analysis/configuration` is removed entirely. Nothing else in the backend calls it internally — it exists only to serve the frontend, and `POST /api/analysis/start` does not depend on it (that endpoint just takes whatever `{type, model}` pairs the frontend sends).
- `GET /api/settings/models` becomes the single source of truth for "what models exist per analysis type" everywhere in the frontend. No other endpoint should be introduced or reused for this purpose.
- **Archive card badges**: one badge per *type key* in the grouped response (`SUMMARY`, `NER`, `TOPIC_DETECTION`), not one per model row. A type with 2 models still shows exactly one badge for that type — "does this type have a default configured," not "how many models exist for it."
- **Analysis-configuration modal**: one tool-row per type, same as before, but the model area for each row becomes a `<select>` populated from that type's model array (from the grouped response), rather than a static model name. The `<select>` defaults to whichever entry has `is_default: true` for that type.
- When the user submits the modal ("Start Analyse"), the `model` sent to `POST /api/analysis/start` for each type must be whatever is **currently selected in that type's dropdown** — not a hardcoded default. This is the actual fix for the visible bug: previously every checkbox implicitly meant "use the type's only model," which silently broke the moment a type had more than one.
- This applies retroactively to any type with multiple rows, not just NER — the fix must be generic across all three types, not special-cased for NER just because that's what surfaced the bug.

# Component Overview

## Remove the old endpoint

**File:** wherever `GET /api/analysis/configuration` currently lives (referenced as `analysis/start_router.py` in earlier work — confirm actual path)

```python
# DELETE this route entirely:
@router.get("/configuration")
async def get_configuration(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AnalysisConfiguration))
    configs = result.scalars().all()
    return [{"type": c.type, "model": c.model} for c in configs]
```

`POST /api/analysis/start` in the same file is untouched — only the `GET /configuration` route is removed. If `AnalysisConfiguration`/`select` imports in that file become unused as a result, remove them too.

## Frontend — repoint to the grouped endpoint

*(Same caveat as prior frontend contexts this session: actual component files/paths were never shared, so names/paths below are illustrative — reconcile against the real codebase.)*

Wherever the archive card and the analysis-configuration modal currently fetch from `/api/analysis/configuration`, switch to `/api/settings/models` and adjust the rendering logic:

**Archive card** — badge rendering changes from "one badge per array element" to "one badge per object key":

```typescript
// before: configuration was AnalysisTypeConfig[] — flat array, one badge per element
// after: configuration is Record<string, {id, model, is_default}[]> — one badge per key
const types = Object.keys(modelsByType);
// render one badge per `type` in `types`, using is_default presence/absence
// within modelsByType[type] to decide badge state — not the array length
```

**Analysis-configuration modal** — tool-row's static model badge becomes a dropdown:

```html
<!-- before -->
<span class="model-badge">{{ config.model }}</span>

<!-- after -->
<select class="form-select" [(ngModel)]="selectedModelByType[type]">
  @for (option of modelsByType[type]; track option.id) {
    <option [value]="option.model" [selected]="option.is_default">{{ option.model }}</option>
  }
</select>
```

`selectedModelByType[type]` initializes to the `is_default: true` entry's `model` for each type when the modal opens, and updates as the user changes the dropdown. On submit, build the `POST /api/analysis/start` request body from `selectedModelByType`, not from a static default.

Search the frontend codebase for any remaining reference to `/api/analysis/configuration` (e.g. `grep -rn "analysis/configuration" frontend/src`) to catch any consumer not listed above.

## No changes needed

- **`POST /api/analysis/start`** — untouched; already accepts arbitrary `{type, model}` pairs and already filters out completed/running types (`feature-context-prevent-duplicate-analysis-start`) — that logic is unaffected by which model string arrives, only by which types
- **`GET /api/settings/models`, `add_ollama_model`, `set_default_models`** — untouched; this bugfix consumes them as-is
- **Migrations, `AnalysisConfiguration` model** — untouched; this is a read-path fix, not a data-shape change