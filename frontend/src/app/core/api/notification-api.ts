import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { Page } from './admin-users-api';

export interface AppNotification {
  id: string;
  type: string;
  title: string;
  message: string;
  isRead: boolean;
  createdAt: string;
  readAt: string | null;
  referral: { id: string; referralNumber: string; caseId: string } | null;
}

@Injectable({ providedIn: 'root' })
export class NotificationApi {
  private readonly http = inject(HttpClient);

  list(q: {
    unreadOnly?: boolean;
    page: number;
    pageSize: number;
  }): Observable<Page<AppNotification>> {
    let params = new HttpParams().set('page', q.page).set('pageSize', q.pageSize);
    if (q.unreadOnly) params = params.set('unreadOnly', true);
    return this.http.get<Page<AppNotification>>('/api/v1/notifications', { params });
  }

  unreadCount(background = false): Observable<{ unread: number }> {
    const headers = background ? new HttpHeaders({ 'X-Background-Poll': '1' }) : undefined;
    return this.http.get<{ unread: number }>('/api/v1/notifications/unread-count', { headers });
  }

  markRead(id: string): Observable<AppNotification> {
    return this.http.post<AppNotification>(`/api/v1/notifications/${id}/read`, {});
  }

  markAllRead(): Observable<{ unread: number }> {
    return this.http.post<{ unread: number }>('/api/v1/notifications/read-all', {});
  }
}
