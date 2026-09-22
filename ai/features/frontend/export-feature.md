# Assumptions / Open Items

- **Wireframes not directly viewed in this conversation.** They live at `ai/wireframes/export` (two files, per the request: one for the Configuration screen addition, one for the archive card's export action). Read both before implementing — where this document's description differs from what's drawn there, **the wireframe wins** for layout, copy, icon choice, and visual details. Treat this document as "which API calls to wire up, when, and what state they need to handle," not as a visual spec.
- Same caveat as every prior frontend context this session: exact component names, file paths, and whether this codebase uses signals vs. `@Input()`/RxJS are illustrative guesses, not confirmed against the real Angular codebase. Reconcile against whatever actually exists.
- Assumes the existing `AnalysisConfigurationService`-style pattern (a service per settings resource, `shareReplay(1)` where multiple consumers might ask for the same data) is the established convention — reuse it for a new `ExportSettingsService` if that pattern already exists, rather than inventing a different one.

# Use Case

Two frontend additions, both wiring up an already-implemented backend (`feature-context-export-archive`, `bugfix-context-export-path-join`):

1. **Configuration screen** — a new section (alongside the existing "Model downloaden" / "Standaard modellen" / "Verwerkingsinstellingen" sections) to view and change the export destination folder and the export content-length cap.
2. **Archive browser cards** — a new "Export" action, letting the user choose CSV or JSON, triggering the export, and reporting back either the destination folder or a clear error.

# Business Rules

## Configuration screen — export settings section

- On load, call `GET /api/settings/export`. This returns `{default_export_path: string, content_char_limit: number}`. Note: `default_export_path` will never be `null` once this endpoint has been hit at least once anywhere in the app — the backend auto-computes and persists a cross-platform default the first time it's read, so the frontend does not need a "not configured yet" empty state for this field, and should not treat a fresh install specially.
- Display the current `default_export_path` as read-only text (it's a real, already-valid folder path — not something a user should free-type, since typos would silently create a new, wrong folder rather than erroring).
- Provide a way to change it: reuse the agent's existing `/pick-folder` endpoint directly (the same mechanism already used elsewhere in this app for choosing an archive's source folder) — open the native folder picker, take the path it returns, and use that as the new `default_export_path` value.
- Provide a numeric input for `content_char_limit` (must be `> 0` — mirror whatever validation styling the existing "Tekens voor Samenvatting & Topics" / "Tekens voor NER" numeric inputs in this same screen already use, since this is the same kind of field).
- One save action submits both fields together via `PUT /api/settings/export` with body `{default_export_path, content_char_limit}`. There is no reason to split this into two separate saves — they're one settings block.
- After a successful save, update the displayed values from the response (the endpoint returns the saved state) rather than trusting local form state, in case anything server-side normalizes the value.

## Archive card — export action

- New action, alongside the existing Verkennen / Analyse / delete actions on each archive card. Always available regardless of how much (or how little) analysis has been run on that archive — export includes whatever exists and leaves the rest empty/null (per `feature-context-export-archive`'s missing-result rule), so there's no analysis-completeness precondition to check before allowing export.
- The user must choose a format before anything happens — CSV or JSON, mutually exclusive, no default, no "both." This needs some kind of chooser (dropdown, split-button, small menu — see wireframe) rather than a single click, since the backend requires an explicit `format` field with no fallback.
- On format selection, call `POST /api/archives/{archive_id}/export` with body `{"format": "csv"}` or `{"format": "json"}`.
- This is a **synchronous** call — no task/progress polling exists for this feature (deliberately; see `feature-context-export-archive`'s reasoning for why a background task wasn't needed here). Show a loading/disabled state on the action while the request is in flight, since it involves real database queries and could take a moment on a large archive, even though it's not a long-running background job.
- On success (`200`, body `{"path": "<final folder path>"}`): show the user where the export landed — e.g. a toast/notification containing that path. There is no file to download; it's already been written to disk by the agent, so the UI's job is purely to confirm success and say where.
- On failure:
    - `404` — archive not found. Shouldn't normally happen from an existing card, but handle gracefully rather than crash.
    - `502` — the agent was unreachable or failed to write (permission denied, disk full, path no longer exists, etc.). Show the error message from the response body's `detail` field directly — it's already a human-readable explanation from the backend, don't paraphrase or hide it.

# Component Overview

## ExportSettingsService

**New file:** `frontend/src/app/services/export-settings.service.ts`

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ExportSettings {
  default_export_path: string;
  content_char_limit: number;
}

@Injectable({ providedIn: 'root' })
export class ExportSettingsService {
  constructor(private http: HttpClient) {}

  getExportSettings(): Observable<ExportSettings> {
    return this.http.get<ExportSettings>('/api/settings/export');
  }

  updateExportSettings(settings: ExportSettings): Observable<ExportSettings> {
    return this.http.put<ExportSettings>('/api/settings/export', settings);
  }
}
```

## Configuration screen — export settings section

**File:** wherever the Configuration screen's other settings sections live (e.g. `frontend/src/app/pages/configuration/configuration.component.ts` — adjust to the real path)

```typescript
// Illustrative addition to the existing Configuration component
exportSettings: ExportSettings | null = null;

ngOnInit() {
  // ...existing loads for model config / processing settings...
  this.exportSettingsService.getExportSettings().subscribe(settings => {
    this.exportSettings = settings;
  });
}

async onPickExportFolder() {
  // Reuse the exact same agent /pick-folder call already used elsewhere in
  // this app for choosing a folder — do not invent a new mechanism.
  const chosenPath = await this.agentService.pickFolder(); // illustrative — match existing method name/signature
  if (chosenPath && this.exportSettings) {
    this.exportSettings.default_export_path = chosenPath;
  }
}

onSaveExportSettings() {
  if (!this.exportSettings) return;
  this.exportSettingsService.updateExportSettings(this.exportSettings).subscribe(saved => {
    this.exportSettings = saved;
    // show a save-confirmation the same way the other Configuration sections already do
  });
}
```

Template (illustrative — follow the wireframe's exact structure/copy):

```html
<div class="section">
  <div class="section-title">Export instellingen</div>
  <div class="section-desc">Beheer waar exports terechtkomen en hoeveel tekst ze bevatten.</div>

  <div class="form-group">
    <label class="form-label">Exportlocatie</label>
    <div class="form-row">
      <input class="form-input" type="text" [value]="exportSettings?.default_export_path" readonly>
      <button class="btn-primary" (click)="onPickExportFolder()">Map kiezen</button>
    </div>
  </div>

  <div class="setting-row">
    <div class="setting-info">
      <div class="setting-name">Tekens per bestand in export</div>
      <div class="setting-desc">Het maximaal aantal tekens van de geëxtraheerde tekst dat wordt opgenomen in een export.</div>
    </div>
    <input class="form-input-number" type="number" [(ngModel)]="exportSettings!.content_char_limit" min="1">
  </div>

  <div class="section-footer">
    <button class="btn-save" (click)="onSaveExportSettings()">Opslaan</button>
  </div>
</div>
```

## ExportArchiveService

**New file:** `frontend/src/app/services/export-archive.service.ts`

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type ExportFormat = 'csv' | 'json';

export interface ExportResult {
  path: string;
}

@Injectable({ providedIn: 'root' })
export class ExportArchiveService {
  constructor(private http: HttpClient) {}

  exportArchive(archiveId: string, format: ExportFormat): Observable<ExportResult> {
    return this.http.post<ExportResult>(`/api/archives/${archiveId}/export`, { format });
  }
}
```

## Archive card — export action

**File:** the archive card component (e.g. `frontend/src/app/components/archive-card/archive-card.component.ts` — same component this session's earlier badge/button work touched)

```typescript
exporting = false;

onExport(format: ExportFormat) {
  this.exporting = true;
  this.exportArchiveService.exportArchive(this.archive().id, format).subscribe({
    next: (result) => {
      this.exporting = false;
      // show success, including result.path, via whatever toast/notification
      // mechanism this app already uses elsewhere
      this.notificationService.success(`Geëxporteerd naar: ${result.path}`);
    },
    error: (err) => {
      this.exporting = false;
      const message = err?.error?.detail ?? 'Export mislukt.';
      this.notificationService.error(message);
    },
  });
}
```

Template — illustrative placement only, exact chrome (dropdown vs. split-button vs. menu) per the wireframe:

```html
<div class="card-footer">
  <button class="btn-explore" (click)="onExplore()">Verkennen</button>

  @if (!analysisSplit().allCompleted) {
    <button class="btn-analyse-remaining" (click)="onOpenAnalysisModal()">Analyse</button>
  }

  <!-- New: export action. Needs a format chooser, not a single click —
       see wireframe for exact interaction (dropdown/menu/split-button). -->
  <div class="export-action">
    <button class="btn-export" [disabled]="exporting" (click)="toggleExportMenu()">
      {{ exporting ? 'Bezig...' : 'Export' }}
    </button>
    @if (exportMenuOpen) {
      <div class="export-menu">
        <button (click)="onExport('csv')">Exporteer als CSV</button>
        <button (click)="onExport('json')">Exporteer als JSON</button>
      </div>
    }
  </div>

  <button class="btn-delete" (click)="onDelete()"><!-- unchanged --></button>
</div>
```

## No changes needed

- **Backend** — both endpoints this feature consumes (`GET`/`PUT /api/settings/export`, `POST /api/archives/{archive_id}/export`) already exist and are fully implemented
- **Agent `/pick-folder`** — reused as-is; no new agent-side work for this frontend piece (the agent-side `/export/write` and `/export/default-path` endpoints are backend-facing, not called directly by the frontend)
- **Archive card's existing Verkennen/Analyse/delete actions** — unaffected, this only adds a new action alongside them