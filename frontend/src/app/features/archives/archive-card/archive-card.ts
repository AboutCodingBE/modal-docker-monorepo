import { Component, input, output, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Archive } from '../../../models/archive.model';
import { ConfigurationService } from '../../../services/configuration.service';
import { ExportArchiveService, ExportFormat } from '../../../services/export-archive.service';
import { ProgressBar } from '../../../shared/progress-bar/progress-bar';
import { AnalysisPipeline } from '../../analysis/analysis-pipeline/analysis-pipeline';
import { ANALYSIS_TYPE_META, splitAnalysisTypes } from '../../../shared/analysis-type.util';

const TYPE_LABELS: Record<string, string> = {
  summary: 'Samenvatting',
  ner: 'Entiteitsherkenning',
  topic_detection: 'Onderwerpdetectie',
};

@Component({
  selector: 'app-archive-card',
  templateUrl: './archive-card.html',
  styleUrl: './archive-card.css',
  imports: [ProgressBar, AnalysisPipeline],
})
export class ArchiveCard {
  archive = input.required<Archive>();
  cardClicked = output<string>();
  startAnalysisClicked = output<string>();
  deleteClicked = output<string>();

  private configService = inject(ConfigurationService);
  private exportService = inject(ExportArchiveService);
  private modelsByType = toSignal(this.configService.getModels(), { initialValue: {} as Record<string, { id: string; model: string; is_default: boolean }[]> });

  private configuration = computed(() =>
    Object.entries(this.modelsByType()).map(([type, entries]) => ({
      type,
      model: entries.find(e => e.is_default)?.model ?? entries[0]?.model ?? '',
    }))
  );

  configuredTypes = computed(() => this.configuration());

  analysisSplit = computed(() =>
    splitAnalysisTypes(this.configuration(), this.archive().completed_analysis_types),
  );

  statusLabel = computed(() => {
    const labels: Record<string, string> = {
      analysed: 'ANALYSED',
      ingested: 'INGESTED',
      in_progress: 'BEZIG',
      failed: 'FAILED',
    };
    return labels[this.archive().status] ?? this.archive().status.toUpperCase();
  });

  statusClass = computed(() => `status-${this.archive().status}`);

  // Show Tika progress bar only when no AI analysis pipeline is active
  showProgressBar = computed(() => {
    if (this.archive().analysisEvent) return false;
    const p = this.archive().progress ?? 0;
    return p > 0 && p < 100;
  });

  // Show AI analysis pipeline when an analysis event is present
  showPipeline = computed(() => !!this.archive().analysisEvent);

  progress = computed(() => this.archive().progress ?? 0);

  stepName = computed(() => {
    const type = this.archive().analysisEvent?.type;
    return type ? (TYPE_LABELS[type] ?? type) : 'Analyse';
  });

  // ── Export ───────────────────────────────────────────────────────────────
  exporting = signal(false);
  exportMenuOpen = signal(false);
  exportSuccessPath = signal<string | null>(null);
  exportError = signal<string | null>(null);

  toggleExportMenu(): void {
    this.exportMenuOpen.update(open => !open);
  }

  onExport(format: ExportFormat): void {
    this.exportMenuOpen.set(false);
    this.exporting.set(true);
    this.exportSuccessPath.set(null);
    this.exportError.set(null);

    this.exportService.exportArchive(this.archive().id, format).subscribe({
      next: (result) => {
        this.exporting.set(false);
        this.exportSuccessPath.set(result.path);
        setTimeout(() => this.exportSuccessPath.set(null), 5000);
      },
      error: (err) => {
        this.exporting.set(false);
        this.exportError.set(err?.error?.detail ?? 'Export mislukt.');
        setTimeout(() => this.exportError.set(null), 5000);
      },
    });
  }

  isDone(type: string): boolean {
    return this.archive().completed_analysis_types.includes(type);
  }

  analysisTypeLabel(type: string): string {
    return ANALYSIS_TYPE_META[type]?.label ?? type;
  }
}
