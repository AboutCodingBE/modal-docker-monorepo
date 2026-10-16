import { Component, input, output, signal, computed, OnInit } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveCategoryCount, ArchiveService, OcrVerifyResult } from '../../../services/archive.service';
import { ConfigurationService } from '../../../services/configuration.service';

interface AnalysisType {
  type: string;
  label: string;
  description: string;
  icon: string;
}

const TYPE_DISPLAY: Record<string, { label: string; description: string; icon: string }> = {
  summary: {
    label: 'Samenvatting',
    description: 'AI-gegenereerde samenvattingen per bestand en map.',
    icon: '📝',
  },
  ner: {
    label: 'Entiteitsherkenning',
    description: 'Detecteert personen, locaties en organisaties in de tekst.',
    icon: '🔍',
  },
  topic_detection: {
    label: 'Onderwerpdetectie',
    description: 'Identificeert de belangrijkste onderwerpen per bestand.',
    icon: '🏷️',
  },
};

const DEFAULT_DISPLAY = { label: '', description: '', icon: '⚙️' };

/** Sentinel used in both the UI and the API to represent "no category". */
const NONE_SENTINEL = '__none__';

type OcrStep = 'idle' | 'verifying' | 'verified' | 'verify_failed' | 'starting';

@Component({
  selector: 'app-analysis-modal',
  templateUrl: './analysis-modal.html',
  styleUrl: './analysis-modal.css',
})
export class AnalysisModal implements OnInit {
  archive = input.required<Archive>();

  closed = output<void>();
  analysisStarted = output<{ archiveId: string; tasks: { taskId: string; type: string }[] }>();
  ocrStarted = output<{ archiveId: string; taskId: string }>();

  // ── Regular analysis types ───────────────────────────────────────────────
  types = signal<AnalysisType[]>([]);
  modelOptions = signal<Record<string, string[]>>({});
  selected = signal<Set<string>>(new Set());
  models = signal<Record<string, string>>({});

  // ── Category filter ──────────────────────────────────────────────────────
  categories = signal<ArchiveCategoryCount[]>([]);
  /** Per-type set of selected category keys (null → NONE_SENTINEL). */
  categorySelections = signal<Record<string, Set<string>>>({});
  /** The tool type whose settings pane is currently open (null = closed). */
  paneOpen = signal<string | null>(null);

  // ── Shared state ─────────────────────────────────────────────────────────
  submitting = signal(false);
  error = signal<string | null>(null);

  // ── OCR state ────────────────────────────────────────────────────────────
  ocrSelected = signal(false);
  ocrStep = signal<OcrStep>('idle');
  ocrError = signal<string | null>(null);
  ocrVerifyResult = signal<OcrVerifyResult | null>(null);

  // ── Computed ─────────────────────────────────────────────────────────────
  canStart = computed(() => !this.ocrSelected() && this.selected().size > 0 && !this.submitting());
  canVerify = computed(() => this.ocrSelected() && this.ocrStep() === 'idle' && !this.submitting());
  canStartOcr = computed(() => this.ocrSelected() && this.ocrStep() === 'verified' && !this.submitting());
  ocrBusy = computed(() => this.ocrStep() === 'verifying' || this.ocrStep() === 'starting');
  ocrWarning = computed(() => this.ocrSelected() && this.archive().completed_analysis_types.length > 0);

  constructor(private archiveService: ArchiveService, private configService: ConfigurationService) {}

  ngOnInit(): void {
    this.configService.getModels().subscribe({
      next: (grouped) => {
        const completedSet = new Set(this.archive().completed_analysis_types);
        const allTypeKeys = Object.keys(grouped);
        const pendingKeys = allTypeKeys.filter(t => !completedSet.has(t));
        const doneKeys = allTypeKeys.filter(t => completedSet.has(t));

        const analysisTypes: AnalysisType[] = [...doneKeys, ...pendingKeys].map(t => {
          const key = t.toLowerCase();
          return { type: key, ...(TYPE_DISPLAY[key] ?? { ...DEFAULT_DISPLAY, label: t }) };
        });

        const options: Record<string, string[]> = {};
        const defaultModels: Record<string, string> = {};
        for (const t of allTypeKeys) {
          const key = t.toLowerCase();
          const entries = grouped[t];
          options[key] = entries.map(e => e.model);
          const defaultEntry = entries.find(e => e.is_default) ?? entries[0];
          if (defaultEntry) defaultModels[key] = defaultEntry.model;
        }

        this.types.set(analysisTypes);
        this.modelOptions.set(options);
        this.selected.set(new Set(pendingKeys.map(t => t.toLowerCase())));
        this.models.set(defaultModels);
        this._initCategorySelections();
      },
    });

    this.archiveService.getArchiveCategories(this.archive().id).subscribe({
      next: (cats) => {
        this.categories.set(cats);
        this._initCategorySelections();
      },
    });
  }

  // ── Category helpers ──────────────────────────────────────────────────────

  categoryKey(cat: string | null): string {
    return cat ?? NONE_SENTINEL;
  }

  isCategoryChecked(type: string, cat: string | null): boolean {
    return this.categorySelections()[type]?.has(this.categoryKey(cat)) ?? true;
  }

  isAllCategoriesSelected(type: string): boolean {
    const sel = this.categorySelections()[type];
    if (!sel) return true;
    return this.categories().every(c => sel.has(this.categoryKey(c.category)));
  }

  isNarrower(type: string): boolean {
    return this.categories().length > 0 && !this.isAllCategoriesSelected(type);
  }

  selectedCategoryCount(type: string): number {
    return this.categorySelections()[type]?.size ?? this.categories().length;
  }

  toggleCategory(type: string, cat: string | null): void {
    const key = this.categoryKey(cat);
    this.categorySelections.update(all => {
      const current = new Set(all[type] ?? this._allKeys());
      if (current.has(key)) {
        if (current.size <= 1) return all; // last one — block uncheck
        current.delete(key);
      } else {
        current.add(key);
      }
      return { ...all, [type]: current };
    });
  }

  toggleSelectAll(type: string): void {
    const allKeys = this._allKeys();
    const current = this.categorySelections()[type] ?? new Set(allKeys);
    const isAll = allKeys.every(k => current.has(k));
    if (isAll) return; // already all selected — no-op (can't go to empty)
    this.categorySelections.update(all => ({ ...all, [type]: new Set(allKeys) }));
  }

  // ── Pane open/close ───────────────────────────────────────────────────────

  togglePane(type: string, event: MouseEvent): void {
    event.stopPropagation();
    this.paneOpen.update(v => (v === type ? null : type));
  }

  closePane(): void {
    this.paneOpen.set(null);
  }

  // ── Regular analysis type helpers ─────────────────────────────────────────

  isChecked(type: string): boolean {
    return this.selected().has(type);
  }

  toggle(type: string): void {
    if (this.ocrSelected()) {
      this.ocrSelected.set(false);
      this._resetOcrState();
    }
    this.selected.update(s => {
      const next = new Set(s);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }

  getModel(type: string): string {
    return this.models()[type] ?? this.modelOptions()[type]?.[0] ?? '';
  }

  pickModel(type: string, model: string): void {
    this.models.update(m => ({ ...m, [type]: model }));
  }

  // ── OCR helpers ───────────────────────────────────────────────────────────

  toggleOcr(): void {
    if (this.ocrSelected()) {
      this.ocrSelected.set(false);
      this._resetOcrState();
      const pendingKeys = this.types()
        .map(t => t.type)
        .filter(t => !this.archive().completed_analysis_types.includes(t.toUpperCase()));
      this.selected.set(new Set(pendingKeys));
    } else {
      this.ocrSelected.set(true);
      this.selected.set(new Set());
      this.closePane();
    }
  }

  verifyOcr(): void {
    if (!this.canVerify()) return;
    this.ocrStep.set('verifying');
    this.ocrError.set(null);
    this.archiveService.verifyOcrSource(this.archive().id).subscribe({
      next: result => {
        this.ocrVerifyResult.set(result);
        this.ocrStep.set(result.ok ? 'verified' : 'verify_failed');
        if (!result.ok) this.ocrError.set(this._formatVerifyError(result));
      },
      error: err => {
        this.ocrStep.set('verify_failed');
        const detail = err?.error?.detail;
        if (detail === 'agent_timeout') {
          this.ocrError.set('De agent reageerde niet op tijd. Controleer of de agent actief is.');
        } else if (detail === 'no_candidates') {
          this.ocrError.set('Dit archief bevat geen OCR-kandidaatbestanden.');
        } else {
          this.ocrError.set('Kon de agent niet bereiken. Controleer of de agent actief is.');
        }
      },
    });
  }

  retryVerify(): void {
    this.ocrStep.set('idle');
    this.ocrError.set(null);
    this.ocrVerifyResult.set(null);
  }

  submitOcr(): void {
    if (!this.canStartOcr()) return;
    this.ocrStep.set('starting');
    this.ocrError.set(null);
    this.archiveService.startOcr(this.archive().id).subscribe({
      next: resp => {
        this.ocrStarted.emit({ archiveId: this.archive().id, taskId: resp.task_id });
        this._reset();
        this.closed.emit();
      },
      error: err => {
        const detail = err?.error?.detail;
        if (detail === 'ocr_already_running') {
          this.ocrError.set('Er is al een OCR-analyse actief voor dit archief.');
          this.ocrStep.set('verified');
        } else {
          this.ocrError.set('Het starten van OCR is mislukt. Probeer opnieuw te verifiëren.');
          this.ocrStep.set('verify_failed');
        }
      },
    });
  }

  // ── Modal controls ────────────────────────────────────────────────────────

  close(): void {
    if (this.submitting() || this.ocrBusy()) return;
    this._reset();
    this.closed.emit();
  }

  onBackdrop(event: MouseEvent): void {
    if (event.target === event.currentTarget) this.close();
  }

  submit(): void {
    if (!this.canStart()) return;
    this.submitting.set(true);
    this.error.set(null);

    const analysis = [...this.selected()].map(type => ({
      type,
      model: this.getModel(type),
      // Omit categories when all are selected (backend default = all)
      categories: this.isNarrower(type)
        ? [...(this.categorySelections()[type] ?? this._allKeys())]
        : undefined,
    }));

    this.archiveService.startAnalysis(this.archive().id, analysis).subscribe({
      next: resp => {
        const tasks = resp.task_ids.map((taskId, i) => ({ taskId, type: analysis[i].type }));
        this.analysisStarted.emit({ archiveId: this.archive().id, tasks });
        this._reset();
        this.closed.emit();
      },
      error: (err) => {
        const detail = err?.error?.detail ?? '';
        if (detail.startsWith('no_analyzable_files_for_')) {
          const type = detail.replace('no_analyzable_files_for_', '');
          this.error.set(`Geen analyseerbare bestanden voor de geselecteerde categorieën (${type}).`);
        } else {
          this.error.set('Er is een fout opgetreden bij het starten van de analyse.');
        }
        this.submitting.set(false);
      },
    });
  }

  // ── Private helpers ───────────────────────────────────────────────────────

  private _allKeys(): string[] {
    return this.categories().map(c => this.categoryKey(c.category));
  }

  private _initCategorySelections(): void {
    const types = this.types();
    const cats = this.categories();
    if (types.length === 0 || cats.length === 0) return;

    const allKeys = cats.map(c => this.categoryKey(c.category));
    const sel: Record<string, Set<string>> = {};
    for (const t of types) {
      // Preserve existing selection if already set; otherwise default to all
      sel[t.type] = this.categorySelections()[t.type] ?? new Set(allKeys);
    }
    this.categorySelections.set(sel);
  }

  private _formatVerifyError(result: OcrVerifyResult): string {
    if (result.reason === 'cancelled') return 'Mapkeuze geannuleerd.';
    if (result.reason === 'folder_not_readable') return 'De geselecteerde map is niet leesbaar.';
    if (result.mismatches?.length) {
      const examples = result.mismatches.slice(0, 3).join(', ');
      return `Verificatie mislukt: ${result.matched ?? 0} van ${result.total ?? '?'} bestanden gevonden. Niet gevonden: ${examples}.`;
    }
    return 'Verificatie mislukt. Controleer of u de juiste map heeft geselecteerd.';
  }

  private _resetOcrState(): void {
    this.ocrStep.set('idle');
    this.ocrError.set(null);
    this.ocrVerifyResult.set(null);
  }

  private _reset(): void {
    this.ocrSelected.set(false);
    this._resetOcrState();
    this.paneOpen.set(null);
    this.selected.set(new Set(this.types().map(t => t.type)));
    this.models.set(
      Object.fromEntries(this.types().map(t => [t.type, this.modelOptions()[t.type]?.[0] ?? '']))
    );
    this.submitting.set(false);
    this.error.set(null);
    // Reset category selections to all-selected
    const allKeys = this._allKeys();
    const sel: Record<string, Set<string>> = {};
    for (const t of this.types()) sel[t.type] = new Set(allKeys);
    this.categorySelections.set(sel);
  }
}
