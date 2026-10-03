import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export const EMBEDDING_MODEL = 'qwen3-embedding:0.6b';

export interface SearchChunkRaw {
  id: string;
  file_id: string;
  chunk_index: number;
  chunk_text: string;
  token_count: number | null;
  created_at: string;
  name: string;
  full_path: string;
  relative_path: string;
  distance: number;
}

export interface SearchChunk {
  id: string;
  chunk_index: number;
  chunk_text: string;
  distance: number;
  relevance: number; // (1 - distance) * 100, rounded
}

export interface SearchResultGroup {
  file_id: string;
  name: string;
  relative_path: string;
  best_relevance: number;
  chunks: SearchChunk[];
}

@Injectable({ providedIn: 'root' })
export class SemanticSearchService {
  constructor(private http: HttpClient) {}

  downloadEmbeddingModel(): Observable<{ download_id: string }> {
    return this.http.post<{ download_id: string }>('/api/models/ollama', { model: EMBEDDING_MODEL });
  }

  startEmbeddingAnalysis(archiveId: string): Observable<{ task_ids: string[] }> {
    return this.http.post<{ task_ids: string[] }>('/api/analysis/start', {
      archiveId,
      analysis: [{ type: 'EMBEDDING', model: EMBEDDING_MODEL }],
    });
  }

  search(archiveId: string, query: string, topN?: number): Observable<SearchChunkRaw[]> {
    const params: Record<string, string | number> = { q: query };
    if (topN !== undefined) params['top_n'] = topN;
    return this.http.get<SearchChunkRaw[]>(`/api/archives/${archiveId}/search`, { params });
  }

  groupResults(raw: SearchChunkRaw[]): SearchResultGroup[] {
    const groups = new Map<string, SearchResultGroup>();
    for (const item of raw) {
      const relevance = Math.round((1 - item.distance) * 100);
      if (!groups.has(item.file_id)) {
        groups.set(item.file_id, {
          file_id: item.file_id,
          name: item.name,
          relative_path: item.relative_path,
          best_relevance: relevance,
          chunks: [],
        });
      }
      groups.get(item.file_id)!.chunks.push({
        id: item.id,
        chunk_index: item.chunk_index,
        chunk_text: item.chunk_text,
        distance: item.distance,
        relevance,
      });
    }
    return Array.from(groups.values());
  }
}
