import { Component, OnInit, OnDestroy, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Subscription } from 'rxjs';
import { Archive } from '../../../models/archive.model';
import { ArchiveService } from '../../../services/archive.service';
import { ActiveTask, TaskProgressService } from '../../../services/task-progress.service';
import { ArchiveCard } from '../archive-card/archive-card';
import { NewArchiveModal } from '../new-archive-modal/new-archive-modal';
import { AnalysisModal } from '../../analysis/analysis-modal/analysis-modal';
import { DeleteArchiveModal } from '../delete-archive-modal/delete-archive-modal';

@Component({
  selector: 'app-archive-browser',
  imports: [ArchiveCard, NewArchiveModal, AnalysisModal, DeleteArchiveModal],
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

  // Delete modal state
  archiveToDelete = signal<Archive | null>(null);

  // Track which task IDs belong to AI analysis (vs Tika ingestion)
  private analysisTaskIds = new Set<string>();

  // Per-archive queue of task IDs not yet subscribed to SSE
  private taskQueues = new Map<string, string[]>();

  // Maps task ID to its analysis type (e.g. 'summary', 'ner')
  private taskTypes = new Map<string, string>();

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
        this._loadAndTrack();
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

  openDeleteModal(archiveId: string): void {
    const archive = this.archives().find(a => a.id === archiveId);
    if (archive) this.archiveToDelete.set(archive);
  }

  confirmDelete(): void {
    const archive = this.archiveToDelete();
    if (!archive) return;

    this.archiveToDelete.set(null);
    this.archiveService.deleteArchive(archive.id).subscribe({
      next: () => {
        this.archives.update(list => list.filter(a => a.id !== archive.id));
      },
    });
  }

  cancelDelete(): void {
    this.archiveToDelete.set(null);
  }

  openAnalysisModal(archiveId: string): void {
    const archive = this.archives().find(a => a.id === archiveId);
    if (archive) this.analysisModalArchive.set(archive);
  }

  closeAnalysisModal(): void {
    this.analysisModalArchive.set(null);
  }

  onAnalysisStarted(event: { archiveId: string; tasks: { taskId: string; type: string }[] }): void {
    // Register all task IDs as AI analysis tasks
    for (const { taskId, type } of event.tasks) {
      this.analysisTaskIds.add(taskId);
      this.taskTypes.set(taskId, type);
    }

    // Open SSE only for the first task; queue the rest
    if (event.tasks.length > 0) {
      this.taskProgress.track(event.archiveId, event.tasks[0].taskId);
      this.taskQueues.set(event.archiveId, event.tasks.slice(1).map(t => t.taskId));
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
            const enrichedEvent = isCompleted || isFailed ? null : {
              ...update.event,
              type: this.taskTypes.get(update.event.task_id),
            };
            return {
              ...a,
              status: completedStatus,
              analysisEvent: enrichedEvent,
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

      // When an AI analysis task finishes, start the next queued task
      if (isAiAnalysis && (isCompleted || isFailed)) {
        const queue = this.taskQueues.get(update.archiveId) ?? [];
        if (queue.length > 0) {
          const [nextTaskId, ...rest] = queue;
          this.taskQueues.set(update.archiveId, rest);
          this.taskProgress.track(update.archiveId, nextTaskId);
        } else {
          this.taskQueues.delete(update.archiveId);
        }
      }
    });
  }

  // ── Reload / navigate-back: reconnect to in-flight tasks ──────────────────

  private _loadAndTrack(): void {
    this.taskProgress.getActiveTasks().subscribe({
      next: (tasks) => {
        // Emit an immediate snapshot for each task so cards show current state
        for (const task of tasks) {
          this.taskProgress.emitSnapshot(task);
        }

        // Tika tasks: subscribe immediately
        for (const task of tasks.filter(t => t.task_type === 'tika')) {
          this.taskProgress.track(task.archive_id, task.task_id);
        }

        // Analysis tasks: group by archive (already ordered by created_at ASC),
        // subscribe to the first per archive and queue the rest
        const byArchive = new Map<string, ActiveTask[]>();
        for (const task of tasks.filter(t => t.task_type === 'analysis')) {
          this.analysisTaskIds.add(task.task_id);
          const list = byArchive.get(task.archive_id) ?? [];
          list.push(task);
          byArchive.set(task.archive_id, list);
        }

        for (const [archiveId, archiveTasks] of byArchive) {
          this.taskProgress.track(archiveId, archiveTasks[0].task_id);
          if (archiveTasks.length > 1) {
            this.taskQueues.set(archiveId, archiveTasks.slice(1).map(t => t.task_id));
          }
        }
      },
    });
  }
}
