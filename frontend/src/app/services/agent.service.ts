import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable, of } from 'rxjs';
import { catchError, map } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export interface AgentStatus {
  available: boolean;
  detail?: string;
}

export interface FolderSelection {
  path: string;
  fileCount?: number;
}

@Injectable({
  providedIn: 'root',
})
export class AgentService {
  private agentUrl = environment.agentUrl;

  constructor(private http: HttpClient) {}

  /**
   * Check if the local agent is running.
   */
  checkHealth(): Observable<AgentStatus> {
    return this.http.get<{ status: string }>(`${this.agentUrl}/health`).pipe(
      map(() => ({ available: true })),
      catchError(() =>
        of({
          available: false,
          detail: 'Local agent is not running. Please start the agent to ingest archives.',
        })
      )
    );
  }

  /**
   * Trigger the native folder picker on the user's machine.
   * Returns the selected folder path.
   */
  pickFolder(): Observable<FolderSelection> {
    return this.http.post<FolderSelection>(`${this.agentUrl}/pick-folder`, {});
  }
}
