import { DatePipe } from '@angular/common';
import { Component, computed, effect, inject, input, output, signal } from '@angular/core';
import { NonNullableFormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatRadioModule } from '@angular/material/radio';
import { RouterLink } from '@angular/router';
import { Observable, filter, finalize, of, switchMap } from 'rxjs';

import {
  AssessmentInput,
  CaseDecision,
  CaseDetail,
  DECISION_LABELS,
  DoctorApi,
  REFERRAL_STATUS_LABELS,
} from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { ConfirmDialog, ConfirmData } from '../../shared/dialogs/confirm-dialog';
import { notBlank, todayIso } from '../../shared/forms/validators';

const SUCCESS: Record<CaseDecision | 'none', string> = {
  none: 'Оцінку збережено',
  Close: 'Випадок завершено',
  FollowUp: 'Контроль заплановано',
  Refer: 'Направлення створено',
};

@Component({
  selector: 'app-assessment-panel',
  imports: [
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatIconModule,
    MatInputModule,
    MatRadioModule,
  ],
  template: `
    @let c = caseData();
    @switch (c.status) {
      @case ('FollowUpPlanned') {
        <p class="state" role="status">
          <mat-icon aria-hidden="true">event</mat-icon>
          <span>
            Контроль заплановано на <strong>{{ c.followUpDate | date: 'dd.MM.yyyy' }}</strong>
            @if (c.followUpNote) {
              — {{ c.followUpNote }}
            }
          </span>
        </p>
      }
      @case ('Referred') {
        <p class="state" role="status">
          <mat-icon aria-hidden="true">send</mat-icon>
          @if (c.referral; as r) {
            <span>
              Направлено на гістопатологію:
              <a [routerLink]="['/doctor/referrals', r.id]" class="mono">{{ r.referralNumber }}</a>
              ({{ referralLabels[r.status] }}).
              @if (r.status === 'Completed') {
                Результат лабораторії затверджено.
              }
            </span>
          }
        </p>
      }
      @case ('Closed') {
        <p class="state" role="status">
          <mat-icon aria-hidden="true">lock</mat-icon>
          <span>Випадок завершено. Дані доступні лише для перегляду.</span>
        </p>
      }
    }

    @if (c.status === 'Closed') {
      <h3>Оцінка лікаря</h3>
      <p class="pre">{{ c.doctorAssessment || '—' }}</p>
      @if (c.decision) {
        <p class="dl-muted">Рішення: {{ decisionLabels[c.decision] }}</p>
      }
    } @else {
      <form class="dl-form wide" [formGroup]="form" (ngSubmit)="save()" novalidate>
        <mat-form-field appearance="outline">
          <mat-label>Оцінка лікаря</mat-label>
          <textarea
            matInput
            formControlName="doctorAssessment"
            rows="5"
            maxlength="5000"
            placeholder="Ваш клінічний висновок"
          ></textarea>
          @if (form.controls.doctorAssessment.hasError('required')) {
            <mat-error>Щоб завершити випадок, заповніть оцінку лікаря</mat-error>
          }
        </mat-form-field>

        @if (decisions().length) {
          <fieldset>
            <legend>Рішення</legend>
            <mat-radio-group formControlName="decision" class="radios">
              @for (d of decisions(); track d) {
                <mat-radio-button [value]="d">{{ decisionLabels[d] }}</mat-radio-button>
              }
            </mat-radio-group>
          </fieldset>
        }

        @switch (form.controls.decision.value) {
          @case ('FollowUp') {
            <mat-form-field appearance="outline">
              <mat-label>Дата контролю</mat-label>
              <input matInput type="date" formControlName="followUpDate" [min]="today" required />
              @if (form.controls.followUpDate.hasError('past')) {
                <mat-error>Дата контролю не може бути в минулому</mat-error>
              } @else {
                <mat-error>Вкажіть дату контролю</mat-error>
              }
            </mat-form-field>
            <mat-form-field appearance="outline">
              <mat-label>Примітка до контролю</mat-label>
              <textarea
                matInput
                formControlName="followUpNote"
                rows="2"
                maxlength="2000"
              ></textarea>
            </mat-form-field>
          }
          @case ('Refer') {
            <mat-form-field appearance="outline">
              <mat-label>Клінічне питання / підстава направлення</mat-label>
              <textarea
                matInput
                formControlName="referralReason"
                rows="3"
                maxlength="2000"
                required
              ></textarea>
              <mat-error>Вкажіть підставу направлення</mat-error>
            </mat-form-field>
          }
        }

        <div class="dl-actions">
          <button mat-flat-button type="submit" [disabled]="saving()">
            {{ submitLabel() }}
          </button>
          @if (c.availableActions.includes('Reopen')) {
            <button mat-stroked-button type="button" (click)="reopen()" [disabled]="saving()">
              <mat-icon>undo</mat-icon> Повторний огляд (повернути у «Відкритий»)
            </button>
          }
        </div>
      </form>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    .wide {
      max-width: 720px;
    }
    .state {
      display: flex;
      align-items: flex-start;
      gap: 8px;
      margin: 0 0 16px;
      padding: 10px 14px;
      border-radius: 8px;
      background: var(--dl-bg);
    }
    h3 {
      margin: 0 0 8px;
      font: var(--mat-sys-title-medium);
    }
    .pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    fieldset {
      border: 0;
      padding: 0;
      margin: 8px 0 12px;
    }
    legend {
      font: var(--mat-sys-title-small);
      margin-bottom: 4px;
    }
    .radios {
      display: flex;
      flex-direction: column;
      align-items: flex-start;
    }
  `,
})
export class AssessmentPanel {
  readonly caseData = input.required<CaseDetail>();
  readonly changed = output<CaseDetail>();

  private readonly api = inject(DoctorApi);
  private readonly notify = inject(NotifyService);
  private readonly dialog = inject(MatDialog);

  readonly decisionLabels = DECISION_LABELS;
  readonly referralLabels = REFERRAL_STATUS_LABELS;
  readonly today = todayIso();
  readonly saving = signal(false);

  private readonly fb = inject(NonNullableFormBuilder);
  readonly form = this.fb.group({
    doctorAssessment: [''],
    decision: this.fb.control<CaseDecision | null>(null),
    followUpDate: [''],
    followUpNote: [''],
    referralReason: [''],
  });

  readonly decisions = computed(() =>
    (['Close', 'FollowUp', 'Refer'] as CaseDecision[]).filter((d) =>
      this.caseData().availableActions.includes(d),
    ),
  );
  private readonly decision = signal<CaseDecision | null>(null);
  readonly submitLabel = computed(() => {
    const d = this.decision();
    return d ? `Зберегти: ${DECISION_LABELS[d].toLowerCase()}` : 'Зберегти оцінку';
  });

  constructor() {
    effect(() => {
      const c = this.caseData();
      this.form.reset({
        doctorAssessment: c.doctorAssessment ?? '',
        decision: null,
        followUpDate: '',
        followUpNote: '',
        referralReason: '',
      });
    });
    this.form.controls.decision.valueChanges.subscribe((d) => {
      this.decision.set(d);
      const f = this.form.controls;
      f.doctorAssessment.setValidators(d === 'Close' ? [Validators.required, notBlank] : []);
      f.followUpDate.setValidators(
        d === 'FollowUp'
          ? [Validators.required, (x) => (x.value && x.value < this.today ? { past: true } : null)]
          : [],
      );
      f.referralReason.setValidators(d === 'Refer' ? [Validators.required, notBlank] : []);
      for (const ctl of [f.doctorAssessment, f.followUpDate, f.referralReason]) {
        ctl.updateValueAndValidity({ emitEvent: false });
      }
    });
  }

  save(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    const v = this.form.getRawValue();
    const body: AssessmentInput = { doctorAssessment: v.doctorAssessment };
    if (v.decision) {
      body.decision = v.decision;
      if (v.decision === 'FollowUp') {
        body.followUpDate = v.followUpDate;
        body.followUpNote = v.followUpNote;
      }
      if (v.decision === 'Refer') body.referralReason = v.referralReason;
    }
    this.confirm(v.decision)
      .pipe(
        filter(Boolean),
        switchMap(() => {
          this.saving.set(true);
          return this.api
            .saveAssessment(this.caseData().id, body)
            .pipe(finalize(() => this.saving.set(false)));
        }),
      )
      .subscribe({
        next: (c) => {
          this.notify.success(
            v.decision === 'Refer' && c.referral
              ? `${SUCCESS.Refer}: ${c.referral.referralNumber}`
              : SUCCESS[v.decision ?? 'none'],
          );
          this.changed.emit(c);
        },
        error: (e) => this.notify.error(e, 'Не вдалося зберегти рішення'),
      });
  }

  reopen(): void {
    this.ask({
      title: 'Повторний огляд',
      message:
        'Випадок повернеться у статус «Відкритий»: можна буде змінити дані, фото й рішення. Запланований контроль буде скасовано.',
      confirmText: 'Повернути у «Відкритий»',
    })
      .pipe(
        filter(Boolean),
        switchMap(() => {
          this.saving.set(true);
          return this.api
            .reopenCase(this.caseData().id)
            .pipe(finalize(() => this.saving.set(false)));
        }),
      )
      .subscribe({
        next: (c) => {
          this.notify.success('Випадок повернуто у статус «Відкритий»');
          this.changed.emit(c);
        },
        error: (e) => this.notify.error(e, 'Не вдалося змінити статус'),
      });
  }

  private confirm(decision: CaseDecision | null): Observable<boolean> {
    if (decision === 'Close') {
      return this.ask({
        title: 'Завершити випадок?',
        message:
          'Після завершення випадок стане доступним лише для перегляду: змінити дані, фото, оцінку чи рішення буде неможливо.',
        confirmText: 'Завершити випадок',
        danger: true,
      });
    }
    if (decision === 'Refer') {
      return this.ask({
        title: 'Направити на гістопатологію?',
        message:
          'Буде створено направлення зі статусом «Надіслано», а випадок перейде у статус «Направлено». Дані й фото випадку більше не редагуватимуться.',
        confirmText: 'Створити направлення',
      });
    }
    return of(true);
  }

  private ask(data: ConfirmData): Observable<boolean> {
    return this.dialog.open(ConfirmDialog, { data }).afterClosed();
  }
}
