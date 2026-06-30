import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
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
}

export interface NerResult {
  file_id: string;
  file_name: string;
  persons: string[];
  locations: string[];
  organisations: string[];
  misc: string[];
  total_entities: number;
}

export interface TopicsResult {
  file_id: string;
  file_name: string;
  topics: string[];
  total_topics: number;
}

export interface FolderFilesData {
  folder_id: string;
  folder_name: string;
  files: FolderFile[];
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

export interface AnalysisConfigEntry {
  type: string;
  model: string;
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

  getTopicsForFile(archiveId: string, fileId: string): Observable<TopicsResult> {
    return this.http.get<TopicsResult>(`/api/archives/${archiveId}/files/${fileId}/topics`);
  }

  getAnalysisConfiguration(): Observable<AnalysisConfigEntry[]> {
    return this.http.get<AnalysisConfigEntry[]>('/api/analysis/configuration');
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
