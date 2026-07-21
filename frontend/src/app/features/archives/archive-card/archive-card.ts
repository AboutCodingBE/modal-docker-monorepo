import { Component, input, output, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Archive } from '../../../models/archive.model';
import { ArchiveService, AnalysisConfigEntry } from '../../../services/archive.service';
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

  private archiveService = inject(ArchiveService);
  private configuration = toSignal(this.archiveService.getAnalysisConfiguration(), {
    initialValue: [] as AnalysisConfigEntry[],
  });

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

  isDone(type: string): boolean {
    return this.archive().completed_analysis_types.includes(type);
  }

  analysisTypeLabel(type: string): string {
    return ANALYSIS_TYPE_META[type]?.label ?? type;
  }
}
