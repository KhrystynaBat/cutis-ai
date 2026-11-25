import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

export type AnalysisStatus = 'Queued' | 'Running' | 'Completed' | 'Failed';
export type XaiMethod = 'gradcam' | 'gradcam_pp';

export const XAI_METHOD_LABELS: Record<XaiMethod, string> = {
  gradcam: 'Grad-CAM',
  gradcam_pp: 'Grad-CAM++',
};

export const ANALYSIS_STATUS_LABELS: Record<AnalysisStatus | 'NotStarted', string> = {
  NotStarted: 'Не запускався',
  Queued: 'У черзі',
  Running: 'Виконується',
  Completed: 'Завершено',
  Failed: 'Помилка',
};

export interface ClassLabel {
  code: string;
  labelUk: string;
}

export interface ClassScore extends ClassLabel {
  score: number;
}

export interface XaiArtifact {
  id: string;
  method: XaiMethod;
  component: string;
  layerName: string;
  gridSize: number | null;
  status: 'Completed' | 'Failed';
  errorCode: string | null;
  reason: string | null;
  url: string | null;
}

export interface Analysis {
  id: string;
  caseId: string;
  imageId: string;
  status: AnalysisStatus;
  model: string;
  modelVersion: string | null;
  preprocessingVersion: string;
  predictedClass: ClassLabel | null;
  score: number | null;
  scores: ClassScore[];
  errorCode: string | null;
  errorMessage: string | null;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  xai: XaiArtifact[];
  imageGateOverridden?: boolean;
}

export interface AiStatus {
  status: 'ready' | 'loading' | 'unavailable';
  code: string | null;
  message: string;
  model: string;
  modelVersion: string | null;
  preprocessingVersion: string;
  components: string[];
  xaiMethods: XaiMethod[];
  maxConcurrentAnalyses: number;
  pendingAnalyses: number;
  /** image filter: ready | loading | unavailable */
  gateStatus?: 'ready' | 'loading' | 'unavailable';
}

export function isActive(a: Analysis | null | undefined): boolean {
  return !!a && (a.status === 'Queued' || a.status === 'Running');
}

@Injectable({ providedIn: 'root' })
export class AnalysisApi {
  private readonly http = inject(HttpClient);

  start(caseId: string): Observable<Analysis> {
    return this.http.post<Analysis>(`/api/v1/cases/${caseId}/analyses`, {});
  }

  list(caseId: string): Observable<Analysis[]> {
    return this.http.get<Analysis[]>(`/api/v1/cases/${caseId}/analyses`);
  }

  get(id: string): Observable<Analysis> {
    return this.http.get<Analysis>(`/api/v1/analyses/${id}`);
  }

  aiStatus(): Observable<AiStatus> {
    return this.http.get<AiStatus>('/api/v1/system/ai-status');
  }
}
