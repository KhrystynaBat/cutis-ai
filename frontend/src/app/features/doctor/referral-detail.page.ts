import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';

import { Referral, ReferralApi } from '../../core/api/referral-api';
import { NotifyService } from '../../core/notify.service';
import { AnalysisResult } from '../../shared/ai/analysis-result';
import { CaseStatusChip } from '../../shared/case-status-chip';
import { LabResultView } from '../../shared/lab-result-view';
import { ReferralStatusChip } from '../../shared/referral-status-chip';
import { FullNamePipe } from '../../shared/names';

@Component({
  selector: 'app-referral-detail-page',
  imports: [
    FullNamePipe,
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatProgressBarModule,
    AnalysisResult,
    CaseStatusChip,
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
            <dt>Пацієнт</dt>
            <dd>
              <a [routerLink]="['/doctor/patients', r.patient.id]">
                {{ r.patient | fullName }}
              </a>
              <span class="dl-muted"> · {{ r.patient.dateOfBirth | date: 'dd.MM.yyyy' }}</span>
            </dd>
          </div>
          <div>
            <dt>Випадок</dt>
            <dd>
              <a [routerLink]="['/doctor/cases', r.case.id]" class="mono">{{
                r.case.id.slice(0, 8)
              }}</a>
              <app-case-status [status]="r.case.status" />
            </dd>
          </div>
          <div>
            <dt>Дата направлення</dt>
            <dd>{{ r.createdAt | date: 'dd.MM.yyyy HH:mm' }}</dd>
          </div>
          <div>
            <dt>Опрацьовує</dt>
            <dd>
              @if (r.assignee; as a) {
                {{ a | fullName }}
              } @else {
                <span class="dl-muted">ще не взято лабораторією</span>
              }
            </dd>
          </div>
          <div>
            <dt>№ лабораторного дослідження</dt>
            <dd>{{ r.labAccessionNumber || '—' }}</dd>
          </div>
        </dl>
      </section>

      <section class="dl-card grid">
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
          <p><span class="dl-muted">Огляд:</span> {{ r.case.examinedAt | date: 'dd.MM.yyyy' }}</p>
          <p><span class="dl-muted">Локалізація:</span> {{ r.case.bodyLocation }}</p>
          <p class="pre">{{ r.case.clinicalDescription }}</p>
          <h3>Клінічне питання / підстава</h3>
          <p class="pre">{{ r.reason }}</p>
          <h3>Оцінка лікаря</h3>
          <p class="pre">{{ r.case.doctorAssessment || '—' }}</p>
        </div>
      </section>

      <section class="dl-card" aria-labelledby="ref-ai">
        <h3 id="ref-ai">Аналіз ШІ на момент направлення</h3>
        @if (r.analysis; as a) {
          <app-analysis-result [analysis]="a" [originalUrl]="r.analysisImageUrl ?? ''" />
        } @else {
          <p class="dl-muted">Направлення створено без аналізу ШІ.</p>
        }
      </section>

      <section class="dl-card" aria-labelledby="lab-title">
        <h3 id="lab-title">Результат лабораторії</h3>
        @if (r.labResult; as res) {
          <app-lab-result-view [result]="res" />
          @if (r.case.status === 'Referred') {
            <p>
              <a mat-stroked-button [routerLink]="['/doctor/cases', r.case.id]">Відкрити випадок</a>
            </p>
          }
        } @else {
          <p class="dl-muted">
            {{
              r.status === 'InProgress'
                ? 'Лабораторія опрацьовує направлення.'
                : 'Лабораторія ще не взяла направлення в роботу.'
            }}
          </p>
        }
      </section>
    } @else {
      <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
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
        display: flex;
        gap: 8px;
        align-items: center;
        flex-wrap: wrap;
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
      margin: 0 0 8px;
      font: var(--mat-sys-title-medium);
    }
    img {
      display: block;
      max-width: 100%;
      max-height: 420px;
      border-radius: 8px;
      border: 1px solid var(--dl-border);
      background: #000;
    }
    .pre {
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
  `,
})
export class ReferralDetailPage implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(ReferralApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);

  readonly referral = signal<Referral | null>(null);

  ngOnInit(): void {
    this.api.get(this.id()).subscribe({
      next: (r) => this.referral.set(r),
      error: (e) => {
        this.notify.error(e, 'Направлення не знайдено');
        void this.router.navigate(['/doctor/referrals']);
      },
    });
  }
}
