import { Component, effect, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, FileAnalysis, AnalysisSummaryEntry } from '../../../../services/archive.service';

@Component({
  selector: 'app-analysis-summary',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './analysis-summary.html',
  styleUrl: './analysis-summary.css',
})
export class AnalysisSummary {
  archiveId = input.required<string>();
  fileId = input.required<string>();
  label = input<string>('AI-GEGENEREERDE SAMENVATTING');

  private archiveService = inject(ArchiveService);

  analysis = signal<FileAnalysis | null>(null);
  loading = signal(true);

  constructor() {
    effect(() => {
      const archiveId = this.archiveId();
      const fileId = this.fileId();
      if (archiveId && fileId) {
        this._load(archiveId, fileId);
      }
    }, { allowSignalWrites: true });
  }

  private _load(archiveId: string, fileId: string): void {
    this.loading.set(true);
    this.archiveService.getFileAnalysis(archiveId, fileId).subscribe({
      next: (data) => { this.analysis.set(data); this.loading.set(false); },
      error: () => { this.analysis.set(null); this.loading.set(false); },
    });
  }

  get latestSummary(): AnalysisSummaryEntry | null {
    return this.analysis()?.summaries[0] ?? null;
  }
}
