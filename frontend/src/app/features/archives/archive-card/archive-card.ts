import { Component, input, output, computed } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ProgressBar } from '../../../shared/progress-bar/progress-bar';
import { AnalysisPipeline } from '../../analysis/analysis-pipeline/analysis-pipeline';

const TYPE_LABELS: Record<string, string> = {
  summary: 'Samenvatting',
  ner: 'Entiteitsherkenning',
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
}
