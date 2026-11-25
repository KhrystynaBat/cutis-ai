import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import {
  CommonPasswords,
  PasswordContext,
  passwordErrorText,
  passwordHint,
  passwordPolicyValidator,
  passwordsMatch,
} from '../../shared/forms/password';
import { PasswordStrength } from '../../shared/forms/password-strength';

@Component({
  selector: 'app-change-password-dialog',
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    PasswordStrength,
  ],
  template: `
    <h2 mat-dialog-title>Змінити пароль</h2>
    <form [formGroup]="form" (ngSubmit)="save()" novalidate>
      <mat-dialog-content>
        <mat-form-field appearance="outline">
          <mat-label>Поточний пароль</mat-label>
          <input
            matInput
            type="password"
            formControlName="currentPassword"
            autocomplete="current-password"
          />
          <mat-error>Вкажіть поточний пароль</mat-error>
        </mat-form-field>
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
          <mat-error>{{ newPasswordError() }}</mat-error>
        </mat-form-field>
        <app-password-strength [password]="newPassword()" [context]="context()" />
        <mat-form-field appearance="outline">
          <mat-label>Повторіть новий пароль</mat-label>
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
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" mat-dialog-close>Скасувати</button>
        <button mat-flat-button type="submit" [disabled]="submitting()">Змінити пароль</button>
      </mat-dialog-actions>
    </form>
  `,
  styles: `
    mat-form-field {
      width: 100%;
    }
  `,
})
export class ChangePasswordDialog {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly notify = inject(NotifyService);
  private readonly ref = inject(MatDialogRef<ChangePasswordDialog>);
  private readonly common = inject(CommonPasswords);

  readonly context = computed<PasswordContext | null>(() => {
    const u = this.auth.user();
    return u ? { email: u.email, names: [u.firstName, u.lastName, u.middleName] } : null;
  });
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.fb.group(
    {
      currentPassword: ['', Validators.required],
      newPassword: [
        '',
        [
          passwordPolicyValidator(
            () => this.context(),
            () => this.common.list(),
          ),
        ],
      ],
      confirmPassword: [''],
    },
    { validators: passwordsMatch },
  );
  readonly newPassword = toSignal(this.form.controls.newPassword.valueChanges, {
    initialValue: '',
  });
  readonly hint = computed(() =>
    passwordHint(this.newPassword(), this.context(), this.common.list()),
  );

  newPasswordError(): string | null {
    return passwordErrorText(this.form.controls.newPassword);
  }

  save(): void {
    this.form.controls.newPassword.updateValueAndValidity(); // the list may have loaded meanwhile
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { currentPassword, newPassword } = this.form.getRawValue();
    this.submitting.set(true);
    this.error.set(null);
    this.auth
      .changePassword(currentPassword, newPassword)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: () => {
          this.notify.success('Пароль змінено');
          this.ref.close(true);
        },
        error: (e) => this.error.set(parseApiError(e).message),
      });
  }
}
