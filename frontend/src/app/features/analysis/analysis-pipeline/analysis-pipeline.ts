import { Component, input, computed } from '@angular/core';
import { AnalysisProgressEvent } from '../../../models/archive.model';

@Component({
  selector: 'app-analysis-pipeline',
  templateUrl: './analysis-pipeline.html',
  styleUrl: './analysis-pipeline.css',
})
export class AnalysisPipeline {
  event = input.required<AnalysisProgressEvent>();
  stepName = input<string>('Samenvatting');

  percentage = computed(() => this.event().percentage);
  processed = computed(() => this.event().processed);
  total = computed(() => this.event().total_files);
  currentFile = computed(() => {
    const f = this.event().current_file;
    if (!f) return null;
    // Show only the filename, not the full path
    const parts = f.replace(/\\/g, '/').split('/');
    return parts[parts.length - 1];
  });
  isCompleted = computed(() => this.event().status === 'completed');
  isFailed = computed(() => this.event().status === 'failed');
}
