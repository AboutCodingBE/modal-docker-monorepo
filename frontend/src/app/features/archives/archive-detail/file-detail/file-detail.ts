import { Component, effect, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, FolderFile, NerResult, TopicsResult } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

type Tab = 'samenvatting' | 'ner' | 'topics';

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

  activeTab = signal<Tab>('samenvatting');
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
        this.activeTab.set('samenvatting');
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
