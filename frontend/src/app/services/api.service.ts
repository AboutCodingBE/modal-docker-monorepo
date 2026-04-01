import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../../environments/environment';

export interface HealthStatus {
  status: string;
  tika_status?: number;
  agent_status?: number;
  detail?: string;
}

@Injectable({
  providedIn: 'root',
})
export class ApiService {
  private apiUrl = environment.apiUrl;

  constructor(private http: HttpClient) {}

  checkHealth(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>(`${this.apiUrl}/health`);
  }

  checkTikaHealth(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>(`${this.apiUrl}/health/tika`);
  }

  checkAgentHealth(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>(`${this.apiUrl}/health/agent`);
  }
}
