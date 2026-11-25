import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { RouterLink } from '@angular/router';

import { Dashboard, DoctorApi } from '../../core/api/doctor-api';
import { ReferralApi, ReferralSummary } from '../../core/api/referral-api';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import { CaseStatusChip } from '../../shared/case-status-chip';
import { ShortNamePipe } from '../../shared/names';

@Component({
  selector: 'app-doctor-dashboard-page',
  imports: [
    ShortNamePipe,
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    CaseStatusChip,
  ],
  template: `
    <section class="dl-card">
      @if (auth.user()) {
        <h2 class="dl-page-title">{{ auth.greeting() }}</h2>
      }
      <div class="dl-actions">
        <a mat-flat-button routerLink="/doctor/patients/new">
          <mat-icon>person_add</mat-icon> Новий пацієнт
        </a>
        <a mat-stroked-button routerLink="/doctor/cases/new">
          <mat-icon>note_add</mat-icon> Створити випадок
        </a>
      </div>
    </section>

    @if (data(); as d) {
      <div class="cards" role="list">
        <a class="dl-card stat" role="listitem" routerLink="/doctor/patients">
          <span class="num">{{ d.patients }}</span
          ><span>Мої пацієнти</span>
        </a>
        <a class="dl-card stat" role="listitem" routerLink="/doctor/cases">
          <span class="num">{{ d.activeCases }}</span
          ><span>Активні випадки</span>
        </a>
        <a class="dl-card stat" role="listitem" routerLink="/doctor/referrals">
          <span class="num">{{ d.pendingReferrals }}</span
          ><span>Направлення в очікуванні</span>
        </a>
        <a class="dl-card stat" role="listitem" href="#new-results">
          <span class="num">{{ d.readyResults }}</span
          ><span>Готові результати</span>
        </a>
      </div>

      <section class="dl-card" id="new-results" aria-labelledby="results-title">
        <h2 id="results-title" class="dl-page-title">Нові результати лабораторії</h2>
        @if (newResults().length === 0) {
          <p class="dl-muted">Результатів, що очікують ознайомлення, немає.</p>
        } @else {
          <ul class="recent">
            @for (r of newResults(); track r.id) {
              <li>
                <a [routerLink]="['/doctor/referrals', r.id]" class="mono">{{
                  r.referralNumber
                }}</a>
                <span>{{ r.patient | shortName }}</span>
                <span class="dl-muted">{{ r.bodyLocation }}</span>
                <a mat-button [routerLink]="['/doctor/cases', r.caseId]">Випадок</a>
              </li>
            }
          </ul>
        }
      </section>

      <section class="dl-card" aria-labelledby="recent-title">
        <h2 id="recent-title" class="dl-page-title">Останні випадки</h2>
        @if (d.recentCases.length === 0) {
          <p class="dl-muted">Випадків ще немає.</p>
        } @else {
          <ul class="recent">
            @for (c of d.recentCases; track c.id) {
              <li>
                <a [routerLink]="['/doctor/cases', c.id]">
                  {{ c.patient | shortName }}
                </a>
                <span class="dl-muted">{{ c.examinedAt | date: 'dd.MM.yyyy' }}</span>
                <app-case-status [status]="c.status" />
              </li>
            }
          </ul>
        }
      </section>
    } @else if (failed()) {
      <section class="dl-card">
        <p class="dl-error-text">Не вдалося завантажити дані.</p>
        <button mat-button type="button" (click)="load()">Повторити</button>
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
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
    }
    .stat {
      display: flex;
      flex-direction: column;
      gap: 4px;
      color: inherit;
      text-decoration: none;
    }
    .num {
      font: var(--mat-sys-display-small);
      color: var(--mat-sys-primary);
    }
    .recent {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 10px;
    }
    .recent li {
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
    }
  `,
})
export class DoctorDashboardPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(DoctorApi);
  private readonly referrals = inject(ReferralApi);
  private readonly notify = inject(NotifyService);

  readonly data = signal<Dashboard | null>(null);
  readonly failed = signal(false);
  readonly newResults = signal<ReferralSummary[]>([]);

  constructor() {
    this.load();
  }

  load(): void {
    this.failed.set(false);
    this.api.dashboard().subscribe({
      next: (d) => {
        this.data.set(d);
        if (d.readyResults > 0) this.loadNewResults();
      },
      error: (e) => {
        this.failed.set(true);
        this.notify.error(e);
      },
    });
  }

  private loadNewResults(): void {
    this.referrals
      .list({ status: 'Completed', caseStatus: 'Referred', page: 1, pageSize: 5 })
      .subscribe({ next: (p) => this.newResults.set(p.items), error: (e) => this.notify.error(e) });
  }
}
