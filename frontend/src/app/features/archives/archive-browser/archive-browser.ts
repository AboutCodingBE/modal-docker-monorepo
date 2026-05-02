import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';
import { TaskProgressService } from '../../../services/task-progress.service';
import { ArchiveCard } from '../archive-card/archive-card';
import { NewArchiveModal } from '../new-archive-modal/new-archive-modal';
import { AnalysisModal } from '../../analysis/analysis-modal/analysis-modal';

@Component({
  selector: 'app-archive-browser',
  imports: [ArchiveCard, NewArchiveModal, AnalysisModal],
  templateUrl: './archive-browser.html',
  styleUrl: './archive-browser.css',
})
export class ArchiveBrowser implements OnInit, OnDestroy {
  archives = signal<Archive[]>([]);
  loading = signal(true);
  loadError = signal(false);
  modalOpen = signal(false);

  // Analysis modal state
  analysisModalArchive = signal<Archive | null>(null);

  // Track which task IDs belong to AI analysis (vs Tika ingestion)
  private analysisTaskIds = new Set<string>();

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

  // ── Analysis modal ─────────────────────────────────────────────────────────

  openAnalysisModal(archiveId: string): void {
    const archive = this.archives().find(a => a.id === archiveId);
    if (archive) this.analysisModalArchive.set(archive);
  }

  closeAnalysisModal(): void {
    this.analysisModalArchive.set(null);
  }

  onAnalysisStarted(event: { archiveId: string; taskIds: string[] }): void {
    // Register task IDs as AI analysis tasks
    for (const taskId of event.taskIds) {
      this.analysisTaskIds.add(taskId);
      this.taskProgress.track(event.archiveId, taskId);
    }

    // Mark archive as in_progress immediately
    this.archives.update(list =>
      list.map(a =>
        a.id === event.archiveId ? { ...a, status: 'in_progress' as const } : a
      )
    );
  }

  // ── SSE updates ────────────────────────────────────────────────────────────

  private _subscribeToUpdates(): void {
    this.updatesSub = this.taskProgress.updates$.subscribe((update) => {
      const isAiAnalysis = this.analysisTaskIds.has(update.event.task_id);
      const { status, percentage } = update.event;
      const isCompleted = status === 'completed';
      const isFailed = status === 'failed';

      this.archives.update((list) =>
        list.map((a) => {
          if (a.id !== update.archiveId) return a;

          if (isAiAnalysis) {
            // AI analysis: completed → 'analysed', active → keep pipeline event
            const completedStatus = isCompleted ? 'analysed' as const : isFailed ? 'failed' as const : 'in_progress' as const;
            return {
              ...a,
              status: completedStatus,
              analysisEvent: isCompleted || isFailed ? null : update.event,
            };
          } else {
            // Tika ingestion: completed → 'ingested', active → progress bar
            return {
              ...a,
              progress: isCompleted ? 100 : percentage,
              status: isCompleted ? 'ingested' as const : isFailed ? 'failed' as const : 'in_progress' as const,
            };
          }
        })
      );
    });
  }
}
