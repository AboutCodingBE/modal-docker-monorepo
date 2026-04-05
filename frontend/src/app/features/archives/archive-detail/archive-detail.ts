import { Component, OnInit, signal, computed, inject } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { CommonModule } from '@angular/common';

interface FileTypeCount {
  extension: string;
  count: number;
}

interface ArchiveStats {
  total_files: number;
  total_folders: number;
  file_types: FileTypeCount[];
}

interface FolderData {
  path: string;
  direct_file_count: number;
  subfolders: { name: string; path: string }[];
  file_types: FileTypeCount[];
}

// ── Mock data ──────────────────────────────────────────────
const MOCK_STATS: ArchiveStats = {
  total_files: 1089,
  total_folders: 18,
  file_types: [
    { extension: '.pdf', count: 514 },
    { extension: '.jpg', count: 429 },
    { extension: '.tiff', count: 119 },
    { extension: '.xlsx', count: 16 },
    { extension: '.docx', count: 9 },
    { extension: '.md', count: 1 },
    { extension: '.json', count: 1 },
  ],
};

const MOCK_FOLDERS: Record<string, FolderData> = {
  '/': {
    path: '/',
    direct_file_count: 3,
    subfolders: [
      { name: 'Briefwisseling', path: '/Briefwisseling' },
      { name: 'Notariële akten', path: '/Notariële akten' },
      { name: 'Kaarten en plannen', path: '/Kaarten en plannen' },
      { name: 'Foto-archief', path: '/Foto-archief' },
      { name: 'Registers', path: '/Registers' },
    ],
    file_types: [
      { extension: '.md', count: 1 },
      { extension: '.xlsx', count: 1 },
      { extension: '.json', count: 1 },
    ],
  },
  '/Briefwisseling': {
    path: '/Briefwisseling',
    direct_file_count: 65,
    subfolders: [
      { name: 'Inkomend 1850-1900', path: '/Briefwisseling/Inkomend 1850-1900' },
      { name: 'Uitgaand 1850-1900', path: '/Briefwisseling/Uitgaand 1850-1900' },
      { name: 'Inkomend 1900-1950', path: '/Briefwisseling/Inkomend 1900-1950' },
    ],
    file_types: [
      { extension: '.pdf', count: 45 },
      { extension: '.tiff', count: 12 },
      { extension: '.docx', count: 8 },
    ],
  },
  '/Notariële akten': {
    path: '/Notariële akten',
    direct_file_count: 143,
    subfolders: [
      { name: 'Testamenten', path: '/Notariële akten/Testamenten' },
      { name: 'Koopakten', path: '/Notariële akten/Koopakten' },
      { name: 'Huwelijkscontracten', path: '/Notariële akten/Huwelijkscontracten' },
    ],
    file_types: [
      { extension: '.pdf', count: 135 },
      { extension: '.xlsx', count: 8 },
    ],
  },
  '/Kaarten en plannen': {
    path: '/Kaarten en plannen',
    direct_file_count: 65,
    subfolders: [
      { name: 'Stadsplannen', path: '/Kaarten en plannen/Stadsplannen' },
      { name: 'Kadaster', path: '/Kaarten en plannen/Kadaster' },
    ],
    file_types: [
      { extension: '.tiff', count: 35 },
      { extension: '.jpg', count: 20 },
      { extension: '.pdf', count: 10 },
    ],
  },
  '/Foto-archief': {
    path: '/Foto-archief',
    direct_file_count: 232,
    subfolders: [
      { name: 'Personen', path: '/Foto-archief/Personen' },
      { name: 'Gebouwen', path: '/Foto-archief/Gebouwen' },
      { name: 'Evenementen', path: '/Foto-archief/Evenementen' },
    ],
    file_types: [
      { extension: '.jpg', count: 200 },
      { extension: '.tiff', count: 30 },
      { extension: '.xlsx', count: 1 },
      { extension: '.docx', count: 1 },
    ],
  },
  '/Registers': {
    path: '/Registers',
    direct_file_count: 35,
    subfolders: [
      { name: 'Bevolkingsregisters', path: '/Registers/Bevolkingsregisters' },
      { name: 'Burgerlijke stand', path: '/Registers/Burgerlijke stand' },
    ],
    file_types: [
      { extension: '.pdf', count: 25 },
      { extension: '.tiff', count: 10 },
    ],
  },
};

function _fallbackFolder(path: string): FolderData {
  return { path, direct_file_count: 0, subfolders: [], file_types: [] };
}
// ──────────────────────────────────────────────────────────

@Component({
  selector: 'app-archive-detail',
  imports: [CommonModule],
  templateUrl: './archive-detail.html',
  styleUrl: './archive-detail.css',
})
export class ArchiveDetail implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  archiveId = signal<string>('');
  archiveName = signal('Gemeentearchief Brugge');
  archivePath = signal('/Volumes/ExternalDrive/gemeentearchief-brugge');
  archiveDate = signal('2026-03-16');

  stats = signal<ArchiveStats>(MOCK_STATS);
  currentPath = signal('/');
  folderData = computed(() => MOCK_FOLDERS[this.currentPath()] ?? _fallbackFolder(this.currentPath()));

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
    this.archiveId.set(this.route.snapshot.paramMap.get('id') ?? '');
  }

  navigateTo(path: string): void {
    this.currentPath.set(path);
  }

  goBack(): void {
    this.router.navigate(['/archives']);
  }
}
