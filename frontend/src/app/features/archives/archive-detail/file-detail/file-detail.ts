import { Component, effect, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, Correspondent, FolderFile, NerResult, TopicsResult } from '../../../../services/archive.service';
import { AnalysisSummary } from '../analysis-summary/analysis-summary';

type Tab = 'overzicht' | 'samenvatting' | 'ner' | 'topics';

const PREVIEW_LIMIT = 2;

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

  correspondents = signal<Correspondent[] | null>(null);
  modalOpen = signal(false);
  modalRole = signal<string | null>(null);

  constructor() {
    effect(
      () => {
        const file = this.file();
        const archiveId = this.archiveId();
        this.activeTab.set('overzicht');
        this.nerData.set(null);
        this.nerLoaded.set(false);
        this.topicsData.set(null);
        this.topicsLoaded.set(false);
        this.correspondents.set(null);
        this.modalOpen.set(false);
        if (archiveId && file) {
          this._loadCorrespondents(archiveId, file.id);
        }
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

  formatCorrespondent(c: Correspondent): string {
    return c.name || c.email || '';
  }

  corrForRole(role: string): Correspondent[] {
    return (this.correspondents() ?? []).filter(c => c.role === role);
  }

  corrLabel(role: string): string {
    const items = this.corrForRole(role);
    const labels: Record<string, string> = { from: 'Van', to: 'Aan', cc: 'CC', bcc: 'BCC' };
    const base = labels[role] ?? role;
    return items.length > 1 ? `${base} (${items.length})` : base;
  }

  corrPreview(role: string): string {
    return this.corrForRole(role)
      .slice(0, PREVIEW_LIMIT)
      .map(c => this.formatCorrespondent(c))
      .filter(Boolean)
      .join(', ');
  }

  corrMoreCount(role: string): number {
    return Math.max(0, this.corrForRole(role).length - PREVIEW_LIMIT);
  }

  openModal(role: string): void {
    this.modalRole.set(role);
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
  }

  modalTitle(): string {
    const role = this.modalRole();
    return role ? this.corrLabel(role) : '';
  }

  modalItems(): string[] {
    const role = this.modalRole();
    if (!role) return [];
    return this.corrForRole(role)
      .map(c => {
        if (c.name && c.email) return `${c.name} <${c.email}>`;
        return c.name || c.email || '';
      })
      .filter(Boolean);
  }

  private _loadCorrespondents(archiveId: string, fileId: string): void {
    this.archiveService.getFileAnalysis(archiveId, fileId).subscribe({
      next: (data) => this.correspondents.set(data.correspondents ?? null),
      error: () => this.correspondents.set(null),
    });
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
