import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Archive } from '../models/archive.model';
import { SseProgressEvent } from '../shared/progress-bar/progress-bar';

@Injectable({ providedIn: 'root' })
export class ArchiveService {
  constructor(private http: HttpClient) {}

  getAll(): Observable<Archive[]> {
    return this.http.get<Archive[]>('/api/archives');
  }

  create(name: string, path: string): Observable<Archive> {
    return this.http.post<Archive>('/api/archives', { name, path });
  }

  subscribeToProgress(taskId: string): Observable<SseProgressEvent> {
    return new Observable((observer) => {
      const source = new EventSource(`/api/analysis/tasks/${taskId}/progress`);

      source.onmessage = (event) => {
        try {
          observer.next(JSON.parse(event.data) as SseProgressEvent);
        } catch {
          // ignore malformed events
        }
      };

      source.onerror = () => {
        source.close();
        observer.complete();
      };

      return () => source.close();
    });
  }
}
