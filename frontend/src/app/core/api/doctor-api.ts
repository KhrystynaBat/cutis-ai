import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page } from './admin-users-api';

export type CaseStatus = 'Open' | 'FollowUpPlanned' | 'Referred' | 'Closed';

export const CASE_STATUS_LABELS: Record<CaseStatus, string> = {
  Open: 'Відкритий',
  FollowUpPlanned: 'Заплановано контроль',
  Referred: 'Направлено',
  Closed: 'Закритий',
};

export type CaseDecision = 'Close' | 'FollowUp' | 'Refer';
export type CaseAction = CaseDecision | 'Reopen';

export const DECISION_LABELS: Record<CaseDecision, string> = {
  Close: 'Завершити випадок',
  FollowUp: 'Запланувати контроль',
  Refer: 'Направити на гістопатологію',
};

export type ReferralStatus = 'Sent' | 'InProgress' | 'Completed';

export const REFERRAL_STATUS_LABELS: Record<ReferralStatus, string> = {
  Sent: 'Надіслано',
  InProgress: 'В роботі',
  Completed: 'Завершено',
};

export interface ReferralRef {
  id: string;
  referralNumber: string;
  status: ReferralStatus;
  createdAt: string;
}

export interface ReferralBrief extends ReferralRef {
  reason: string;
  analysisId: string | null;
}

export interface Patient {
  id: string;
  firstName: string;
  lastName: string;
  middleName?: string | null;
  dateOfBirth: string;
  age: number;
  email: string | null;
  phone: string | null;
  notes: string | null;
  isArchived: boolean;
  casesCount: number;
  lastVisit: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface PatientInput {
  firstName: string;
  lastName: string;
  middleName?: string | null;
  dateOfBirth: string;
  email: string | null;
  phone: string | null;
  notes: string | null;
}

export interface PatientRef {
  id: string;
  firstName: string;
  lastName: string;
  middleName?: string | null;
  dateOfBirth: string;
}

export interface CaseImage {
  id: string;
  originalFilename: string;
  mimeType: string;
  byteSize: number;
  uploadedAt: string;
  url: string;
  gateOverridden?: boolean;
}

export interface ImageCheck {
  passed: boolean;
  score: number | null;
}

export interface CaseSummary {
  id: string;
  patient: PatientRef;
  examinedAt: string;
  bodyLocation: string;
  status: CaseStatus;
  hasImage: boolean;
  /** latest completed AI analysis, if any */
  aiResult: { code: string; labelUk: string; score: number } | null;
  /** latest referral of the case */
  referral: ReferralRef | null;
  createdAt: string;
}

export interface CaseDetail extends CaseSummary {
  clinicalDescription: string;
  doctorAssessment: string | null;
  followUpDate: string | null;
  followUpNote: string | null;
  updatedAt: string;
  image: CaseImage | null;
  isEditable: boolean;
  decision: CaseDecision | null;
  referral: ReferralBrief | null;
  availableActions: CaseAction[];
}

export interface AssessmentInput {
  doctorAssessment?: string | null;
  decision?: CaseDecision | null;
  followUpDate?: string | null;
  followUpNote?: string | null;
  referralReason?: string | null;
}

export interface CaseInput {
  patientId: string;
  examinedAt: string;
  bodyLocation: string;
  clinicalDescription: string;
}

export interface Dashboard {
  patients: number;
  activeCases: number;
  pendingReferrals: number;
  readyResults: number;
  recentCases: CaseSummary[];
}

export interface PatientQuery {
  search?: string;
  includeArchived?: boolean;
  page: number;
  pageSize: number;
}

export interface CaseQuery {
  search?: string;
  status?: CaseStatus | '';
  patientId?: string;
  page: number;
  pageSize: number;
}

function params(q: object): HttpParams {
  let p = new HttpParams();
  for (const [k, v] of Object.entries(q)) {
    if (v !== undefined && v !== null && v !== '' && v !== false) {
      p = p.set(k, String(v).trim());
    }
  }
  return p;
}

@Injectable({ providedIn: 'root' })
export class DoctorApi {
  private readonly http = inject(HttpClient);

  dashboard(): Observable<Dashboard> {
    return this.http.get<Dashboard>('/api/v1/doctor/dashboard');
  }

  listPatients(q: PatientQuery): Observable<Page<Patient>> {
    return this.http.get<Page<Patient>>('/api/v1/patients', { params: params(q) });
  }

  getPatient(id: string): Observable<Patient> {
    return this.http.get<Patient>(`/api/v1/patients/${id}`);
  }

  createPatient(body: PatientInput): Observable<Patient> {
    return this.http.post<Patient>('/api/v1/patients', body);
  }

  updatePatient(id: string, body: Partial<PatientInput>): Observable<Patient> {
    return this.http.patch<Patient>(`/api/v1/patients/${id}`, body);
  }

  setPatientArchived(id: string, archived: boolean): Observable<Patient> {
    return this.http.post<Patient>(
      `/api/v1/patients/${id}/${archived ? 'archive' : 'unarchive'}`,
      {},
    );
  }

  listCases(q: CaseQuery): Observable<Page<CaseSummary>> {
    return this.http.get<Page<CaseSummary>>('/api/v1/cases', { params: params(q) });
  }

  getCase(id: string): Observable<CaseDetail> {
    return this.http.get<CaseDetail>(`/api/v1/cases/${id}`);
  }

  createCase(body: CaseInput): Observable<CaseDetail> {
    return this.http.post<CaseDetail>('/api/v1/cases', body);
  }

  updateCase(id: string, body: Partial<CaseInput>): Observable<CaseDetail> {
    return this.http.patch<CaseDetail>(`/api/v1/cases/${id}`, body);
  }

  saveAssessment(caseId: string, body: AssessmentInput): Observable<CaseDetail> {
    return this.http.patch<CaseDetail>(`/api/v1/cases/${caseId}/assessment`, body);
  }

  reopenCase(caseId: string): Observable<CaseDetail> {
    return this.http.post<CaseDetail>(`/api/v1/cases/${caseId}/reopen`, {});
  }

  uploadImage(caseId: string, file: File, confirmNonDermoscopic = false): Observable<CaseImage> {
    const form = new FormData();
    form.append('file', file, file.name);
    if (confirmNonDermoscopic) form.append('confirm_non_dermoscopic', 'true');
    return this.http.post<CaseImage>(`/api/v1/cases/${caseId}/images`, form);
  }

  checkImage(file: File): Observable<ImageCheck> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<ImageCheck>('/api/v1/images/check', form);
  }
}
