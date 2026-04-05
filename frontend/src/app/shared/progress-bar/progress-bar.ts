import { Component, input, computed } from '@angular/core';

export interface SseProgressEvent {
  task_id: string;
  status: string;
  total_files: number;
  processed: number;
  failed_count: number;
  current_file: string;
  percentage: number;
}

@Component({
  selector: 'app-progress-bar',
  templateUrl: './progress-bar.html',
  styleUrl: './progress-bar.css',
})
export class ProgressBar {
  percentage = input.required<number>();

  fillClass = computed(() => {
    const p = this.percentage();
    if (p >= 100) return 'complete';
    if (p > 0) return 'partial';
    return 'zero';
  });

  label = computed(() => {
    const p = this.percentage();
    if (p >= 100) return 'Voltooid';
    if (p > 0) return `${p}%`;
    return 'Niet gestart';
  });
}
