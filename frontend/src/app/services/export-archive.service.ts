import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export type ExportFormat = 'csv' | 'json';

export interface ExportResult {
  path: string;
}

@Injectable({ providedIn: 'root' })
export class ExportArchiveService {
  constructor(private http: HttpClient) {}

  exportArchive(archiveId: string, format: ExportFormat): Observable<ExportResult> {
    return this.http.post<ExportResult>(`/api/archives/${archiveId}/export`, { format });
  }
}
