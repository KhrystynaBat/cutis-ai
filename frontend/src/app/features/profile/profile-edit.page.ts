import { Component, OnInit, inject, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { Observable, finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { Profile } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import {
  StaffExtraFields,
  staffExtraBody,
  staffExtraFormValue,
  staffExtraGroup,
} from '../../shared/forms/staff-extra-fields';
import { PHONE } from '../../shared/forms/validators';
import { openEmailChange } from './email-change-dialog';

const NAME_PATTERN = /\S/;

export const emailSentMessage = (masked: string) =>
  `Інші дані збережено. Щоб змінити електронну пошту, перейдіть за посиланням у листі, який ми надіслали на ${masked}.`;

@Component({
  selector: 'app-profile-edit-page',
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    StaffExtraFields,
  ],
  template: `
    <section class="dl-card profile" aria-labelledby="pe-title">
      <h2 id="pe-title" class="dl-page-title">Редагування профілю</h2>
      <form [formGroup]="form" (ngSubmit)="save()" novalidate>
        <section class="block" aria-labelledby="pe-personal">
          <h3 id="pe-personal">Особисті дані</h3>
          <div class="form-grid">
            <mat-form-field appearance="outline">
              <mat-label>Прізвище</mat-label>
              <input matInput formControlName="lastName" autocomplete="family-name" required />
              <mat-error>Вкажіть прізвище</mat-error>
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Ім'я</mat-label>
              <input matInput formControlName="firstName" autocomplete="given-name" required />
              <mat-error>Вкажіть ім'я</mat-error>
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>По батькові</mat-label>
              <input matInput formControlName="middleName" autocomplete="additional-name" />
              <mat-error>Некоректне значення</mat-error>
            </mat-form-field>
            <app-staff-extra-fields [group]="form.controls.extra" />
          </div>
        </section>

        <section class="block" aria-labelledby="pe-contacts">
          <h3 id="pe-contacts">Контактні дані</h3>
          <div class="form-grid">
            <mat-form-field appearance="outline">
              <mat-label>Електронна пошта</mat-label>
              <input matInput type="email" formControlName="email" autocomplete="email" required />
              @if (form.controls.email.hasError('taken')) {
                <mat-error>Ця адреса вже використовується</mat-error>
              } @else if (form.controls.email.hasError('email')) {
                <mat-error>Некоректна адреса електронної пошти</mat-error>
              } @else {
                <mat-error>Вкажіть електронну пошту</mat-error>
              }
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Телефон</mat-label>
              <input matInput type="tel" formControlName="phone" autocomplete="tel" />
              <mat-error>Цифри, пробіли, дужки, дефіс; можна з + на початку</mat-error>
            </mat-form-field>
          </div>
        </section>

        @if (error(); as e) {
          <p class="dl-error-text" role="alert">{{ e }}</p>
        }
        <div class="form-actions">
          <a mat-button routerLink="/profile">Скасувати</a>
          <button mat-flat-button type="submit" [disabled]="saving()">Зберегти</button>
        </div>
      </form>
    </section>
  `,
  styleUrl: './profile.scss',
})
export class ProfileEditPage implements OnInit {
  private readonly fb = inject(NonNullableFormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotifyService);

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
    email: ['', [Validators.required, Validators.email, Validators.maxLength(254)]],
    phone: ['', [Validators.pattern(PHONE)]],
    extra: staffExtraGroup(this.fb),
  });

  ngOnInit(): void {
    const u = this.auth.user();
    if (!u) return;
    this.form.patchValue({
      firstName: u.firstName ?? '',
      lastName: u.lastName ?? '',
      middleName: u.middleName ?? '',
      email: u.email,
      phone: u.phone ?? '',
      extra: staffExtraFormValue(u),
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const newEmail = this.form.controls.email.value.trim().toLowerCase();
    if (newEmail === this.auth.user()?.email) {
      this.saveOthers().subscribe({
        next: () => this.done('Зміни збережено'),
        error: (e) => this.error.set(parseApiError(e).message),
      });
      return;
    }
    openEmailChange(this.dialog, newEmail).subscribe((r) => {
      if (!r) return;
      if (!r.sent) {
        const c = this.form.controls.email;
        c.setErrors(r.code === 'EMAIL_TAKEN' ? { taken: true } : { email: true });
        c.markAsTouched();
        return;
      }
      this.saveOthers().subscribe({
        next: () => this.done(emailSentMessage(r.pendingEmailMasked), true),
        error: (e) => this.error.set(parseApiError(e).message),
      });
    });
  }

  private saveOthers(): Observable<Profile> {
    const { firstName, lastName, middleName, phone } = this.form.getRawValue();
    this.saving.set(true);
    this.error.set(null);
    return this.auth
      .updateProfile({
        firstName: firstName.trim(),
        lastName: lastName.trim(),
        middleName: middleName.trim() || null,
        phone: phone.trim() || null,
        ...staffExtraBody(this.form.controls.extra),
      })
      .pipe(finalize(() => this.saving.set(false)));
  }

  private done(message: string, long = false): void {
    if (long) this.notify.info(message);
    else this.notify.success(message);
    void this.router.navigate(['/profile']);
  }
}
