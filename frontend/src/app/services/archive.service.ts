import { Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';
import { Archive } from '../models/archive.model';

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

export interface CategoryCount {
  category: string;
  count: number;
}

export interface FolderData {
  path: string;
  folder_id: string | null;
  direct_file_count: number;
  subfolders: { name: string; path: string }[];
  mime_types: MimeTypeCount[];
  categories: CategoryCount[];
}

export interface FolderFile {
  id: string;
  name: string;
  relative_path: string;
  extension: string | null;
  size_bytes: number | null;
  mime_type: string | null;
  category: string | null;
  language: string | null;
  author: string | null;
  content_created_at: string | null;
}

export interface NerResult {
  file_id: string;
  file_name: string;
  model: string | null;
  persons: string[];
  locations: string[];
  organisations: string[];
  misc: string[];
  total_entities: number;
}

export interface NerFolderResult {
  folder_id: string;
  folder_name: string;
  model: string | null;
  persons: string[];
  locations: string[];
  organisations: string[];
  misc: string[];
  total_entities: number;
}

export interface TopicsResult {
  file_id: string;
  file_name: string;
  model: string | null;
  topics: string[];
  total_topics: number;
}

export interface TopicsFolderResult {
  folder_id: string;
  folder_name: string;
  model: string | null;
  topics: string[];
  total_topics: number;
}

export interface TimelineHeatmapCell {
  year: number;
  y_value: string;
  count: number;
}

export interface TimelineHeatmapResult {
  folder_id: string;
  folder_name: string;
  y_dimension: string;
  years: number[];
  available_range: [number | null, number | null];
  y_values: string[];
  y_value_counts: Record<string, number>;
  default_range: [number | null, number | null];
  cells: TimelineHeatmapCell[];
}

export interface FolderFilesData {
  folder_id: string;
  folder_name: string;
  files: FolderFile[];
}

export interface ListFilesParams {
  folder_path?: string;
  sort_by?: string;
  sort_dir?: string;
  mime_types?: string[];
  categories?: string[];
  languages?: string[];
  entities?: string[];
  topics?: string[];
  cursor_id?: string;
  cursor_value?: string;
}

export interface ListFilesResponse {
  files: FolderFile[];
  has_next: boolean;
  next_cursor_id: string | null;
  next_cursor_value: string | null;
}

export interface AutocompleteResponse {
  suggestions: string[];
}

export interface AnalysisSummaryEntry {
  analysis_id: string;
  model: string;
  date: string;
  result: string;
}

export interface FileAnalysis {
  file_id: string;
  type: 'file' | 'folder';
  summaries: AnalysisSummaryEntry[];
}

@Injectable({ providedIn: 'root' })
export class ArchiveService {
  constructor(private http: HttpClient) {}

  getAll(): Observable<Archive[]> {
    return this.http.get<Archive[]>('/api/archives');
  }

  create(name: string, path: string, ocr_enabled: boolean): Observable<Archive> {
    return this.http.post<Archive>('/api/archives', { name, path, ocr_enabled });
  }

  getStats(archiveId: string): Observable<ArchiveStats> {
    return this.http.get<ArchiveStats>(`/api/archives/${archiveId}/stats`);
  }

  getFolder(archiveId: string, path: string): Observable<FolderData> {
    return this.http.get<FolderData>(`/api/archives/${archiveId}/folder`, {
      params: { path },
    });
  }

  getRootFiles(archiveId: string): Observable<FolderFilesData> {
    return this.http.get<FolderFilesData>(`/api/archives/${archiveId}/folder/root/files`);
  }

  getFolderFiles(archiveId: string, folderId: string): Observable<FolderFilesData> {
    return this.http.get<FolderFilesData>(`/api/archives/${archiveId}/folder/${folderId}/files`);
  }

  getFileAnalysis(archiveId: string, fileId: string): Observable<FileAnalysis> {
    return this.http.get<FileAnalysis>(`/api/archives/${archiveId}/analysis/${fileId}`);
  }

  getNerForFile(archiveId: string, fileId: string): Observable<NerResult> {
    return this.http.get<NerResult>(`/api/archives/${archiveId}/files/${fileId}/ner`);
  }

  getNerForFolder(archiveId: string, folderId: string): Observable<NerFolderResult> {
    return this.http.get<NerFolderResult>(`/api/archives/${archiveId}/folders/${folderId}/ner`);
  }

  getTopicsForFile(archiveId: string, fileId: string): Observable<TopicsResult> {
    return this.http.get<TopicsResult>(`/api/archives/${archiveId}/files/${fileId}/topics`);
  }

  getTopicsForFolder(archiveId: string, folderId: string): Observable<TopicsFolderResult> {
    return this.http.get<TopicsFolderResult>(`/api/archives/${archiveId}/folders/${folderId}/topics`);
  }

  getTimelineHeatmap(archiveId: string, folderId: string, yDimension: string, rangeMin?: number, rangeMax?: number): Observable<TimelineHeatmapResult> {
    let params = new HttpParams().set('y_dimension', yDimension);
    if (rangeMin !== undefined) params = params.set('range_min', String(rangeMin));
    if (rangeMax !== undefined) params = params.set('range_max', String(rangeMax));
    return this.http.get<TimelineHeatmapResult>(`/api/archives/${archiveId}/folders/${folderId}/timeline-heatmap`, { params });
  }

  getFileContent(fileId: string): Observable<{ file_id: string; content: string | null }> {
    return this.http.get<{ file_id: string; content: string | null }>(`/api/files/${fileId}/content`);
  }

  listFiles(archiveId: string, params: ListFilesParams): Observable<ListFilesResponse> {
    const httpParams: Record<string, string | string[]> = {};
    if (params.folder_path) httpParams['folder_path'] = params.folder_path;
    if (params.sort_by) httpParams['sort_by'] = params.sort_by;
    if (params.sort_dir) httpParams['sort_dir'] = params.sort_dir;
    if (params.mime_types?.length) httpParams['mime_types'] = params.mime_types;
    if (params.categories?.length) httpParams['categories'] = params.categories;
    if (params.languages?.length) httpParams['languages'] = params.languages;
    if (params.entities?.length) httpParams['entities'] = params.entities;
    if (params.topics?.length) httpParams['topics'] = params.topics;
    if (params.cursor_id) httpParams['cursor_id'] = params.cursor_id;
    if (params.cursor_value) httpParams['cursor_value'] = params.cursor_value;
    return this.http.get<ListFilesResponse>(`/api/archives/${archiveId}/files`, { params: httpParams });
  }

  autocompleteEntities(archiveId: string, entityType: string, prefix: string): Observable<AutocompleteResponse> {
    return this.http.get<AutocompleteResponse>(`/api/archives/${archiveId}/autocomplete/entities`, {
      params: { entity_type: entityType, prefix },
    });
  }

  autocompleteTopics(archiveId: string, prefix: string): Observable<AutocompleteResponse> {
    return this.http.get<AutocompleteResponse>(`/api/archives/${archiveId}/autocomplete/topics`, {
      params: { prefix },
    });
  }

  deleteArchive(archiveId: string): Observable<void> {
    return this.http.delete<void>(`/api/archives/${archiveId}`);
  }

  startAnalysis(
    archiveId: string,
    analysis: { type: string; model: string }[],
  ): Observable<{ task_ids: string[] }> {
    return this.http.post<{ task_ids: string[] }>('/api/analysis/start', {
      archiveId,
      analysis,
    });
  }

}
