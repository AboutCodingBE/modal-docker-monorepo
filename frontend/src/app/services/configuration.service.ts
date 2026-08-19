import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface ModelEntry {
  id: string;
  model: string;
  is_default: boolean;
}

export interface ProcessingSettings {
  summary_char_limit: number;
  topic_char_limit: number;
  ner_llm_char_limit: number;
  minimum_text_length: number;
}

export interface DownloadProgressEvent {
  status: string;
  completed_bytes: number | null;
  total_bytes: number | null;
  done: boolean;
  error: string | null;
}

@Injectable({ providedIn: 'root' })
export class ConfigurationService {
  constructor(private http: HttpClient) {}

  startOllamaDownload(model: string): Observable<{ download_id: string }> {
    return this.http.post<{ download_id: string }>('/api/models/ollama', { model });
  }

  getModels(): Observable<Record<string, ModelEntry[]>> {
    return this.http.get<Record<string, ModelEntry[]>>('/api/settings/models');
  }

  setDefaultModels(ids: string[]): Observable<Record<string, ModelEntry[]>> {
    return this.http.put<Record<string, ModelEntry[]>>('/api/settings/models/defaults', { ids });
  }

  getProcessingSettings(): Observable<ProcessingSettings> {
    return this.http.get<ProcessingSettings>('/api/settings/processing');
  }

  updateProcessingSettings(settings: {
    summary_char_limit: number;
    topic_char_limit: number;
    ner_llm_char_limit: number;
    minimum_text_length: number;
  }): Observable<ProcessingSettings> {
    return this.http.put<ProcessingSettings>('/api/settings/processing', settings);
  }
}
