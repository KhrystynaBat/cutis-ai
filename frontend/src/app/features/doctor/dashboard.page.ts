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
import { InitialsPipe, ShortNamePipe } from '../../shared/names';

@Component({
  selector: 'app-doctor-dashboard-page',
  imports: [
    ShortNamePipe,
    InitialsPipe,
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    CaseStatusChip,
  ],
  template: `
    <section class="dl-card hero">
      <div class="hero-text">
        <span class="today">{{ today | date: 'EEEE, d MMMM' }}</span>
        @if (auth.user()) {
          <h2 class="dl-page-title">{{ auth.greeting() }}</h2>
        }
        @if (data(); as d) {
          @if (d.readyResults > 0) {
            <span class="dl-muted">Нові результати лабораторії: {{ d.readyResults }}</span>
          }
        }
      </div>
      <div class="dl-actions">
        <a mat-stroked-button routerLink="/doctor/patients/new">
          <mat-icon>person_add</mat-icon> Новий пацієнт
        </a>
        <a mat-flat-button routerLink="/doctor/cases/new">
          <mat-icon>note_add</mat-icon> Створити випадок
        </a>
      </div>
    </section>

    @if (data(); as d) {
      <div class="cards" role="list">
        <a class="dl-card stat" role="listitem" routerLink="/doctor/patients">
          <span class="ico teal"><mat-icon aria-hidden="true">groups</mat-icon></span>
          <span class="num">{{ d.patients }}</span>
          <span class="label">Мої пацієнти</span>
        </a>
        <a class="dl-card stat" role="listitem" routerLink="/doctor/cases">
          <span class="ico amber"><mat-icon aria-hidden="true">clinical_notes</mat-icon></span>
          <span class="num">{{ d.activeCases }}</span>
          <span class="label">Активні випадки</span>
        </a>
        <a class="dl-card stat" role="listitem" routerLink="/doctor/referrals">
          <span class="ico violet"><mat-icon aria-hidden="true">send</mat-icon></span>
          <span class="num">{{ d.pendingReferrals }}</span>
          <span class="label">Направлення в очікуванні</span>
        </a>
        <a class="dl-card stat" role="listitem" href="#new-results">
          <span class="ico green"><mat-icon aria-hidden="true">task_alt</mat-icon></span>
          <span class="num">{{ d.readyResults }}</span>
          <span class="label">Готові результати</span>
        </a>
      </div>

      <div class="columns">
        <section class="dl-card" aria-labelledby="recent-title">
          <div class="card-head">
            <h2 id="recent-title" class="dl-page-title">Останні випадки</h2>
            <a class="more" routerLink="/doctor/cases">Усі випадки →</a>
          </div>
          @if (d.recentCases.length === 0) {
            <p class="dl-muted">Випадків ще немає.</p>
          } @else {
            <ul class="recent">
              @for (c of d.recentCases; track c.id) {
                <li>
                  <span class="avatar" aria-hidden="true">{{ c.patient | initials }}</span>
                  <a class="name" [routerLink]="['/doctor/cases', c.id]">
                    {{ c.patient | shortName }}
                  </a>
                  <span class="dl-muted">{{ c.examinedAt | date: 'dd.MM.yyyy' }}</span>
                  <app-case-status [status]="c.status" />
                </li>
              }
            </ul>
          }
        </section>

        <section class="dl-card" id="new-results" aria-labelledby="results-title">
          <h2 id="results-title" class="dl-page-title">Нові результати лабораторії</h2>
          @if (newResults().length === 0) {
            <p class="dl-muted">Результатів, що очікують ознайомлення, немає.</p>
          } @else {
            <ul class="results">
              @for (r of newResults(); track r.id) {
                <li>
                  <a [routerLink]="['/doctor/referrals', r.id]" class="mono ref">{{
                    r.referralNumber
                  }}</a>
                  <span class="name">{{ r.patient | shortName }}</span>
                  <span class="dl-muted">{{ r.bodyLocation }}</span>
                  <a class="more" [routerLink]="['/doctor/cases', r.caseId]">Відкрити випадок →</a>
                </li>
              }
            </ul>
          }
        </section>
      </div>
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
      gap: 20px;
      max-width: 1280px;
    }
    .hero {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 20px;
      flex-wrap: wrap;
    }
    .hero-text {
      display: flex;
      flex-direction: column;
      gap: 4px;
    }
    .hero .dl-page-title {
      margin: 0;
      font-size: 28px;
    }
    .today {
      color: var(--mat-sys-primary);
      font-weight: 500;
    }
    .today::first-letter {
      text-transform: uppercase;
    }
    .hero .dl-actions {
      margin: 0;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
    }
    .stat {
      display: flex;
      flex-direction: column;
      gap: 2px;
      padding: 20px 22px;
      color: inherit;
      text-decoration: none;
      transition: border-color 0.15s;
    }
    .stat:hover {
      border-color: #b9d7e0;
    }
    .ico {
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      margin-bottom: 12px;
      border-radius: 12px;
    }
    .ico.teal {
      background: var(--dl-primary-soft);
      color: var(--mat-sys-primary);
    }
    .ico.amber {
      background: #fff3e0;
      color: #a35f00;
    }
    .ico.violet {
      background: var(--dl-violet-bg);
      color: #5a45c7;
    }
    .ico.green {
      background: var(--dl-ok-bg);
      color: var(--dl-ok);
    }
    .num {
      font-size: 32px;
      font-weight: 700;
      letter-spacing: -0.02em;
      line-height: 1.2;
    }
    .label {
      color: var(--dl-text-muted);
    }
    .columns {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
      gap: 20px;
      align-items: start;
    }
    @media (max-width: 959.98px) {
      .columns {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .card-head {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 12px;
    }
    .more {
      color: var(--mat-sys-primary);
      font-weight: 600;
      text-decoration: none;
    }
    .recent,
    .results {
      list-style: none;
      margin: 0;
      padding: 0;
    }
    .recent li {
      display: grid;
      grid-template-columns: 36px minmax(0, 1fr) auto auto;
      align-items: center;
      gap: 14px;
      padding: 12px 0;
      border-bottom: 1px solid var(--dl-border-soft);
    }
    .recent li:last-child {
      border-bottom: 0;
    }
    .avatar {
      display: grid;
      place-items: center;
      width: 36px;
      height: 36px;
      border-radius: 50%;
      background: var(--dl-primary-soft);
      color: #0b4f62;
      font-size: 12px;
      font-weight: 600;
    }
    .name {
      font-weight: 600;
      color: inherit;
      text-decoration: none;
    }
    a.name:hover {
      color: var(--mat-sys-primary);
    }
    .results {
      display: grid;
      gap: 12px;
    }
    .results li {
      display: flex;
      flex-direction: column;
      gap: 6px;
      padding: 16px;
      border-radius: 14px;
      border: 1px solid #cfe6ec;
      background: #f2f9fb;
    }
    .ref {
      color: #0b4f62;
      font-weight: 600;
    }
  `,
})
export class DoctorDashboardPage {
  protected readonly auth = inject(AuthService);
  private readonly api = inject(DoctorApi);
  private readonly referrals = inject(ReferralApi);
  private readonly notify = inject(NotifyService);

  readonly today = new Date();
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
