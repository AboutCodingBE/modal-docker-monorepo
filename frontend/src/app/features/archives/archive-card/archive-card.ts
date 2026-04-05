import { Component, input, computed } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ProgressBar } from '../../../shared/progress-bar/progress-bar';

@Component({
  selector: 'app-archive-card',
  templateUrl: './archive-card.html',
  styleUrl: './archive-card.css',
  imports: [ProgressBar],
})
export class ArchiveCard {
  archive = input.required<Archive>();

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

  showProgressBar = computed(() => {
    const p = this.archive().progress ?? 0;
    return p > 0 && p < 100;
  });

  progress = computed(() => this.archive().progress ?? 0);
}
