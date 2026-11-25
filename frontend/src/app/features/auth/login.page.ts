import { Component, DestroyRef, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { HOME_BY_ROLE, LoginPending, isLoginPending } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';

export const RESEND_COOLDOWN_SECONDS = 60;

@Component({
  selector: 'app-login-page',
  imports: [
    ReactiveFormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
  ],
  templateUrl: './login.page.html',
  styleUrl: './login.page.scss',
})
export class LoginPage {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  /** Query params (component input binding). */
  readonly returnUrl = input<string | undefined>();
  readonly expired = input<string | undefined>();
  readonly passwordSet = input<string | undefined>();

  readonly form = this.fb.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required]],
  });
  readonly hidePassword = signal(true);
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);

  readonly pending = signal<LoginPending | null>(null);
  readonly resendIn = signal(0);
  readonly resending = signal(false);
  readonly resendInfo = signal<string | null>(null);
  private timer: ReturnType<typeof setInterval> | null = null;

  constructor() {
    inject(DestroyRef).onDestroy(() => this.stopTimer());
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    if (this.submitting()) return;
    this.submitting.set(true);
    this.error.set(null);
    const { email, password } = this.form.getRawValue();
    this.auth
      .login(email, password)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: (r) => {
          if (isLoginPending(r)) {
            this.form.controls.password.reset();
            this.showPending(r);
          } else {
            void this.router.navigateByUrl(this.safeReturnUrl() ?? HOME_BY_ROLE[r.role]);
          }
        },
        error: (e) => {
          this.error.set(parseApiError(e).message);
          this.form.controls.password.reset();
        },
      });
  }

  resend(): void {
    if (this.resendIn() > 0 || this.resending()) return;
    this.resending.set(true);
    this.error.set(null);
    this.resendInfo.set(null);
    this.auth
      .resendLoginLink()
      .pipe(finalize(() => this.resending.set(false)))
      .subscribe({
        next: (r) => {
          this.showPending(r);
          this.resendInfo.set('Лист надіслано ще раз.');
        },
        error: (e) => this.error.set(parseApiError(e).message),
      });
  }

  backToLogin(): void {
    this.stopTimer();
    this.pending.set(null);
    this.error.set(null);
    this.resendInfo.set(null);
  }

  private showPending(r: LoginPending): void {
    this.pending.set(r);
    this.startTimer();
  }

  private startTimer(): void {
    this.stopTimer();
    this.resendIn.set(RESEND_COOLDOWN_SECONDS);
    this.timer = setInterval(() => {
      const left = this.resendIn() - 1;
      this.resendIn.set(Math.max(0, left));
      if (left <= 0) this.stopTimer();
    }, 1000);
  }

  private stopTimer(): void {
    if (this.timer !== null) clearInterval(this.timer);
    this.timer = null;
  }

  private safeReturnUrl(): string | null {
    const url = this.returnUrl();
    return url && url.startsWith('/') && !url.startsWith('//') && url !== '/' ? url : null;
  }
}
