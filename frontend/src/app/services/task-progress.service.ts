import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Subject, Subscription } from 'rxjs';
import { SseProgressEvent } from '../shared/progress-bar/progress-bar';

export interface ActiveTask {
  task_id: string;
  archive_id: string;
  status: string;
  total_files: number;
  processed: number;
  failed_count: number;
  percentage: number;
}

export interface ProgressUpdate {
  archiveId: string;
  event: SseProgressEvent;
}

@Injectable({ providedIn: 'root' })
export class TaskProgressService {
  private sources = new Map<string, EventSource>();
  private updates = new Subject<ProgressUpdate>();

  readonly updates$ = this.updates.asObservable();

  constructor(private http: HttpClient) {}

  loadAndTrack(): void {
    this.http.get<ActiveTask[]>('/api/analysis/tasks/active').subscribe({
      next: (tasks) => {
        for (const task of tasks) {
          // Emit snapshot immediately so the card shows current progress on load
          this.updates.next({
            archiveId: task.archive_id,
            event: {
              task_id: task.task_id,
              status: task.status,
              total_files: task.total_files,
              processed: task.processed,
              failed_count: task.failed_count,
              current_file: null,
              percentage: task.percentage,
            },
          });
          this._subscribe(task.archive_id, task.task_id);
        }
      },
    });
  }

  track(archiveId: string, taskId: string): void {
    this._subscribe(archiveId, taskId);
  }

  private _subscribe(archiveId: string, taskId: string): void {
    // Avoid duplicate connections
    if (this.sources.has(taskId)) return;

    const source = new EventSource(`/api/analysis/tasks/${taskId}/progress`);

    source.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as SseProgressEvent;
        this.updates.next({ archiveId, event: data });

        if (data.status === 'completed' || data.status === 'failed') {
          source.close();
          this.sources.delete(taskId);
        }
      } catch {
        // ignore malformed events
      }
    };

    source.onerror = () => {
      source.close();
      this.sources.delete(taskId);
    };

    this.sources.set(taskId, source);
  }
}
