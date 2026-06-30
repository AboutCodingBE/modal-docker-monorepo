import { Component, input, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FolderData } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

type Tab = 'overzicht' | 'samenvatting';

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

  activeTab = signal<Tab>('overzicht');

  get folderName(): string {
    const path = this.folderData().path;
    const parts = path.split('/').filter(Boolean);
    return parts.length > 0 ? parts[parts.length - 1] : '/';
  }

  switchTab(tab: Tab): void {
    this.activeTab.set(tab);
  }
}
