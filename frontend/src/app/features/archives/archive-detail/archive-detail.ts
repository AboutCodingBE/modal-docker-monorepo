import { Component, OnInit, signal, computed, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';
import { ArchiveService, ArchiveStats, FolderData } from '../../../services/archive.service';

@Component({
  selector: 'app-archive-detail',
  imports: [CommonModule],
  templateUrl: './archive-detail.html',
  styleUrl: './archive-detail.css',
})
export class ArchiveDetail implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private archiveService = inject(ArchiveService);

  archiveId = signal<string>('');
  stats = signal<ArchiveStats | null>(null);
  folderData = signal<FolderData | null>(null);
  currentPath = signal('/');
  loadingStats = signal(true);
  loadingFolder = signal(true);

  breadcrumbs = computed(() => {
    const path = this.currentPath();
    if (path === '/') return [{ label: '/', path: '/' }];
    const parts = path.split('/').filter(Boolean);
    return [
      { label: '/', path: '/' },
      ...parts.map((part, i) => ({
        label: part,
        path: '/' + parts.slice(0, i + 1).join('/'),
      })),
    ];
  });

  ngOnInit(): void {
    const id = this.route.snapshot.paramMap.get('id') ?? '';
    this.archiveId.set(id);
    this._loadStats(id);
    this._loadFolder(id, '/');
  }

  navigateTo(path: string): void {
    this.currentPath.set(path);
    this._loadFolder(this.archiveId(), path);
  }

  goBack(): void {
    this.router.navigate(['/archives']);
  }

  private _loadStats(id: string): void {
    this.loadingStats.set(true);
    this.archiveService.getStats(id).subscribe({
      next: (stats) => {
        this.stats.set(stats);
        this.loadingStats.set(false);
      },
      error: () => this.loadingStats.set(false),
    });
  }

  private _loadFolder(id: string, path: string): void {
    this.loadingFolder.set(true);
    this.archiveService.getFolder(id, path).subscribe({
      next: (folder) => {
        this.folderData.set(folder);
        this.loadingFolder.set(false);
      },
      error: () => this.loadingFolder.set(false),
    });
  }
}
