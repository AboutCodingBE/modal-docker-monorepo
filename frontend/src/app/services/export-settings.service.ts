import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ExportSettings {
  default_export_path: string;
  content_char_limit: number;
}

@Injectable({ providedIn: 'root' })
export class ExportSettingsService {
  constructor(private http: HttpClient) {}

  getExportSettings(): Observable<ExportSettings> {
    return this.http.get<ExportSettings>('/api/settings/export');
  }

  updateExportSettings(settings: ExportSettings): Observable<ExportSettings> {
    return this.http.put<ExportSettings>('/api/settings/export', settings);
  }
}
