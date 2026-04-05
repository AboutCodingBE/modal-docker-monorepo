import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
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
export class ArchiveBrowser implements OnInit, OnDestroy {
  archives = signal<Archive[]>([]);
  loading = signal(true);
  loadError = signal(false);
  modalOpen = signal(false);

  private progressSubs = new Map<string, Subscription>();

  constructor(private archiveService: ArchiveService, private router: Router) {}

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

  ngOnDestroy(): void {
    this.progressSubs.forEach((sub) => sub.unsubscribe());
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

    if (archive.tika_task_id) {
      this._trackProgress(archive.id, archive.tika_task_id);
    }
  }

  openArchive(id: string): void {
    this.router.navigate(['/archives', id]);
  }

  private _trackProgress(archiveId: string, taskId: string): void {
    const sub = this.archiveService.subscribeToProgress(taskId).subscribe({
      next: (event) => {
        this.archives.update((list) =>
          list.map((a) => {
            if (a.id !== archiveId) return a;
            const isCompleted = event.status === 'completed';
            const isFailed = event.status === 'failed';
            return {
              ...a,
              progress: isCompleted ? 100 : event.percentage,
              status: isCompleted ? 'ingested' : isFailed ? 'failed' : 'in_progress',
            };
          })
        );
      },
      complete: () => {
        this.progressSubs.delete(taskId);
      },
    });

    this.progressSubs.set(taskId, sub);
  }
}
