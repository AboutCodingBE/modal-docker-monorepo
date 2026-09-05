# Assumptions / Open Items

- The actual "Nieuw Archief Toevoegen" modal component wasn't shared in this conversation — same caveat as every prior frontend context this session: component name/file path/state-management style below are illustrative, reconcile against the real codebase. The wireframe at `ai/wireframes/ocr-on-ingest.html` is the source of truth for markup/classes/copy; this document is instructions for wiring it up, not a visual spec.
- Confirmed explicitly: the "Archief Ingesten" button's active/inactive coloring in the wireframe is just illustrative of what the *enabled* state looks like — it is **not** indicating the button should always be enabled. The existing validation (button only enabled once a valid name and folder path are both filled in) must be preserved exactly as it works today. The OCR toggle must have **no effect whatsoever** on that button's enabled/disabled state — it's an independent field, not a validation input.

# Use Case

Add an OCR on/off toggle to the "Nieuw Archief Toevoegen" modal, per the wireframe: a compact inline row ("OCR Analyse" / "Herken tekst in gescande documenten") with a two-option pill toggle (Uit / Aan), defaulting to **Uit (off)** — matching the backend's default (`feature-context-archive-ocr-toggle`, where `ocr_enabled` defaults to `False`). The chosen value is sent as `ocr_enabled` in the existing `POST /api/archives` call when the user clicks "Archief Ingesten".

# Business Rules

- Default state on modal open: **Uit** (off) — both sides (frontend default, backend default) must agree; this isn't a case where the frontend picks its own default independently.
- The pill toggle has exactly two states, `Uit`/`Aan`, mapping to `ocr_enabled: false`/`ocr_enabled: true` respectively — mutually exclusive, matches the wireframe's `data-state`/`.active` pattern (clicking one option deactivates the other).
- `ocr_enabled` is included in the existing `POST /api/archives` request body, alongside `name` and `path` — no new endpoint, no new request, just one more field on the request that already exists.
- The OCR toggle is purely a form input, not a validation gate — it does not participate in whatever logic currently enables/disables "Archief Ingesten". Only `name` and `path` validity control that button, exactly as today.
- Resetting the modal (cancel, or reopening it fresh for a new archive) should reset the OCR toggle back to its default (off), not remember the last-used value from a previous ingestion — same reasoning as the name/path fields presumably already resetting between uses.

# Component Overview

## Modal component — add OCR state and wire it into the existing submit call

**File:** wherever the "Nieuw Archief Toevoegen" modal component lives (e.g. `frontend/src/app/components/create-archive-modal/create-archive-modal.component.ts` — adjust to the real path)

```typescript
// Illustrative addition to the existing modal component
ocrEnabled = false; // default off, matches backend default

onToggleOcr(value: boolean) {
  this.ocrEnabled = value;
}

resetForm() {
  // ...existing name/path reset logic...
  this.ocrEnabled = false;
}

onSubmit() {
  // ...existing name/path validation and disabled-button logic, untouched...
  this.archiveService.createArchive({
    name: this.name,
    path: this.path,
    ocr_enabled: this.ocrEnabled, // NEW field on the existing request
  }).subscribe(/* ...existing success/error handling... */);
}
```

## Template — add the OCR row from the wireframe

Insert between the folder-selection field group and the modal footer, matching the wireframe's structure/classes exactly:

```html
<!-- existing naam / locatie field groups above, unchanged -->

<div class="ocr-row">
  <div class="ocr-text">
    <div class="ocr-label">OCR Analyse</div>
    <div class="ocr-desc">Herken tekst in gescande documenten</div>
  </div>
  <div class="pill-toggle">
    <button
      class="pill-option"
      [class.active]="!ocrEnabled"
      (click)="onToggleOcr(false)"
      type="button"
    >Uit</button>
    <button
      class="pill-option"
      [class.active]="ocrEnabled"
      (click)="onToggleOcr(true)"
      type="button"
    >Aan</button>
  </div>
</div>

<!-- existing modal-footer (Annuleren / Archief Ingesten) below, unchanged —
     "Archief Ingesten"'s [disabled] binding must remain driven only by
     name/path validity, not touched by ocrEnabled at all -->
```

`type="button"` on both pill options matters if this form is a real `<form>` element — without it, clicking a pill button inside a `<form>` could trigger a submit, which is not the intent here (only "Archief Ingesten" should submit).

## Archive creation service — add the field to the existing request type

**File:** wherever the archive-creation HTTP call is already defined (e.g. `frontend/src/app/services/archive.service.ts`)

```typescript
// before
export interface CreateArchiveRequest {
  name: string;
  path: string;
}

// after
export interface CreateArchiveRequest {
  name: string;
  path: string;
  ocr_enabled: boolean;
}
```

No change to the method signature or the HTTP call itself — just the request body's shape gains one field, matching the backend's `CreateArchiveRequest` Pydantic model from `feature-context-archive-ocr-toggle`.

## No changes needed

- **Backend** — `POST /api/archives` already accepts `ocr_enabled` (implemented in `feature-context-archive-ocr-toggle`); this context only wires the frontend up to it
- **"Archief Ingesten" button's enable/disable logic** — untouched, still driven only by name/path validity
- **Folder-picker flow ("Select Folder" button)** — untouched, unrelated to this change