import { Component, OnInit, inject, input, signal, viewChild } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatAutocompleteModule } from '@angular/material/autocomplete';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { finalize, switchMap } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { DoctorApi, Patient } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { BODY_LOCATIONS } from '../../shared/body-locations';
import { PhotoPicker } from '../../shared/forms/photo-picker';
import { notBlank, notFutureDate, todayIso } from '../../shared/forms/validators';
import { FullNamePipe, fullName } from '../../shared/names';
import { provideIsoDates } from '../../shared/forms/iso-date-adapter';

@Component({
  selector: 'app-case-form-page',
  providers: [provideIsoDates()],
  imports: [
    FullNamePipe,
    ReactiveFormsModule,
    RouterLink,
    MatFormFieldModule,
    MatDatepickerModule,
    MatInputModule,
    MatSelectModule,
    MatAutocompleteModule,
    MatButtonModule,
    MatProgressBarModule,
    PhotoPicker,
  ],
  template: `
    <section class="dl-card dl-narrow" aria-labelledby="cf-title">
      <h2 id="cf-title" class="dl-page-title">
        {{ id() ? 'Редагування випадку' : 'Новий випадок' }}
      </h2>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
      }
      <form class="dl-form" [formGroup]="form" (ngSubmit)="save()" novalidate>
        @if (!id()) {
          <mat-form-field appearance="outline">
            <mat-label>Пацієнт</mat-label>
            <mat-select formControlName="patientId" required>
              @for (p of patients(); track p.id) {
                <mat-option [value]="p.id">
                  {{ p | fullName }}, {{ p.dateOfBirth.slice(0, 4) }} р.н.
                </mat-option>
              }
            </mat-select>
            @if (!loading() && patients().length === 0) {
              <mat-hint>
                Немає активних пацієнтів — <a routerLink="/doctor/patients/new">додайте пацієнта</a>
              </mat-hint>
            }
            <mat-error>Оберіть пацієнта</mat-error>
          </mat-form-field>
        } @else if (patientName()) {
          <p><span class="dl-muted">Пацієнт:</span> {{ patientName() }}</p>
        }

        <mat-form-field appearance="outline">
          <mat-label>Дата огляду</mat-label>
          <input
            matInput
            [matDatepicker]="examPicker"
            formControlName="examinedAt"
            [max]="today"
            placeholder="дд.мм.рррр"
            required
            (click)="examPicker.open()"
          />
          <mat-datepicker-toggle matIconSuffix [for]="examPicker" />
          <mat-datepicker #examPicker />
          @if (form.controls.examinedAt.hasError('future')) {
            <mat-error>Дата не може бути в майбутньому</mat-error>
          } @else {
            <mat-error>Вкажіть дату огляду</mat-error>
          }
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Локалізація на тілі</mat-label>
          <input
            matInput
            formControlName="bodyLocation"
            [matAutocomplete]="locations"
            maxlength="200"
            required
          />
          <mat-autocomplete #locations="matAutocomplete">
            @for (l of filteredLocations(); track l) {
              <mat-option [value]="l">{{ l }}</mat-option>
            }
          </mat-autocomplete>
          <mat-hint>Оберіть зі списку або введіть власний варіант</mat-hint>
          <mat-error>Вкажіть локалізацію</mat-error>
        </mat-form-field>

        <mat-form-field appearance="outline">
          <mat-label>Клінічний опис / скарги</mat-label>
          <textarea
            matInput
            formControlName="clinicalDescription"
            rows="5"
            maxlength="5000"
            required
          ></textarea>
          <mat-hint align="end">{{ form.controls.clinicalDescription.value.length }}/5000</mat-hint>
          <mat-error>Опишіть ураження або скарги</mat-error>
        </mat-form-field>

        @if (!id()) {
          <fieldset class="photo">
            <legend>Дерматоскопічне фото</legend>
            <app-photo-picker [checkDermoscopy]="true" (fileChange)="photo.set($event)" />
            @if (photoMissing()) {
              <p class="dl-error-text" role="alert">Додайте фото</p>
            }
          </fieldset>
        }

        @if (error(); as e) {
          <p class="dl-error-text" role="alert">{{ e }}</p>
        }
        <div class="dl-actions">
          <button
            mat-flat-button
            type="submit"
            [disabled]="saving() || loading() || !!picker()?.blocksSave()"
          >
            {{ id() ? 'Зберегти' : 'Створити' }}
          </button>
          <a mat-button [routerLink]="id() ? ['/doctor/cases', id()] : '/doctor/cases'"
            >Скасувати</a
          >
        </div>
        @if (saving()) {
          <mat-progress-bar mode="indeterminate" aria-label="Збереження" />
        }
      </form>
    </section>
  `,
  styles: `
    .photo {
      border: none;
      padding: 0;
      margin: 4px 0 12px;
    }
    legend {
      margin-bottom: 8px;
      color: var(--dl-text-muted);
    }
  `,
})
export class CaseFormPage implements OnInit {
  /** Route param in edit mode. */
  readonly id = input<string>();
  readonly patientId = input<string>();

  private readonly fb = inject(NonNullableFormBuilder);
  private readonly api = inject(DoctorApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);

  readonly today = todayIso();
  readonly patients = signal<Patient[]>([]);
  readonly patientName = signal('');
  readonly photo = signal<File | null>(null);
  protected readonly picker = viewChild(PhotoPicker);
  readonly photoMissing = signal(false);
  readonly loading = signal(false);
  readonly saving = signal(false);
  readonly error = signal<string | null>(null);
  readonly filteredLocations = signal(BODY_LOCATIONS);

  readonly form = this.fb.group({
    patientId: ['', Validators.required],
    examinedAt: [todayIso(), [Validators.required, notFutureDate]],
    bodyLocation: ['', [Validators.required, Validators.maxLength(200), notBlank]],
    clinicalDescription: ['', [Validators.required, Validators.maxLength(5000), notBlank]],
  });

  constructor() {
    this.form.controls.bodyLocation.valueChanges.subscribe((v) => {
      const q = v.trim().toLowerCase();
      this.filteredLocations.set(BODY_LOCATIONS.filter((l) => l.toLowerCase().includes(q)));
    });
  }

  ngOnInit(): void {
    const id = this.id();
    this.loading.set(true);
    if (id) {
      this.form.controls.patientId.disable();
      this.api
        .getCase(id)
        .pipe(finalize(() => this.loading.set(false)))
        .subscribe({
          next: (c) => {
            if (!c.isEditable) {
              this.notify.info('Випадок можна редагувати лише у статусі «Відкритий»');
              void this.router.navigate(['/doctor/cases', id]);
              return;
            }
            this.patientName.set(fullName(c.patient));
            this.form.patchValue(c);
          },
          error: (e) => {
            this.notify.error(e, 'Випадок не знайдено');
            void this.router.navigate(['/doctor/cases']);
          },
        });
      return;
    }
    this.api
      .listPatients({ page: 1, pageSize: 100 })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (r) => {
          this.patients.set(r.items);
          const pre = this.patientId();
          if (pre && r.items.some((p) => p.id === pre)) {
            this.form.controls.patientId.setValue(pre);
          }
        },
        error: (e) => this.notify.error(e, 'Не вдалося завантажити пацієнтів'),
      });
  }

  save(): void {
    const id = this.id();
    this.photoMissing.set(!id && !this.photo());
    if (this.form.invalid || this.photoMissing()) {
      this.form.markAllAsTouched();
      return;
    }
    if (!id && this.picker()?.blocksSave()) return;
    const v = this.form.getRawValue();
    const body = {
      examinedAt: v.examinedAt,
      bodyLocation: v.bodyLocation.trim(),
      clinicalDescription: v.clinicalDescription.trim(),
    };
    this.saving.set(true);
    this.error.set(null);

    if (id) {
      this.api
        .updateCase(id, body)
        .pipe(finalize(() => this.saving.set(false)))
        .subscribe({
          next: () => {
            this.notify.success('Зміни збережено');
            void this.router.navigate(['/doctor/cases', id]);
          },
          error: (e) => this.error.set(parseApiError(e).message),
        });
      return;
    }

    const photo = this.photo() as File;
    const confirmed = this.picker()?.confirmNonDermoscopic() ?? false;
    let createdId: string | null = null;
    this.api
      .createCase({ ...body, patientId: v.patientId })
      .pipe(
        switchMap((c) => {
          createdId = c.id;
          return this.api.uploadImage(c.id, photo, confirmed);
        }),
        finalize(() => this.saving.set(false)),
      )
      .subscribe({
        next: () => {
          this.notify.success('Випадок створено');
          void this.router.navigate(['/doctor/cases', createdId]);
        },
        error: (e) => {
          if (createdId) {
            this.notify.error(e, 'Випадок створено, але фото не завантажено');
            void this.router.navigate(['/doctor/cases', createdId]);
          } else {
            this.error.set(parseApiError(e).message);
          }
        },
      });
  }
}
