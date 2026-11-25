import { Component, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import {
  MAT_DIALOG_DATA,
  MatDialog,
  MatDialogModule,
  MatDialogRef,
} from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Observable, finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { AuthService } from '../../core/auth/auth.service';

export interface EmailChangeDialogData {
  newEmail: string;
}

export type EmailChangeDialogResult =
  { sent: true; pendingEmailMasked: string } | { sent: false; code: string; message: string };

@Component({
  selector: 'app-email-change-dialog',
  imports: [
    ReactiveFormsModule,
    MatDialogModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
  ],
  template: `
    <h2 mat-dialog-title>Підтвердіть зміну електронної пошти</h2>
    <form [formGroup]="form" (ngSubmit)="confirm()" novalidate>
      <mat-dialog-content>
        <p class="intro">
          Нова адреса: <strong>{{ data.newEmail }}</strong
          >. Щоб змінити адресу для входу, введіть поточний пароль. На нову адресу ми надішлемо лист
          із посиланням; доки ви його не відкриєте, вхід і листи — на поточну адресу.
        </p>
        <mat-form-field appearance="outline">
          <mat-label>Поточний пароль</mat-label>
          <input
            matInput
            type="password"
            formControlName="currentPassword"
            autocomplete="current-password"
          />
          @if (form.controls.currentPassword.hasError('wrong')) {
            <mat-error>Поточний пароль невірний</mat-error>
          } @else {
            <mat-error>Вкажіть поточний пароль</mat-error>
          }
        </mat-form-field>
        @if (error(); as e) {
          <p class="dl-error-text" role="alert">{{ e }}</p>
        }
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button type="button" mat-dialog-close>Скасувати</button>
        <button mat-flat-button type="submit" [disabled]="submitting()">Підтвердити</button>
      </mat-dialog-actions>
    </form>
  `,
  styles: `
    mat-form-field {
      width: 100%;
    }
    .intro {
      margin: 0 0 16px;
      overflow-wrap: anywhere;
    }
  `,
})
export class EmailChangeDialog {
  readonly data = inject<EmailChangeDialogData>(MAT_DIALOG_DATA);
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly ref =
    inject<MatDialogRef<EmailChangeDialog, EmailChangeDialogResult>>(MatDialogRef);

  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = this.fb.group({ currentPassword: ['', Validators.required] });

  confirm(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.submitting.set(true);
    this.error.set(null);
    this.auth
      .requestEmailChange(this.data.newEmail, this.form.getRawValue().currentPassword)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: (r) => this.ref.close({ sent: true, pendingEmailMasked: r.pendingEmailMasked }),
        error: (e) => {
          const err = parseApiError(e);
          if (err.code === 'WRONG_PASSWORD') {
            const c = this.form.controls.currentPassword;
            c.setErrors({ wrong: true });
            c.markAsTouched();
          } else if (err.code === 'EMAIL_TAKEN' || err.code === 'SAME_EMAIL') {
            this.ref.close({ sent: false, code: err.code, message: err.message });
          } else {
            this.error.set(err.message);
          }
        },
      });
  }
}

export function openEmailChange(
  dialog: MatDialog,
  newEmail: string,
): Observable<EmailChangeDialogResult | undefined> {
  return dialog
    .open<EmailChangeDialog, EmailChangeDialogData, EmailChangeDialogResult>(EmailChangeDialog, {
      data: { newEmail },
      width: '520px',
      maxWidth: '95vw',
      autoFocus: 'first-tabbable',
    })
    .afterClosed();
}
