import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Sex } from '../auth/auth.models';

export type StaffRole = 'Doctor' | 'LabSpecialist';
export type UserStatus = 'Active' | 'Blocked' | 'Deactivated';
export type StatusAction = 'block' | 'unblock' | 'deactivate' | 'reactivate';

export interface AdminUser {
  id: string;
  firstName: string;
  lastName: string;
  middleName?: string | null;
  phone?: string | null;
  birthDate?: string | null;
  sex?: Sex | null;
  email: string;
  role: StaffRole;
  status: UserStatus;
  hasPassword: boolean;
  createdAt: string;
  lastLoginAt: string | null;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  pageSize: number;
}

export interface PasswordToken {
  token: string;
  expiresAt: string;
  purpose: 'Invitation' | 'PasswordReset';
  emailQueued?: boolean;
}

export interface UserQuery {
  search?: string;
  role?: StaffRole | '';
  status?: UserStatus | '';
  page: number;
  pageSize: number;
}

export interface UserInput {
  firstName: string;
  lastName: string;
  middleName?: string | null;
  phone?: string | null;
  birthDate?: string | null;
  sex?: Sex | null;
  email: string;
  role: StaffRole;
  isActive?: boolean;
}

export const STATUS_LABELS: Record<UserStatus, string> = {
  Active: 'Активний',
  Blocked: 'Заблокований',
  Deactivated: 'Деактивований',
};

@Injectable({ providedIn: 'root' })
export class AdminUsersApi {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1/admin/users';

  list(q: UserQuery): Observable<Page<AdminUser>> {
    let params = new HttpParams().set('page', q.page).set('pageSize', q.pageSize);
    if (q.search?.trim()) params = params.set('search', q.search.trim());
    if (q.role) params = params.set('role', q.role);
    if (q.status) params = params.set('status', q.status);
    return this.http.get<Page<AdminUser>>(this.base, { params });
  }

  get(id: string): Observable<AdminUser> {
    return this.http.get<AdminUser>(`${this.base}/${id}`);
  }

  create(body: UserInput): Observable<{ user: AdminUser; invitation: PasswordToken }> {
    return this.http.post<{ user: AdminUser; invitation: PasswordToken }>(this.base, body);
  }

  update(id: string, body: Partial<UserInput>): Observable<AdminUser> {
    return this.http.patch<AdminUser>(`${this.base}/${id}`, body);
  }

  setStatus(id: string, action: StatusAction): Observable<AdminUser> {
    return this.http.post<AdminUser>(`${this.base}/${id}/${action}`, {});
  }

  issuePasswordLink(id: string): Observable<PasswordToken> {
    return this.http.post<PasswordToken>(`${this.base}/${id}/password-reset`, {});
  }

  delete(id: string): Observable<void> {
    return this.http.delete<void>(`${this.base}/${id}`);
  }
}

export function passwordLink(token: string, origin = window.location.origin): string {
  return `${origin}/set-password#token=${encodeURIComponent(token)}`;
}
