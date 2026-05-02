import { Component, input, output, signal, computed } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';

interface AnalysisType {
  type: string;
  label: string;
  description: string;
  icon: string;
}

const ANALYSIS_TYPES: AnalysisType[] = [
  {
    type: 'summary',
    label: 'Samenvatting',
    description: 'AI-gegenereerde samenvattingen per bestand en map.',
    icon: '📝',
  },
];

const MODEL_OPTIONS: Record<string, string[]> = {
  summary: ['gemma3:1b'],
};

@Component({
  selector: 'app-analysis-modal',
  templateUrl: './analysis-modal.html',
  styleUrl: './analysis-modal.css',
})
export class AnalysisModal {
  archive = input.required<Archive>();

  closed = output<void>();
  analysisStarted = output<{ archiveId: string; taskIds: string[] }>();

  readonly types = ANALYSIS_TYPES;
  readonly modelOptions = MODEL_OPTIONS;

  selected = signal<Set<string>>(new Set(['summary']));
  models = signal<Record<string, string>>({ summary: 'gemma3:1b' });
  openPopover = signal<string | null>(null);
  submitting = signal(false);
  error = signal<string | null>(null);

  canStart = computed(() => this.selected().size > 0 && !this.submitting());

  constructor(private archiveService: ArchiveService) {}

  isChecked(type: string): boolean {
    return this.selected().has(type);
  }

  toggle(type: string): void {
    this.selected.update(s => {
      const next = new Set(s);
      next.has(type) ? next.delete(type) : next.add(type);
      return next;
    });
  }

  getModel(type: string): string {
    return this.models()[type] ?? this.modelOptions[type]?.[0] ?? '';
  }

  pickModel(type: string, model: string): void {
    this.models.update(m => ({ ...m, [type]: model }));
    this.openPopover.set(null);
  }

  togglePopover(type: string, event: MouseEvent): void {
    event.stopPropagation();
    this.openPopover.update(v => (v === type ? null : type));
  }

  closePopovers(): void {
    this.openPopover.set(null);
  }

  close(): void {
    if (this.submitting()) return;
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
    }));

    this.archiveService.startAnalysis(this.archive().id, analysis).subscribe({
      next: resp => {
        this.analysisStarted.emit({ archiveId: this.archive().id, taskIds: resp.task_ids });
        this._reset();
        this.closed.emit();
      },
      error: () => {
        this.error.set('Er is een fout opgetreden bij het starten van de analyse.');
        this.submitting.set(false);
      },
    });
  }

  private _reset(): void {
    this.selected.set(new Set(['summary']));
    this.models.set({ summary: 'gemma3:1b' });
    this.openPopover.set(null);
    this.submitting.set(false);
    this.error.set(null);
  }
}
