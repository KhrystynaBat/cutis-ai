import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Observable, catchError, firstValueFrom, map, of, tap } from 'rxjs';

import {
  HOME_BY_ROLE,
  LoginPending,
  Profile,
  ProfileUpdate,
  greeting,
  isLoginPending,
} from './auth.models';

export interface EmailChangePending {
  pendingEmailMasked: string;
  expiresAt: string;
}

export interface EmailChangeConfirmed {
  emailMasked: string;
  signedIn: boolean;
}

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly userSig = signal<Profile | null>(null);

  readonly user = this.userSig.asReadonly();
  readonly isLoggedIn = computed(() => this.userSig() !== null);
  readonly greeting = computed(() => greeting(this.userSig()));
  readonly homeUrl = computed(() => {
    const u = this.userSig();
    return u ? HOME_BY_ROLE[u.role] : '/login';
  });

  load(): Promise<Profile | null> {
    return firstValueFrom(
      this.http.get<Profile>('/api/v1/auth/me').pipe(
        tap((u) => this.userSig.set(u)),
        catchError(() => {
          this.userSig.set(null);
          return of(null);
        }),
      ),
    );
  }

  login(email: string, password: string): Observable<Profile | LoginPending> {
    return this.http.post<Profile | LoginPending>('/api/v1/auth/login', { email, password }).pipe(
      tap((r) => {
        if (!isLoginPending(r)) this.userSig.set(r);
      }),
    );
  }

  confirmLogin(token: string): Observable<Profile> {
    return this.http
      .post<Profile>('/api/v1/auth/login/confirm', { token })
      .pipe(tap((u) => this.userSig.set(u)));
  }

  resendLoginLink(): Observable<LoginPending> {
    return this.http.post<LoginPending>('/api/v1/auth/login/resend', {});
  }

  logout(): Observable<void> {
    return this.http.post<void>('/api/v1/auth/logout', {}).pipe(
      catchError(() => of(undefined)),
      tap(() => this.userSig.set(null)),
      map(() => undefined),
    );
  }

  changePassword(currentPassword: string, newPassword: string): Observable<void> {
    return this.http.post<void>('/api/v1/auth/change-password', { currentPassword, newPassword });
  }

  setPasswordWithToken(token: string, newPassword: string): Observable<void> {
    return this.http.post<void>('/api/v1/auth/set-password', { token, newPassword });
  }

  updateProfile(body: ProfileUpdate): Observable<Profile> {
    return this.http.patch<Profile>('/api/v1/auth/me', body).pipe(tap((u) => this.userSig.set(u)));
  }

  requestEmailChange(newEmail: string, currentPassword: string): Observable<EmailChangePending> {
    return this.http
      .post<EmailChangePending>('/api/v1/auth/me/email-change', { newEmail, currentPassword })
      .pipe(
        tap((r) => {
          const u = this.userSig();
          if (u) this.userSig.set({ ...u, pendingEmailMasked: r.pendingEmailMasked });
        }),
      );
  }

  cancelEmailChange(): Observable<void> {
    return this.http.delete<void>('/api/v1/auth/me/email-change').pipe(
      tap(() => {
        const u = this.userSig();
        if (u) this.userSig.set({ ...u, pendingEmailMasked: null });
      }),
    );
  }

  confirmEmailChange(token: string): Observable<EmailChangeConfirmed> {
    return this.http.post<EmailChangeConfirmed>('/api/v1/auth/email-change/confirm', { token });
  }

  clear(): void {
    this.userSig.set(null);
  }
}
