import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import {
  AbstractControl,
  NonNullableFormBuilder,
  ReactiveFormsModule,
  ValidationErrors,
  Validators,
} from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatExpansionModule } from '@angular/material/expansion';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatDatepickerModule } from '@angular/material/datepicker';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';
import { Observable, filter, finalize, switchMap } from 'rxjs';

import { LabResultInput, Referral, ReferralApi } from '../../core/api/referral-api';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import { AnalysisResult } from '../../shared/ai/analysis-result';
import { ConfirmDialog, ConfirmData } from '../../shared/dialogs/confirm-dialog';
import { notBlank, todayIso } from '../../shared/forms/validators';
import { LabResultView } from '../../shared/lab-result-view';
import { ReferralStatusChip } from '../../shared/referral-status-chip';
import { ReassignData, ReassignDialog } from './reassign-dialog';
import { FullNamePipe, ShortNamePipe } from '../../shared/names';
import { provideIsoDates } from '../../shared/forms/iso-date-adapter';

const ACCESSION = /^[\p{L}\p{N}_][\p{L}\p{N}_\-/.]*$/u;

function accessionNumber(c: AbstractControl): ValidationErrors | null {
  const v = typeof c.value === 'string' ? c.value.trim() : '';
  return !v || ACCESSION.test(v) ? null : { pattern: true };
}

const REQUIRED = [
  'labAccessionNumber',
  'histopathologyDiagnosis',
  'histopathologyDescription',
  'examinedAt',
] as const;

@Component({
  selector: 'app-lab-referral-detail-page',
  providers: [provideIsoDates()],
  imports: [
    FullNamePipe,
    ShortNamePipe,
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatDatepickerModule,
    MatInputModule,
    MatProgressBarModule,
    MatExpansionModule,
    AnalysisResult,
    LabResultView,
    ReferralStatusChip,
  ],
  template: `
    @if (referral(); as r) {
      <section class="dl-card" aria-labelledby="ref-title">
        <div class="dl-list-header">
          <h2 id="ref-title" class="dl-page-title">
            Направлення <span class="mono">{{ r.referralNumber }}</span>
          </h2>
          <app-referral-status [status]="r.status" />
        </div>
        <dl class="meta">
          <div>
            <dt>Дата направлення</dt>
            <dd>{{ r.createdAt | date: 'dd.MM.yyyy HH:mm' }}</dd>
          </div>
          <div>
            <dt>Лікар</dt>
            <dd>
              {{ r.doctor | fullName }}
              @if (r.doctor.phone) {
                <span class="dl-muted nowrap">· {{ r.doctor.phone }}</span>
              }
            </dd>
          </div>
          <div>
            <dt>Пацієнт</dt>
            <dd>
              {{ r.patient | fullName }}
              <span class="dl-muted">· {{ r.patient.dateOfBirth | date: 'dd.MM.yyyy' }}</span>
            </dd>
          </div>
          <div>
            <dt>Відповідальний</dt>
            <dd>
              @if (r.assignee; as a) {
                {{ a | fullName }}
                @if (mine()) {
                  <span class="dl-muted">(ви)</span>
                }
                <span class="dl-muted">· з {{ r.assignedAt | date: 'dd.MM.yyyy HH:mm' }}</span>
              } @else {
                <span class="dl-muted">не взято в роботу</span>
              }
            </dd>
          </div>
        </dl>
      </section>

      <section class="dl-card grid" aria-label="Клінічні дані">
        <div>
          <h3>Фото</h3>
          @if (r.case.image; as img) {
            <img
              [src]="img.url"
              alt="Дерматоскопічне фото, локалізація: {{ r.case.bodyLocation }}"
            />
          } @else {
            <p class="dl-muted">Фото не додано.</p>
          }
        </div>
        <div>
          <h3>Клінічна інформація</h3>
          <p><span class="dl-muted">Локалізація:</span> {{ r.case.bodyLocation }}</p>
          <p><span class="dl-muted">Огляд:</span> {{ r.case.examinedAt | date: 'dd.MM.yyyy' }}</p>
          <h4>Клінічний опис лікаря</h4>
          <p class="pre">{{ r.case.clinicalDescription }}</p>
          <h4>Клінічне питання / підстава направлення</h4>
          <p class="pre">{{ r.reason }}</p>
          @if (r.case.doctorAssessment) {
            <h4>Оцінка лікаря</h4>
            <p class="pre">{{ r.case.doctorAssessment }}</p>
          }
        </div>
      </section>

      <!-- the AI block is for reference only and starts collapsed -->
      <mat-expansion-panel class="ai-panel">
        <mat-expansion-panel-header>
          <mat-panel-title>Аналіз ШІ</mat-panel-title>
        </mat-expansion-panel-header>
        <ng-template matExpansionPanelContent>
          @if (r.analysis; as a) {
            <app-analysis-result [analysis]="a" [originalUrl]="r.analysisImageUrl ?? ''" />
          } @else {
            <p class="dl-muted">Направлення створено без аналізу ШІ.</p>
          }
        </ng-template>
      </mat-expansion-panel>

      <section class="dl-card" aria-labelledby="result-title">
        <h3 id="result-title">Гістопатологічний висновок</h3>
        @if (r.status === 'Completed' && r.labResult) {
          <p class="state ok" role="status">
            <mat-icon aria-hidden="true">verified</mat-icon>
            <span>
              Результат затверджено {{ r.labResult.approvedAt | date: 'dd.MM.yyyy HH:mm' }} ({{
                r.labResult.labSpecialist | shortName
              }}).
            </span>
          </p>
          <app-lab-result-view [result]="r.labResult" />
        } @else {
          @if (r.status === 'Sent') {
            <div class="state" role="status">
              <mat-icon aria-hidden="true">inbox</mat-icon>
              <span> Направлення ще не взято в роботу. </span>
              <button mat-flat-button type="button" (click)="start()" [disabled]="busy()">
                <mat-icon>play_arrow</mat-icon> Почати опрацювання
              </button>
            </div>
          } @else if (!mine()) {
            <p class="state" role="status">
              <mat-icon aria-hidden="true">lock_person</mat-icon>
              <span>
                В роботі: <strong>{{ r.assignee | fullName }}</strong
                >.
              </span>
            </p>
          } @else {
            <div class="state mine" role="status">
              <mat-icon aria-hidden="true">assignment_ind</mat-icon>
              <span>Направлення закріплене за вами.</span>
              <span class="grow"></span>
              <button mat-stroked-button type="button" (click)="reassign()" [disabled]="busy()">
                <mat-icon>forward</mat-icon> Передати колезі
              </button>
              <button mat-button type="button" (click)="release()" [disabled]="busy()">
                <mat-icon>undo</mat-icon> Відмовитися
              </button>
            </div>
          }
          @if (r.labResult; as d) {
            <p class="dl-muted" role="status">
              Чернетку збережено {{ d.updatedAt | date: 'dd.MM.yyyy HH:mm' }} ({{
                d.labSpecialist | shortName
              }}).
            </p>
          }
          @if (mine()) {
            <form class="dl-form wide" [formGroup]="form" (ngSubmit)="approve()" novalidate>
              <mat-form-field appearance="outline">
                <mat-label>Номер лабораторного дослідження</mat-label>
                <input matInput formControlName="labAccessionNumber" maxlength="64" />
                <mat-hint>Унікальний; літери, цифри, «-», «/», «.»; напр. HP-26-0042</mat-hint>
                @if (form.controls.labAccessionNumber.hasError('pattern')) {
                  <mat-error>Лише літери, цифри та символи - / . без пробілів</mat-error>
                } @else {
                  <mat-error>Вкажіть номер дослідження</mat-error>
                }
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Дата дослідження</mat-label>
                <input
                  matInput
                  [matDatepicker]="examPicker"
                  formControlName="examinedAt"
                  [min]="minDate()"
                  [max]="today"
                  placeholder="дд.мм.рррр"
                  (click)="examPicker.open()"
                />
                <mat-datepicker-toggle matIconSuffix [for]="examPicker" />
                <mat-datepicker #examPicker />
                @if (form.controls.examinedAt.hasError('range')) {
                  <mat-error>Дата — від дати направлення до сьогодні</mat-error>
                } @else {
                  <mat-error>Вкажіть дату дослідження</mat-error>
                }
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Гістопатологічний висновок</mat-label>
                <textarea
                  matInput
                  formControlName="histopathologyDiagnosis"
                  rows="3"
                  maxlength="2000"
                ></textarea>
                <mat-hint>Ваш незалежний висновок за результатами мікроскопії</mat-hint>
                <mat-error>Вкажіть гістопатологічний висновок</mat-error>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Опис (мікроскопічний)</mat-label>
                <textarea
                  matInput
                  formControlName="histopathologyDescription"
                  rows="6"
                  maxlength="10000"
                ></textarea>
                <mat-error>Вкажіть опис</mat-error>
              </mat-form-field>
              <mat-form-field appearance="outline">
                <mat-label>Коментар</mat-label>
                <textarea matInput formControlName="comment" rows="2" maxlength="2000"></textarea>
              </mat-form-field>

              <div class="dl-actions">
                <button mat-flat-button type="submit" [disabled]="busy()">
                  <mat-icon>task_alt</mat-icon> Затвердити результат
                </button>
                <button mat-stroked-button type="button" (click)="saveDraft()" [disabled]="busy()">
                  <mat-icon>save</mat-icon> Зберегти чернетку
                </button>
                <button mat-button type="button" (click)="cancel()" [disabled]="busy()">
                  Скасувати
                </button>
              </div>
              @if (busy()) {
                <mat-progress-bar mode="indeterminate" aria-label="Збереження" />
              }
            </form>
          }
        }
      </section>
      <a mat-button routerLink="/lab/referrals"><mat-icon>arrow_back</mat-icon> До списку</a>
    } @else {
      <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
      justify-items: stretch;
    }
    :host > a {
      justify-self: start;
    }
    .meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px 40px;
      margin: 8px 0 0;
      dt {
        font: var(--mat-sys-label-medium);
        color: var(--dl-text-muted);
      }
      dd {
        margin: 2px 0 0;
      }
    }
    .grid {
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
      gap: 24px;
      @media (max-width: 799.98px) {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    h3 {
      margin: 0 0 12px;
      font-size: 17px;
      font-weight: 600;
    }
    h4 {
      margin: 16px 0 4px;
      font-size: 12px;
      font-weight: 600;
      letter-spacing: 0.04em;
      text-transform: uppercase;
      color: var(--dl-text-muted);
    }
    img {
      display: block;
      max-width: 100%;
      max-height: 420px;
      border-radius: 14px;
      border: 1px solid var(--dl-border);
      background: #000;
    }
    .pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .ai-panel {
      border: 1px solid var(--dl-border);
      border-radius: var(--dl-radius) !important;
      box-shadow: none !important;
    }
    .state {
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 8px 12px;
      margin: 0 0 16px;
      padding: 14px 16px;
      border-radius: 12px;
      background: var(--dl-bg);
    }
    .state .grow {
      flex: 1;
    }
    .state.mine {
      background: var(--dl-primary-soft);
      color: #0b4f62;
    }
    .state.ok {
      align-items: flex-start;
      background: var(--dl-ok-bg);
      color: var(--dl-ok);
    }
    .wide {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      column-gap: 16px;
      max-width: 980px;
    }
    .wide > :nth-child(n + 3) {
      grid-column: 1 / -1;
    }
    @media (max-width: 799.98px) {
      .wide {
        grid-template-columns: minmax(0, 1fr);
      }
    }
  `,
})
export class LabReferralDetailPage implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ReferralApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);
  private readonly dialog = inject(MatDialog);
  private readonly fb = inject(NonNullableFormBuilder);

  private readonly auth = inject(AuthService);

  readonly referral = signal<Referral | null>(null);
  readonly mine = computed(() => {
    const r = this.referral();
    return !!r && r.status === 'InProgress' && r.assignee?.id === this.auth.user()?.id;
  });
  readonly busy = signal(false);
  readonly today = todayIso();
  readonly minDate = computed(() => {
    const r = this.referral();
    return r ? todayIso(new Date(r.createdAt)) : '';
  });

  readonly form = this.fb.group({
    labAccessionNumber: ['', [accessionNumber]],
    histopathologyDiagnosis: [''],
    histopathologyDescription: [''],
    examinedAt: ['', [(c: AbstractControl) => this.dateInRange(c.value as string)]],
    comment: [''],
  });

  ngOnInit(): void {
    this.api.get(this.id()).subscribe({
      next: (r) => this.show(r),
      error: (e) => {
        this.notify.error(e, 'Направлення не знайдено');
        void this.router.navigate(['/lab/referrals']);
      },
    });
  }

  start(): void {
    this.run(this.api.start(this.id()), 'Направлення взято в роботу', 'Не вдалося змінити статус');
  }

  reassign(): void {
    const r = this.referral();
    if (!r) return;
    this.api
      .labSpecialists()
      .pipe(
        switchMap((all) =>
          this.dialog
            .open(ReassignDialog, {
              data: {
                referralNumber: r.referralNumber,
                colleagues: all.filter((p) => p.id !== this.auth.user()?.id),
              } satisfies ReassignData,
            })
            .afterClosed(),
        ),
        filter((id): id is string => !!id),
      )
      .subscribe({
        next: (id) =>
          this.run(this.api.reassign(this.id(), id), 'Направлення передано', 'Не вдалося передати'),
        error: (e) => this.notify.error(e, 'Не вдалося завантажити список лаборантів'),
      });
  }

  release(): void {
    this.ask({
      title: 'Відмовитися від направлення?',
      message:
        'Направлення повернеться до спільної черги зі статусом «Надіслано», його зможе взяти ' +
        'інший лаборант. Збережена чернетка залишиться.',
      confirmText: 'Відмовитися',
    })
      .pipe(filter(Boolean))
      .subscribe(() =>
        this.run(this.api.release(this.id()), 'Направлення повернуто до черги', 'Не вдалося'),
      );
  }

  saveDraft(): void {
    this.setRequired(false);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.run(
      this.api.saveDraft(this.id(), this.value()),
      'Чернетку збережено',
      'Не вдалося зберегти',
    );
  }

  approve(): void {
    this.setRequired(true);
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.notify.info('Заповніть обов’язкові поля, щоб затвердити результат');
      return;
    }
    const body = this.value();
    this.ask({
      title: 'Затвердити результат?',
      message:
        `№ ${body.labAccessionNumber} · ${body.histopathologyDiagnosis}. ` +
        'Після затвердження результат змінити неможливо.',
      confirmText: 'Затвердити',
    })
      .pipe(filter(Boolean))
      .subscribe(() =>
        this.run(
          this.api.approve(this.id(), body),
          'Результат затверджено',
          'Не вдалося затвердити',
        ),
      );
  }

  cancel(): void {
    const r = this.referral();
    if (r && this.form.dirty) {
      this.fill(r);
      this.notify.info('Незбережені зміни скасовано');
    } else {
      void this.router.navigate(['/lab/referrals']);
    }
  }

  private run(call: Observable<Referral>, ok: string, fail: string): void {
    if (this.busy()) return; // blocks repeated submits
    this.busy.set(true);
    call.pipe(finalize(() => this.busy.set(false))).subscribe({
      next: (r) => {
        this.show(r);
        this.notify.success(ok);
      },
      error: (e) => this.notify.error(e, fail),
    });
  }

  private show(r: Referral): void {
    this.referral.set(r);
    this.fill(r);
  }

  private fill(r: Referral): void {
    const d = r.labResult;
    this.setRequired(false);
    this.form.reset({
      labAccessionNumber: d?.labAccessionNumber ?? '',
      histopathologyDiagnosis: d?.histopathologyDiagnosis ?? '',
      histopathologyDescription: d?.histopathologyDescription ?? '',
      examinedAt: d?.examinedAt ?? '',
      comment: d?.comment ?? '',
    });
  }

  private setRequired(on: boolean): void {
    for (const name of REQUIRED) {
      const c = this.form.controls[name];
      if (on) c.addValidators([Validators.required, notBlank]);
      else c.removeValidators([Validators.required, notBlank]);
      c.updateValueAndValidity({ emitEvent: false });
    }
  }

  private dateInRange(v: string): { range: true } | null {
    if (!v) return null;
    return v > this.today || (this.minDate() && v < this.minDate()) ? { range: true } : null;
  }

  private value(): LabResultInput {
    const v = this.form.getRawValue();
    const t = (s: string) => s.trim() || null;
    return {
      labAccessionNumber: t(v.labAccessionNumber),
      histopathologyDiagnosis: t(v.histopathologyDiagnosis),
      histopathologyDescription: t(v.histopathologyDescription),
      examinedAt: v.examinedAt || null,
      comment: t(v.comment),
    };
  }

  private ask(data: ConfirmData): Observable<boolean> {
    return this.dialog.open(ConfirmDialog, { data }).afterClosed();
  }
}
