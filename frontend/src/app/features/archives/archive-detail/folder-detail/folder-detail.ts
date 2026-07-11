import { Component, effect, inject, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, FolderData, NerFolderResult } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

type Tab = 'overzicht' | 'samenvatting' | 'ner';

@Component({
  selector: 'app-folder-detail',
  standalone: true,
  imports: [CommonModule, AnalysisSummary],
  templateUrl: './folder-detail.html',
  styleUrl: './folder-detail.css',
})
export class FolderDetail {
  archiveId = input.required<string>();
  folderId = input<string | null>(null);
  folderData = input.required<FolderData>();

  private archiveService = inject(ArchiveService);

  activeTab = signal<Tab>('overzicht');
  nerData = signal<NerFolderResult | null>(null);
  nerLoading = signal(false);
  nerLoaded = signal(false);

  constructor() {
    effect(
      () => {
        this.folderId(); // track folder changes
        this.activeTab.set('overzicht');
        this.nerData.set(null);
        this.nerLoaded.set(false);
      },
      { allowSignalWrites: true },
    );
  }

  get folderName(): string {
    const path = this.folderData().path;
    const parts = path.split('/').filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : '/';
  }

  switchTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'ner' && !this.nerLoaded()) {
      this._loadNer();
    }
  }

  private _loadNer(): void {
    const folderId = this.folderId();
    if (!folderId) return;

    this.nerLoading.set(true);
    this.archiveService.getNerForFolder(this.archiveId(), folderId).subscribe({
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
}
