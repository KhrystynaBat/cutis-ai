import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export interface HealthStatus {
  status: string;
  database?: string;
}

@Injectable({ providedIn: 'root' })
export class SystemApi {
  private readonly http = inject(HttpClient);

  live(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>('/api/v1/health/live');
  }

  ready(): Observable<HealthStatus> {
    return this.http.get<HealthStatus>('/api/v1/health/ready');
  }
}
