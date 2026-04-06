import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';
import { TaskProgressService } from '../../../services/task-progress.service';
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

  private updatesSub?: Subscription;

  constructor(
    private archiveService: ArchiveService,
    private taskProgress: TaskProgressService,
    private router: Router,
  ) {}

  ngOnInit(): void {
    this.archiveService.getAll().subscribe({
      next: (archives) => {
        this.archives.set(archives);
        this.loading.set(false);
        this._subscribeToUpdates();
        this.taskProgress.loadAndTrack();
      },
      error: () => {
        this.loadError.set(true);
        this.loading.set(false);
      },
    });
  }

  ngOnDestroy(): void {
    this.updatesSub?.unsubscribe();
  }

  openModal(): void {
    this.modalOpen.set(true);
  }

  closeModal(): void {
    this.modalOpen.set(false);
  }

  openArchive(id: string): void {
    this.router.navigate(['/archives', id]);
  }

  onArchiveCreated(archive: Archive): void {
    this.archives.update((list) => [archive, ...list]);
    this.closeModal();

    if (archive.tika_task_id) {
      this.taskProgress.track(archive.id, archive.tika_task_id);
    }
  }

  private _subscribeToUpdates(): void {
    this.updatesSub = this.taskProgress.updates$.subscribe((update) => {
      this.archives.update((list) =>
        list.map((a) => {
          if (a.id !== update.archiveId) return a;
          const { status, percentage } = update.event;
          const isCompleted = status === 'completed';
          const isFailed = status === 'failed';
          return {
            ...a,
            progress: isCompleted ? 100 : percentage,
            status: isCompleted ? 'ingested' : isFailed ? 'failed' : 'in_progress',
          };
        })
      );
    });
  }
}
