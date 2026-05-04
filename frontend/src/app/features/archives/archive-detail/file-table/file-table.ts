import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { CommonModule } from '@angular/common';
import { ArchiveService, FolderFile } from '../../../../services/archive.service';

@Component({
  selector: 'app-file-table',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './file-table.html',
  styleUrl: './file-table.css',
})
export class FileTable {
  archiveId = input.required<string>();
  /** Pass a UUID string for a subfolder, 'root' for the archive root, or null to hide the table. */
  folderId = input<string | null>(null);

  fileSelected = output<FolderFile | null>();

  private archiveService = inject(ArchiveService);

  files = signal<FolderFile[]>([]);
  loading = signal(false);
  searchTerm = signal('');
  typeFilter = signal('');
  selectedFileId = signal<string | null>(null);

  filteredFiles = computed(() => {
    let list = this.files();
    const term = this.searchTerm().toLowerCase();
    const type = this.typeFilter();
    if (term) list = list.filter((f) => f.name.toLowerCase().includes(term));
    if (type) list = list.filter((f) => f.mime_type === type);
    return list;
  });

  uniqueTypes = computed(() => {
    const types = new Set(
      this.files()
        .map((f) => f.mime_type)
        .filter((t): t is string => t !== null),
    );
    return [...types].sort();
  });

  constructor() {
    effect(
      () => {
        const archiveId = this.archiveId();
        const folderId = this.folderId();
        this.searchTerm.set('');
        this.typeFilter.set('');
        this.selectedFileId.set(null);
        if (archiveId && folderId === 'root') {
          this._loadRootFiles(archiveId);
        } else if (archiveId && folderId) {
          this._loadFiles(archiveId, folderId);
        } else {
          this.files.set([]);
        }
      },
      { allowSignalWrites: true },
    );
  }

  private _loadRootFiles(archiveId: string): void {
    this.loading.set(true);
    this.archiveService.getRootFiles(archiveId).subscribe({
      next: (data) => {
        this.files.set(data.files);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  private _loadFiles(archiveId: string, folderId: string): void {
    this.loading.set(true);
    this.archiveService.getFolderFiles(archiveId, folderId).subscribe({
      next: (data) => {
        this.files.set(data.files);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  onSearch(event: Event): void {
    this.searchTerm.set((event.target as HTMLInputElement).value);
  }

  onTypeFilter(event: Event): void {
    this.typeFilter.set((event.target as HTMLSelectElement).value);
  }

  selectFile(file: FolderFile): void {
    if (this.selectedFileId() === file.id) {
      this.selectedFileId.set(null);
      this.fileSelected.emit(null);
    } else {
      this.selectedFileId.set(file.id);
      this.fileSelected.emit(file);
    }
  }

  formatSize(bytes: number | null): string {
    if (bytes === null || bytes === undefined) return '—';
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
    if (bytes >= 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return bytes + ' B';
  }
}
