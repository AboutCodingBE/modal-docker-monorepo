import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Archive } from '../models/archive.model';
import { SseProgressEvent } from '../shared/progress-bar/progress-bar';

export interface MimeTypeCount {
  mime_type: string;
  count: number;
}

export interface ArchiveStats {
  name: string;
  root_path: string;
  created_at: string | null;
  total_files: number;
  total_folders: number;
  mime_types: MimeTypeCount[];
}

export interface FolderData {
  path: string;
  direct_file_count: number;
  subfolders: { name: string; path: string }[];
  mime_types: MimeTypeCount[];
}

@Injectable({ providedIn: 'root' })
export class ArchiveService {
  constructor(private http: HttpClient) {}

  getAll(): Observable<Archive[]> {
    return this.http.get<Archive[]>('/api/archives');
  }

  create(name: string, path: string): Observable<Archive> {
    return this.http.post<Archive>('/api/archives', { name, path });
  }

  getStats(archiveId: string): Observable<ArchiveStats> {
    return this.http.get<ArchiveStats>(`/api/archives/${archiveId}/stats`);
  }

  getFolder(archiveId: string, path: string): Observable<FolderData> {
    return this.http.get<FolderData>(`/api/archives/${archiveId}/folder`, {
      params: { path },
    });
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
