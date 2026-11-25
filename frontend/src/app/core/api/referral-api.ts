import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page } from './admin-users-api';
import { Analysis } from './analysis-api';
import { CaseImage, CaseStatus, PatientRef, ReferralStatus } from './doctor-api';

export interface PersonRef {
  id: string;
  firstName: string | null;
  lastName: string | null;
  middleName?: string | null;
  /** the referring doctor's phone, for the lab */
  phone?: string | null;
}

export interface ReferralSummary {
  id: string;
  referralNumber: string;
  status: ReferralStatus;
  createdAt: string;
  patient: PatientRef;
  doctor: PersonRef;
  assignee: PersonRef | null;
  caseId: string;
  bodyLocation: string;
  labAccessionNumber: string | null;
}

export interface LabResult {
  id: string;
  labAccessionNumber: string | null;
  histopathologyDiagnosis: string | null;
  histopathologyDescription: string | null;
  examinedAt: string | null;
  comment: string | null;
  isApproved: boolean;
  approvedAt: string | null;
  labSpecialist: PersonRef;
  updatedAt: string;
  /** only for an approved result */
  pdfUrl: string | null;
}

export interface LabResultInput {
  labAccessionNumber: string | null;
  histopathologyDiagnosis: string | null;
  histopathologyDescription: string | null;
  examinedAt: string | null;
  comment: string | null;
}

export interface Referral {
  id: string;
  referralNumber: string;
  status: ReferralStatus;
  reason: string;
  createdAt: string;
  startedAt: string | null;
  completedAt: string | null;
  patient: PatientRef;
  doctor: PersonRef;
  assignee: PersonRef | null;
  assignedAt: string | null;
  case: {
    id: string;
    status: CaseStatus;
    examinedAt: string;
    bodyLocation: string;
    clinicalDescription: string;
    doctorAssessment: string | null;
    image: CaseImage | null;
  };
  analysis: Analysis | null;
  analysisImageUrl: string | null;
  labAccessionNumber: string | null;
  labResult: LabResult | null;
}

export type LabScope = 'queue' | 'mine' | 'unassigned' | 'all';

export const LAB_SCOPE_LABELS: Record<LabScope, string> = {
  all: 'Усі направлення',
  queue: 'Мої та вільні',
  mine: 'Лише мої',
  unassigned: 'Вільні',
};

export interface ReferralQuery {
  search?: string;
  status?: ReferralStatus | '';
  caseStatus?: CaseStatus;
  scope?: LabScope;
  page: number;
  pageSize: number;
}

@Injectable({ providedIn: 'root' })
export class ReferralApi {
  private readonly http = inject(HttpClient);

  list(q: ReferralQuery): Observable<Page<ReferralSummary>> {
    let params = new HttpParams().set('page', q.page).set('pageSize', q.pageSize);
    if (q.search?.trim()) params = params.set('search', q.search.trim());
    if (q.status) params = params.set('status', q.status);
    if (q.caseStatus) params = params.set('caseStatus', q.caseStatus);
    if (q.scope) params = params.set('scope', q.scope);
    return this.http.get<Page<ReferralSummary>>('/api/v1/referrals', { params });
  }

  get(id: string): Observable<Referral> {
    return this.http.get<Referral>(`/api/v1/referrals/${id}`);
  }

  getLabResult(id: string): Observable<LabResult> {
    return this.http.get<LabResult>(`/api/v1/referrals/${id}/lab-result`);
  }

  start(id: string): Observable<Referral> {
    return this.http.post<Referral>(`/api/v1/referrals/${id}/start`, {});
  }

  reassign(id: string, labSpecialistId: string): Observable<Referral> {
    return this.http.post<Referral>(`/api/v1/referrals/${id}/reassign`, { labSpecialistId });
  }

  release(id: string): Observable<Referral> {
    return this.http.post<Referral>(`/api/v1/referrals/${id}/release`, {});
  }

  labSpecialists(): Observable<PersonRef[]> {
    return this.http.get<PersonRef[]>('/api/v1/lab/specialists');
  }

  saveDraft(id: string, body: LabResultInput): Observable<Referral> {
    return this.http.put<Referral>(`/api/v1/referrals/${id}/lab-result/draft`, body);
  }

  approve(id: string, body: LabResultInput): Observable<Referral> {
    return this.http.post<Referral>(`/api/v1/referrals/${id}/lab-result/approve`, body);
  }
}
