import { Component, input, output, signal, computed, OnInit } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';
import { ConfigurationService } from '../../../services/configuration.service';
import { ANALYSIS_TYPE_META } from '../../../shared/analysis-type.util';

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
  doneTypeLabels = signal<string[]>([]);

  selected = signal<Set<string>>(new Set());
  models = signal<Record<string, string>>({});
  openPopover = signal<string | null>(null);
  submitting = signal(false);
  error = signal<string | null>(null);

  canStart = computed(() => this.selected().size > 0 && !this.submitting());

  constructor(private archiveService: ArchiveService, private configService: ConfigurationService) {}

  ngOnInit(): void {
    this.configService.getModels().subscribe({
      next: (grouped) => {
        const completedSet = new Set(this.archive().completed_analysis_types);

        const pendingTypes = Object.keys(grouped).filter(t => !completedSet.has(t));
        const doneTypes = Object.keys(grouped).filter(t => completedSet.has(t));

        this.doneTypeLabels.set(doneTypes.map(t => ANALYSIS_TYPE_META[t]?.label ?? t));

        const analysisTypes: AnalysisType[] = pendingTypes.map(t => {
          const key = t.toLowerCase();
          return { type: key, ...(TYPE_DISPLAY[key] ?? { ...DEFAULT_DISPLAY, label: t }) };
        });

        const options: Record<string, string[]> = {};
        const defaultModels: Record<string, string> = {};
        for (const t of pendingTypes) {
          const key = t.toLowerCase();
          const entries = grouped[t];
          options[key] = entries.map(e => e.model);
          const defaultEntry = entries.find(e => e.is_default) ?? entries[0];
          if (defaultEntry) defaultModels[key] = defaultEntry.model;
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
