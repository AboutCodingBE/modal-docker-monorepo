import { Component, OnInit, signal } from '@angular/core';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';
import { ArchiveCard } from '../archive-card/archive-card';
import { NewArchiveModal } from '../new-archive-modal/new-archive-modal';

@Component({
  selector: 'app-archive-browser',
  imports: [ArchiveCard, NewArchiveModal],
  templateUrl: './archive-browser.html',
  styleUrl: './archive-browser.css',
})
export class ArchiveBrowser implements OnInit {
  archives = signal<Archive[]>([]);
  loading = signal(true);
  loadError = signal(false);
  modalOpen = signal(false);

  constructor(private archiveService: ArchiveService) {}

  ngOnInit(): void {
    this.archiveService.getAll().subscribe({
      next: (archives) => {
        this.archives.set(archives);
        this.loading.set(false);
      },
      error: () => {
        this.loadError.set(true);
        this.loading.set(false);
      },
    });
  }

  openModal(): void {
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
  }

  onArchiveCreated(archive: Archive): void {
    this.archives.update((list) => [archive, ...list]);
    this.closeModal();
  }
}
