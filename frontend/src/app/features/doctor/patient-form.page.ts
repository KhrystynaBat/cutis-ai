import { Component, OnInit, inject, input, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { DoctorApi, PatientInput } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { notBlank, notFutureDate, todayIso, PHONE } from '../../shared/forms/validators';
import { provideIsoDates } from '../../shared/forms/iso-date-adapter';

@Component({
  selector: 'app-patient-form-page',
  providers: [provideIsoDates()],
  imports: [
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatDatepickerModule,
    MatInputModule,
    MatButtonModule,
    MatProgressBarModule,
  ],
  template: `
    <section class="dl-card dl-narrow" aria-labelledby="pf-title">
      <h2 id="pf-title" class="dl-page-title">
        {{ id() ? 'Редагування пацієнта' : 'Новий пацієнт' }}
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
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Дата народження</mat-label>
          <input
            matInput
            [matDatepicker]="birthPicker"
            formControlName="dateOfBirth"
            min="1900-01-01"
            [max]="today"
            placeholder="дд.мм.рррр"
            required
            (click)="birthPicker.open()"
          />
          <mat-datepicker-toggle matIconSuffix [for]="birthPicker" />
          <mat-datepicker #birthPicker startView="multi-year" />
          @if (form.controls.dateOfBirth.hasError('future')) {
            <mat-error>Дата не може бути в майбутньому</mat-error>
          } @else {
            <mat-error>Вкажіть дату народження</mat-error>
          }
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Електронна пошта</mat-label>
          <input matInput type="email" formControlName="email" autocomplete="off" />
          <mat-error>Некоректна адреса електронної пошти</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Телефон</mat-label>
          <input matInput type="tel" formControlName="phone" autocomplete="off" />
          <mat-error>Цифри, пробіли, дужки, дефіс; можна з + на початку</mat-error>
        </mat-form-field>
        <mat-form-field appearance="outline">
          <mat-label>Примітка</mat-label>
          <textarea matInput formControlName="notes" rows="3" maxlength="2000"></textarea>
          <mat-hint align="end">{{ form.controls.notes.value.length }}/2000</mat-hint>
        </mat-form-field>

        @if (error(); as e) {
          <p class="dl-error-text" role="alert">{{ e }}</p>
        }
        <div class="dl-actions">
          <button mat-flat-button type="submit" [disabled]="saving() || loading()">Зберегти</button>
          <a mat-button [routerLink]="id() ? ['/doctor/patients', id()] : '/doctor/patients'">
            Скасувати
          </a>
        </div>
      </form>
    </section>
  `,
})
export class PatientFormPage implements OnInit {
  readonly id = input<string>();

  private readonly fb = inject(NonNullableFormBuilder);
  private readonly api = inject(DoctorApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);

  readonly today = todayIso();
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);

  readonly form = this.fb.group({
    firstName: ['', [Validators.required, Validators.maxLength(100), notBlank]],
    lastName: ['', [Validators.required, Validators.maxLength(100), notBlank]],
    middleName: ['', [Validators.maxLength(100)]],
    dateOfBirth: ['', [Validators.required, notFutureDate]],
    email: ['', [Validators.email, Validators.maxLength(254)]],
    phone: ['', [Validators.pattern(PHONE)]],
    notes: ['', [Validators.maxLength(2000)]],
  });

  ngOnInit(): void {
    const id = this.id();
    if (!id) return;
    this.loading.set(true);
    this.api
      .getPatient(id)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (p) =>
          this.form.patchValue({
            firstName: p.firstName,
            lastName: p.lastName,
            middleName: p.middleName ?? '',
            dateOfBirth: p.dateOfBirth,
            email: p.email ?? '',
            phone: p.phone ?? '',
            notes: p.notes ?? '',
          }),
        error: (e) => {
          this.notify.error(e, 'Пацієнта не знайдено');
          void this.router.navigate(['/doctor/patients']);
        },
      });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const body: PatientInput = {
      firstName: v.firstName.trim(),
      lastName: v.lastName.trim(),
      middleName: v.middleName.trim() || null,
      dateOfBirth: v.dateOfBirth,
      email: v.email.trim() || null,
      phone: v.phone.trim() || null,
      notes: v.notes.trim() || null,
    };
    const id = this.id();
    const request = id ? this.api.updatePatient(id, body) : this.api.createPatient(body);
    this.saving.set(true);
    this.error.set(null);
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (p) => {
        this.notify.success(id ? 'Зміни збережено' : 'Пацієнта створено');
        void this.router.navigate(['/doctor/patients', p.id]);
      },
      error: (e) => this.error.set(parseApiError(e).message),
    });
  }
}
