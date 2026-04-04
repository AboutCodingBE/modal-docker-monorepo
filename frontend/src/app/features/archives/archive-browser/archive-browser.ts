import { Component, signal } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveCard } from '../archive-card/archive-card';
import { NewArchiveModal } from '../new-archive-modal/new-archive-modal';

// Placeholder data until backend is wired up
const MOCK_ARCHIVES: Archive[] = [
  { id: 1, name: 'ADVN_VEA260_VUJO', date: '2026-02-13', files: 438, status: 'analysed' },
  { id: 2, name: 'Collectie_Van_Damme_2025', date: '2026-01-20', files: 1250, status: 'ingested' },
  { id: 3, name: 'Radio_Archief_VRT_S01', date: '2026-01-05', files: 89, status: 'analysed' },
];

@Component({
  selector: 'app-archive-browser',
  imports: [ArchiveCard, NewArchiveModal],
  templateUrl: './archive-browser.html',
  styleUrl: './archive-browser.css',
})
export class ArchiveBrowser {
  archives = signal<Archive[]>(MOCK_ARCHIVES);
  modalOpen = signal(false);

  openModal(): void {
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
  }

  onArchiveCreated(archive: Archive): void {
    this.archives.update((list) => [...list, archive]);
    this.closeModal();
  }
}
