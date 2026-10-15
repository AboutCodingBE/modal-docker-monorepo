import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface LiteralSnippet {
  text: string;
  match_offset: number;
  highlight_start: number;
  highlight_end: number;
}

export interface LiteralSearchResult {
  id: string;
  name: string;
  relative_path: string;
  snippets: LiteralSnippet[];
}

export interface LiteralSearchResponse {
  files: LiteralSearchResult[];
  has_next: boolean;
  next_cursor_id: string | null;
  next_cursor_value: string | null;
}

@Injectable({ providedIn: 'root' })
export class LiteralSearchService {
  constructor(private http: HttpClient) {}

  search(
    archiveId: string,
    query: string,
    cursorId?: string | null,
    cursorValue?: string | null,
  ): Observable<LiteralSearchResponse> {
    const params: Record<string, string> = { q: query };
    if (cursorId) params['cursor_id'] = cursorId;
    if (cursorValue) params['cursor_value'] = cursorValue;
    return this.http.get<LiteralSearchResponse>(
      `/api/archives/${archiveId}/files/search`,
      { params },
    );
  }
}
