# Assumptions / Open Items

This context was written from the wireframe (`ai/wireframes/archive-cards-analysis-config.html`) and the confirmed backend response shapes, **without** access to the actual current Angular component files, service files, or existing `Archive`/`AnalysisConfiguration` TypeScript interfaces. Before implementing, reconcile the following against the real codebase and adjust file paths / naming accordingly — the logic and markup structure below should still hold, but the exact file locations and existing conventions (standalone vs. NgModule, signals vs. RxJS-only, existing service names) are guesses:

- Component/file names and paths (`archive-card`, `analysis-configuration-modal`, etc.) are placeholders — use whatever the existing components are actually called.
- Assumes Angular signals (`input()`, `computed()`) are available/idiomatic in this project. If the codebase is still on `@Input()` decorators / plain RxJS, translate accordingly — the derived-state logic (`computed`) maps directly to a getter or a `combineLatest`.
- Assumes a service already exists (or should exist) that calls `GET /api/analysis/configuration` and one that calls `GET /api/archives`. Reuse those instead of the placeholder service calls shown here.
- Assumes the `Archive` TypeScript interface needs a new `completed_analysis_types: string[]` field added, matching the backend field added in the `feature-context-archive-overview-completed-analysis-types` context. If this interface already has a similarly-named field, rename to match instead of duplicating.

# Use Case

Reflect, in the UI, which analysis types have already run for each archive — both on the archive card (badges) and in the analysis-configuration modal (splitting already-done types from selectable ones). All three pieces of UI described below derive from the exact same comparison: `archive.completed_analysis_types` (from `GET /api/archives`) against the full list of available types (from `GET /api/analysis/configuration`). This context treats them as one feature because they share that one piece of derived state — implementing them separately would mean re-deriving the same done/pending split three times.

Concretely, this covers:
1. **Archive card** — render one badge per available analysis type, styled as "done" or "pending" depending on whether that type is in `completed_analysis_types`.
2. **Archive card** — hide the "Analyse" button entirely when every available type is already completed (the "Volledig geanalyseerd" card state in the wireframe has no Analyse button, only Verkennen + delete).
3. **Analysis modal** — when opened for a given archive, show already-completed types as static, non-interactive "Reeds uitgevoerd" chips, and only render the remaining (not yet completed) types as selectable checkboxes. If nothing has completed yet, omit the "Reeds uitgevoerd" section entirely and show all types as checkboxes (this is the "Ingested" / first modal state in the wireframe).

Reference: the wireframe HTML you provided shows all three states precisely — card states `Ingested — geen analyses` / `Gedeeltelijk geanalyseerd` / `Volledig geanalyseerd`, and modal states `Vanuit Ingested — alles beschikbaar` / `Vanuit Gedeeltelijk — alleen resterende`. Match that markup structure and the Dutch copy exactly (class names `analysis-chip done` / `analysis-chip pending`, `done-chip`, `tool-row`, etc.) — it's reproduced in the component templates below.

Backend endpoints this feature consumes (already implemented, no backend changes here):
- `GET /api/archives` — each archive object includes `completed_analysis_types: string[]`, e.g. `["SUMMARY", "NER"]`. Empty array if nothing completed yet.
- `GET /api/analysis/configuration` — returns `[{ type: string, model: string }, ...]`, e.g. `[{"type": "SUMMARY", "model": "gemma3:1b"}, {"type": "NER", "model": "nl_core_news_lg"}, {"type": "TOPIC_DETECTION", "model": "gemma3:1b"}]`. Both endpoints use the same uppercase casing (`SUMMARY`, `NER`, `TOPIC_DETECTION`) — comparisons must not lowercase/uppercase either side, just compare directly.

# Business Rules

- The set of "available types" for an archive is always the full response of `GET /api/analysis/configuration` — every archive is eligible for every configured type, there's no per-archive subset of available types (other than what's already completed).
- A type is "done" for an archive if its `type` string appears in `archive.completed_analysis_types` (exact match, both uppercase, no case conversion needed).
- A type is "pending" for an archive if it's in the configuration list but not in `archive.completed_analysis_types`.
- `allCompleted` for an archive is true when every configured type is done (i.e. `pendingTypes.length === 0`), and configuration is non-empty (don't treat "configuration hasn't loaded yet" as "all completed").
- Card badges must render in the same order as `GET /api/analysis/configuration` returns them, one badge per configured type, regardless of completion state — pending types still show a badge (dashed/greyed style, per wireframe `.analysis-chip.pending`), they're just not "done".
- The "Analyse" button on the card must be completely removed from the DOM (not just disabled) when `allCompleted` is true — matches the wireframe's "Volledig geanalyseerd" card, which has no Analyse button at all, only Verkennen + delete.
- "Verkennen" and the delete (trash) button must always render regardless of analysis state — this feature does not affect them.
- In the modal, "Reeds uitgevoerd" chips are purely informational — no checkbox, not clickable, can't be unchecked/removed. They exist so the user understands why a type isn't offered.
- Only pending types get an interactive `tool-row` with a checkbox in the modal. Every checkbox defaults to **checked** (matches the wireframe — all available tool-rows start pre-selected), and the user can uncheck individual ones before starting.
- If `pendingTypes` is empty when the modal would otherwise open, this is a defensive/edge case that should not normally occur (the triggering "Analyse" button is hidden once `allCompleted` is true, per rule above) — but the modal should not render a broken empty checkbox list if it somehow happens; render nothing in the "Beschikbare analyses" section rather than an empty container with visible whitespace.
- The label, description, and icon shown for each analysis type (in both the card badges and the modal tool-rows) come from a static frontend mapping keyed by the backend's uppercase type string — not from the backend response. This mapping must be centralized in one place and reused by both the card and the modal, not duplicated.
    - `SUMMARY` → label "Samenvatting", icon 📝, description "AI-gegenereerde samenvattingen per bestand en map."
    - `NER` → label "Entiteitsherkenning", icon 🔍, description "Detecteert personen, locaties en organisaties."
    - `TOPIC_DETECTION` → label "Onderwerpdetectie", icon 🏷, description "Identificeert de belangrijkste onderwerpen per bestand."
    - Card badges use only the label (short chip text), not the description. Modal tool-rows use label + description + icon, matching the wireframe.
- The modal's submit action must only ever send the currently-checked pending types to `POST /api/analysis/start` — completed types are never included in the request body, by construction (they're never rendered as checkboxes in the first place). This is a UI-side mirror of the backend's own defensive filtering (see `feature-context-prevent-duplicate-analysis-start`), not a replacement for it.

# Component Overview

## Shared: analysis type metadata + derived-state helper

**New file:** `frontend/src/app/shared/analysis-type.util.ts` *(adjust path to match actual shared/util conventions in the project)*

```typescript
export interface AnalysisTypeConfig {
  type: string;   // e.g. "SUMMARY", "NER", "TOPIC_DETECTION"
  model: string;
}

export interface AnalysisTypeMeta {
  label: string;
  description: string;
  icon: string;
}

export const ANALYSIS_TYPE_META: Record<string, AnalysisTypeMeta> = {
  SUMMARY: {
    label: 'Samenvatting',
    description: 'AI-gegenereerde samenvattingen per bestand en map.',
    icon: '📝',
  },
  NER: {
    label: 'Entiteitsherkenning',
    description: 'Detecteert personen, locaties en organisaties.',
    icon: '🔍',
  },
  TOPIC_DETECTION: {
    label: 'Onderwerpdetectie',
    description: 'Identificeert de belangrijkste onderwerpen per bestand.',
    icon: '🏷',
  },
};

export interface AnalysisSplit {
  done: AnalysisTypeConfig[];
  pending: AnalysisTypeConfig[];
  allCompleted: boolean;
}

/**
 * Splits the full set of configured analysis types into "done" and "pending"
 * for a given archive, based on archive.completed_analysis_types.
 *
 * Both sides use the same uppercase casing already — no normalization needed.
 */
export function splitAnalysisTypes(
  configuration: AnalysisTypeConfig[],
  completedTypes: string[],
): AnalysisSplit {
  const done = configuration.filter((c) => completedTypes.includes(c.type));
  const pending = configuration.filter((c) => !completedTypes.includes(c.type));
  return {
    done,
    pending,
    allCompleted: configuration.length > 0 && pending.length === 0,
  };
}
```

This is a plain utility module (no Angular dependencies), so it can be unit tested directly and imported by both the card and the modal without either depending on the other.

## Archive model — add the new field

Wherever the `Archive` interface currently lives (e.g. `frontend/src/app/models/archive.model.ts`), add:

```typescript
export interface Archive {
  id: string;
  name: string;
  date: string;
  files: number;
  status: string;
  completed_analysis_types: string[]; // NEW — e.g. ["SUMMARY", "NER"]
}
```

## AnalysisConfigurationService — reuse or create

If a service already calls `GET /api/analysis/configuration`, reuse it as-is (it already returns exactly the `AnalysisTypeConfig[]` shape above). If it doesn't exist yet, create one:

```typescript
import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, shareReplay } from 'rxjs';
import { AnalysisTypeConfig } from '../shared/analysis-type.util';

@Injectable({ providedIn: 'root' })
export class AnalysisConfigurationService {
  private readonly configuration$: Observable<AnalysisTypeConfig[]>;

  constructor(private http: HttpClient) {
    // shareReplay(1) so every archive card / the modal share one HTTP call,
    // not one per card.
    this.configuration$ = this.http
      .get<AnalysisTypeConfig[]>('/api/analysis/configuration')
      .pipe(shareReplay(1));
  }

  getConfiguration(): Observable<AnalysisTypeConfig[]> {
    return this.configuration$;
  }
}
```

## Archive card component

**File:** `frontend/src/app/components/archive-card/archive-card.component.ts` *(adjust to actual path/name)*

```typescript
import { Component, computed, inject, input } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Archive } from '../../models/archive.model';
import { AnalysisConfigurationService } from '../../services/analysis-configuration.service';
import { AnalysisTypeConfig, splitAnalysisTypes } from '../../shared/analysis-type.util';

@Component({
  selector: 'app-archive-card',
  templateUrl: './archive-card.component.html',
  styleUrl: './archive-card.component.scss',
})
export class ArchiveCardComponent {
  archive = input.required<Archive>();

  private configService = inject(AnalysisConfigurationService);
  private configuration = toSignal(this.configService.getConfiguration(), { initialValue: [] as AnalysisTypeConfig[] });

  analysisSplit = computed(() =>
    splitAnalysisTypes(this.configuration(), this.archive().completed_analysis_types),
  );

  // Convenience for the template
  configuredTypes = computed(() => this.configuration());
  isDone = (type: string) => this.archive().completed_analysis_types.includes(type);
}
```

**File:** `frontend/src/app/components/archive-card/archive-card.component.html`

Relevant excerpt — badges section and conditional Analyse button (rest of the card, e.g. name/date/files/Verkennen/delete, is unchanged):

```html
<div class="analysis-indicators">
  @for (config of configuredTypes(); track config.type) {
    <span
      class="analysis-chip"
      [class.done]="isDone(config.type)"
      [class.pending]="!isDone(config.type)"
    >
      {{ analysisTypeLabel(config.type) }}
    </span>
  }
</div>

<div class="card-footer">
  <button class="btn-explore" (click)="onExplore()">
    <!-- Verkennen icon/svg, unchanged -->
    Verkennen
  </button>

  @if (!analysisSplit().allCompleted) {
    <button class="btn-analyse-remaining" (click)="onOpenAnalysisModal()">
      <!-- Analyse icon/svg, unchanged -->
      Analyse
    </button>
  }

  <button class="btn-delete" (click)="onDelete()">
    <!-- delete icon/svg, unchanged -->
  </button>
</div>
```

Add an `analysisTypeLabel(type: string)` helper on the component that reads from `ANALYSIS_TYPE_META[type]?.label ?? type` (fallback to the raw type string if a new type is ever added to the backend before the frontend map is updated, rather than rendering blank).

## Analysis configuration modal component

**File:** `frontend/src/app/components/analysis-configuration-modal/analysis-configuration-modal.component.ts` *(adjust to actual path/name — this is likely an existing modal being extended, not a new one; only the parts described below are new)*

```typescript
import { Component, computed, inject, input } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Archive } from '../../models/archive.model';
import { AnalysisConfigurationService } from '../../services/analysis-configuration.service';
import { ANALYSIS_TYPE_META, AnalysisTypeConfig, splitAnalysisTypes } from '../../shared/analysis-type.util';

@Component({
  selector: 'app-analysis-configuration-modal',
  templateUrl: './analysis-configuration-modal.component.html',
  styleUrl: './analysis-configuration-modal.component.scss',
})
export class AnalysisConfigurationModalComponent {
  archive = input.required<Archive>();

  private configService = inject(AnalysisConfigurationService);
  private configuration = toSignal(this.configService.getConfiguration(), { initialValue: [] as AnalysisTypeConfig[] });

  split = computed(() => splitAnalysisTypes(this.configuration(), this.archive().completed_analysis_types));

  // Selected pending types, defaulting to "all checked" whenever the pending
  // list changes (e.g. modal reopened for a different archive).
  selectedTypes = computed(() => new Set(this.split().pending.map((c) => c.type)));

  meta = ANALYSIS_TYPE_META;

  toggle(type: string, checked: boolean): void {
    // implement against whatever local mutable selection state the existing
    // modal already uses for its checkboxes — this is illustrative, not a
    // prescription for exact state management style.
  }

  onStartAnalysis(): void {
    const itemsToStart = this.split().pending.filter((c) => this.selectedTypes().has(c.type));
    // POST { archiveId: this.archive().id, analysis: itemsToStart.map(...) }
    // to /api/analysis/start via the existing analysis-start service call.
  }
}
```

**File:** `frontend/src/app/components/analysis-configuration-modal/analysis-configuration-modal.component.html`

Relevant excerpt:

```html
<div class="modal-frame">
  <div class="modal-header">
    <h3>Analyse Configureren</h3>
  </div>

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
          <div class="model-badge-wrap">
            <div class="model-label-sm">Model</div>
            <span class="model-badge">{{ config.model }}</span>
          </div>
        </div>
      </div>
    }
  </div>

  <div class="modal-footer">
    <button class="btn-ghost" (click)="onCancel()">Annuleren</button>
    <button class="btn-primary-lg" (click)="onStartAnalysis()">
      <!-- start icon/svg, unchanged -->
      Start Analyse
    </button>
  </div>
</div>
```

Note the `@if (split().done.length > 0)` guard around both the "Reeds uitgevoerd" block and the "Beschikbare analyses" label — when nothing is done yet, neither renders, and the modal body goes straight from the header into the full list of tool-rows (matches the wireframe's "Vanuit Ingested" state, which has no done-section or section label at all).

## No changes needed

- **Backend** — both endpoints this feature consumes already exist and return the shapes described above; no backend work in this context
- **`btn-explore` / `btn-delete` behavior** — unaffected by this feature
- **Analysis run/progress UI (SSE progress bars, etc.)** — unaffected; this context is only about pre-run state (what's already done vs. what can be started), not about tracking an in-progress run