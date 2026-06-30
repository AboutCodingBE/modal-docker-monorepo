import { Component, input, output, signal, computed, OnInit } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveService, AnalysisConfigEntry } from '../../../services/archive.service';

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

@Component({
  selector: 'app-analysis-modal',
  templateUrl: './analysis-modal.html',
  styleUrl: './analysis-modal.css',
})
export class AnalysisModal implements OnInit {
  archive = input.required<Archive>();

  closed = output<void>();
  analysisStarted = output<{ archiveId: string; tasks: { taskId: string; type: string }[] }>();

  types = signal<AnalysisType[]>([]);
  modelOptions = signal<Record<string, string[]>>({});

  selected = signal<Set<string>>(new Set());
  models = signal<Record<string, string>>({});
  openPopover = signal<string | null>(null);
  submitting = signal(false);
  error = signal<string | null>(null);

  canStart = computed(() => this.selected().size > 0 && !this.submitting());

  constructor(private archiveService: ArchiveService) {}

  ngOnInit(): void {
    this.archiveService.getAnalysisConfiguration().subscribe({
      next: (configs: AnalysisConfigEntry[]) => {
        const analysisTypes: AnalysisType[] = configs.map(c => ({
          type: c.type.toLowerCase(),
          ...(TYPE_DISPLAY[c.type.toLowerCase()] ?? { ...DEFAULT_DISPLAY, label: c.type }),
        }));

        const options: Record<string, string[]> = {};
        const defaultModels: Record<string, string> = {};
        for (const c of configs) {
          const key = c.type.toLowerCase();
          options[key] = [c.model];
          defaultModels[key] = c.model;
        }

        this.types.set(analysisTypes);
        this.modelOptions.set(options);
        this.selected.set(new Set(analysisTypes.map(t => t.type)));
        this.models.set(defaultModels);
      },
    });
  }

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
    return this.models()[type] ?? this.modelOptions()[type]?.[0] ?? '';
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
        const tasks = resp.task_ids.map((taskId, i) => ({ taskId, type: analysis[i].type }));
        this.analysisStarted.emit({ archiveId: this.archive().id, tasks });
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
    this.selected.set(new Set(this.types().map(t => t.type)));
    this.models.set(
      Object.fromEntries(this.types().map(t => [t.type, this.modelOptions()[t.type]?.[0] ?? '']))
    );
    this.openPopover.set(null);
    this.submitting.set(false);
    this.error.set(null);
  }
}
