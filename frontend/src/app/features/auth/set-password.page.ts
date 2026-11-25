import { Component, computed, OnInit, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import {
  CommonPasswords,
  passwordErrorText,
  passwordHint,
  passwordPolicyValidator,
  passwordsMatch,
} from '../../shared/forms/password';
import { PasswordStrength } from '../../shared/forms/password-strength';

@Component({
  selector: 'app-set-password-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatIconModule,
    PasswordStrength,
  ],
  template: `
    <main class="page">
      <section class="dl-card dl-narrow" aria-labelledby="sp-title">
        <h1 id="sp-title" class="dl-page-title">Встановлення пароля</h1>
        @if (!token()) {
          <p class="dl-banner" role="alert">
            Посилання неповне. Попросіть адміністратора надіслати нове.
          </p>
          <a mat-stroked-button routerLink="/login">До сторінки входу</a>
        } @else {
          <form class="dl-form" [formGroup]="form" (ngSubmit)="submit()" novalidate>
            <mat-form-field appearance="outline">
              <mat-label>Новий пароль</mat-label>
              <input
                matInput
                type="password"
                formControlName="newPassword"
                autocomplete="new-password"
              />
              @if (hint(); as h) {
                <mat-hint>{{ h }}</mat-hint>
              }
              <mat-error>{{ errorText('newPassword') }}</mat-error>
            </mat-form-field>
            <app-password-strength [password]="newPassword()" />
            <mat-form-field appearance="outline">
              <mat-label>Повторіть пароль</mat-label>
              <input
                matInput
                type="password"
                formControlName="confirmPassword"
                autocomplete="new-password"
              />
            </mat-form-field>
            @if (form.hasError('mismatch') && form.controls.confirmPassword.touched) {
              <p class="dl-error-text" role="alert">Паролі не збігаються</p>
            }
            @if (error(); as e) {
              <p class="dl-error-text" role="alert">{{ e }}</p>
            }
            <div class="dl-actions">
              <button mat-flat-button type="submit" [disabled]="submitting()">
                Зберегти пароль
              </button>
            </div>
          </form>
        }
      </section>
    </main>
  `,
  styles: `
    .page {
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 16px;
      box-sizing: border-box;
    }
  `,
})
export class SetPasswordPage implements OnInit {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  private readonly common = inject(CommonPasswords);
  readonly token = signal<string | null>(null);
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.fb.group(
    {
      newPassword: [
        '',
        passwordPolicyValidator(
          () => null,
          () => this.common.list(),
        ),
      ],
      confirmPassword: [''],
    },
    { validators: passwordsMatch },
  );
  readonly newPassword = toSignal(this.form.controls.newPassword.valueChanges, {
    initialValue: '',
  });
  readonly hint = computed(() => passwordHint(this.newPassword(), null, this.common.list()));

  ngOnInit(): void {
    const fragment = this.route.snapshot.fragment ?? '';
    const token = new URLSearchParams(fragment).get('token');
    this.token.set(token && token.length >= 20 ? token : null);
  }

  errorText(name: 'newPassword'): string | null {
    return passwordErrorText(this.form.controls[name]);
  }

  submit(): void {
    const token = this.token();
    this.form.controls.newPassword.updateValueAndValidity();
    if (!token || this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    this.auth
      .setPasswordWithToken(token, this.form.controls.newPassword.value)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: () => {
          this.auth.clear();
          void this.router.navigate(['/login'], { queryParams: { passwordSet: 1 } });
        },
        error: (e) => this.error.set(parseApiError(e).message),
      });
  }
}
