import { Component, effect, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, FolderFile, NerResult, TopicsResult } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

type Tab = 'overzicht' | 'samenvatting' | 'ner' | 'topics';

@Component({
  selector: 'app-file-detail',
  standalone: true,
  imports: [CommonModule, AnalysisSummary],
  templateUrl: './file-detail.html',
  styleUrl: './file-detail.css',
})
export class FileDetail {
  archiveId = input.required<string>();
  file = input.required<FolderFile>();

  back = output<void>();

  private archiveService = inject(ArchiveService);

  activeTab = signal<Tab>('overzicht');
  nerData = signal<NerResult | null>(null);
  nerLoading = signal(false);
  nerLoaded = signal(false);
  topicsData = signal<TopicsResult | null>(null);
  topicsLoading = signal(false);
  topicsLoaded = signal(false);

  constructor() {
    effect(
      () => {
        this.file(); // track file changes
        this.activeTab.set('overzicht');
        this.nerData.set(null);
        this.nerLoaded.set(false);
        this.topicsData.set(null);
        this.topicsLoaded.set(false);
      },
      { allowSignalWrites: true },
    );
  }

  switchTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'ner' && !this.nerLoaded()) {
      this._loadNer();
    }
    if (tab === 'topics' && !this.topicsLoaded()) {
      this._loadTopics();
    }
  }

  formatSize(bytes: number | null): string {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }

  formatDate(iso: string | null): string {
    if (!iso) return '—';
    return iso.split('T')[0];
  }

  private _loadNer(): void {
    this.nerLoading.set(true);
    this.archiveService.getNerForFile(this.archiveId(), this.file().id).subscribe({
      next: (data) => {
        this.nerData.set(data);
        this.nerLoading.set(false);
        this.nerLoaded.set(true);
      },
      error: () => {
        this.nerData.set(null);
        this.nerLoading.set(false);
        this.nerLoaded.set(true);
      },
    });
  }

  private _loadTopics(): void {
    this.topicsLoading.set(true);
    this.archiveService.getTopicsForFile(this.archiveId(), this.file().id).subscribe({
      next: (data) => {
        this.topicsData.set(data);
        this.topicsLoading.set(false);
        this.topicsLoaded.set(true);
      },
      error: () => {
        this.topicsData.set(null);
        this.topicsLoading.set(false);
        this.topicsLoaded.set(true);
      },
    });
  }
}
