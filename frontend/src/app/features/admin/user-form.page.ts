import { Component, OnInit, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatRadioModule } from '@angular/material/radio';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { AdminUsersApi, StaffRole } from '../../core/api/admin-users-api';
import { parseApiError } from '../../core/api/api-error';
import { ROLE_LABELS } from '../../core/auth/auth.models';
import { NotifyService } from '../../core/notify.service';
import { PasswordLinkDialog } from './password-link-dialog';

import { fullName } from '../../shared/names';

import {
  StaffExtraFields,
  staffExtraBody,
  staffExtraFormValue,
  staffExtraGroup,
} from '../../shared/forms/staff-extra-fields';
import { PHONE } from '../../shared/forms/validators';

const NAME_PATTERN = /\S/;

@Component({
  selector: 'app-user-form-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatInputModule,
    MatRadioModule,
    MatCheckboxModule,
    MatButtonModule,
    MatProgressBarModule,
    StaffExtraFields,
  ],
  template: `
    <section class="dl-card dl-narrow" aria-labelledby="form-title">
      <h2 id="form-title" class="dl-page-title">
        {{ id() ? 'Редагування користувача' : 'Новий користувач' }}
      </h2>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
      }
      <form class="dl-form" [formGroup]="form" (ngSubmit)="save()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>Прізвище</mat-label>
          <input matInput formControlName="lastName" autocomplete="off" required />
          <mat-error>Вкажіть прізвище</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Ім'я</mat-label>
          <input matInput formControlName="firstName" autocomplete="off" required />
          <mat-error>Вкажіть ім'я</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>По батькові</mat-label>
          <input matInput formControlName="middleName" autocomplete="off" />
          <mat-error>Некоректне значення</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Телефон</mat-label>
          <input matInput type="tel" formControlName="phone" autocomplete="off" />
          <mat-error>Цифри, пробіли, дужки, дефіс; можна з + на початку</mat-error>
        </mat-form-field>
        <app-staff-extra-fields [group]="form.controls.extra" />
        <mat-form-field appearance="outline">
          <mat-label>Електронна пошта</mat-label>
          <input matInput type="email" formControlName="email" autocomplete="off" required />
          @if (form.controls.email.hasError('taken')) {
            <mat-error>Ця адреса вже використовується</mat-error>
          } @else if (form.controls.email.hasError('email')) {
            <mat-error>Некоректна адреса електронної пошти</mat-error>
          } @else {
            <mat-error>Вкажіть електронну пошту</mat-error>
          }
        </mat-form-field>

        <fieldset class="roles">
          <legend>Роль</legend>
          <mat-radio-group formControlName="role" aria-label="Роль">
            <mat-radio-button value="Doctor">{{ roleLabels.Doctor }}</mat-radio-button>
            <mat-radio-button value="LabSpecialist">{{
              roleLabels.LabSpecialist
            }}</mat-radio-button>
          </mat-radio-group>
        </fieldset>

        @if (!id()) {
          <mat-checkbox formControlName="isActive">Активний одразу після створення</mat-checkbox>
        }

        @if (error(); as e) {
          <p class="dl-error-text" role="alert">{{ e }}</p>
        }
        <div class="dl-actions">
          <button mat-flat-button type="submit" [disabled]="saving() || loading()">Зберегти</button>
          <a mat-button routerLink="/admin/users">Скасувати</a>
        </div>
      </form>
    </section>
  `,
  styles: `
    .roles {
      border: none;
      padding: 0;
      margin: 0 0 12px;
    }
    legend {
      margin-bottom: 4px;
      color: var(--dl-text-muted);
    }
  `,
})
export class UserFormPage implements OnInit {
  readonly id = input<string>();

  private readonly fb = inject(NonNullableFormBuilder);
  private readonly api = inject(AdminUsersApi);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotifyService);

  readonly roleLabels = ROLE_LABELS;
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    firstName: [
      '',
      [Validators.required, Validators.maxLength(100), Validators.pattern(NAME_PATTERN)],
    ],
    lastName: [
      '',
      [Validators.required, Validators.maxLength(100), Validators.pattern(NAME_PATTERN)],
    ],
    middleName: ['', [Validators.maxLength(100), Validators.pattern(NAME_PATTERN)]],
    phone: ['', [Validators.pattern(PHONE)]],
    email: ['', [Validators.required, Validators.email, Validators.maxLength(254)]],
    role: ['Doctor' as StaffRole, Validators.required],
    isActive: [true],
    extra: staffExtraGroup(this.fb),
  });

  ngOnInit(): void {
    const id = this.id();
    if (!id) return;
    this.loading.set(true);
    this.api
      .get(id)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (u) => {
          this.form.patchValue({
            ...u,
            middleName: u.middleName ?? '',
            phone: u.phone ?? '',
            extra: staffExtraFormValue(u),
          });
        },
        error: (e) => {
          this.notify.error(e, 'Користувача не знайдено');
          void this.router.navigate(['/admin/users']);
        },
      });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const { firstName, lastName, middleName, phone, email, role, isActive } =
      this.form.getRawValue();
    const body = {
      firstName: firstName.trim(),
      lastName: lastName.trim(),
      middleName: middleName.trim() || null,
      phone: phone.trim() || null,
      ...staffExtraBody(this.form.controls.extra),
      email,
      role,
    };
    const id = this.id();
    this.saving.set(true);
    this.error.set(null);
    const onError = (e: unknown) => {
      const err = parseApiError(e);
      if (err.code === 'EMAIL_TAKEN') {
        this.form.controls.email.setErrors({ taken: true });
        this.form.controls.email.markAsTouched();
      } else {
        this.error.set(err.message);
      }
    };

    if (id) {
      this.api
        .update(id, body)
        .pipe(finalize(() => this.saving.set(false)))
        .subscribe({
          next: () => {
            this.notify.success('Зміни збережено');
            void this.router.navigate(['/admin/users']);
          },
          error: onError,
        });
      return;
    }
    this.api
      .create({ ...body, isActive })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: ({ user, invitation }) => {
          this.notify.success('Користувача створено');
          this.dialog
            .open(PasswordLinkDialog, {
              data: { userName: fullName(user), token: invitation },
              width: '560px',
              disableClose: true,
            })
            .afterClosed()
            .subscribe(() => void this.router.navigate(['/admin/users']));
        },
        error: onError,
      });
  }
}
