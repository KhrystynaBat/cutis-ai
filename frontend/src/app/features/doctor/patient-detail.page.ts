import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { Router, RouterLink } from '@angular/router';

import { CaseSummary, DoctorApi, Patient } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { CaseStatusChip } from '../../shared/case-status-chip';
import { ConfirmData, ConfirmDialog } from '../../shared/dialogs/confirm-dialog';
import { FullNamePipe } from '../../shared/names';

@Component({
  selector: 'app-patient-detail-page',
  imports: [
    FullNamePipe,
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    CaseStatusChip,
  ],
  template: `
    @if (patient(); as p) {
      <section class="dl-card" aria-labelledby="p-title">
        <div class="dl-list-header">
          <h2 id="p-title" class="dl-page-title">{{ p | fullName }}</h2>
          <div class="dl-actions">
            <a mat-stroked-button [routerLink]="['/doctor/patients', p.id, 'edit']">
              <mat-icon>edit</mat-icon> Редагувати
            </a>
            @if (!p.isArchived) {
              <a mat-flat-button routerLink="/doctor/cases/new" [queryParams]="{ patientId: p.id }">
                <mat-icon>note_add</mat-icon> Новий випадок
              </a>
            }
          </div>
        </div>
        @if (p.isArchived) {
          <p class="dl-banner">Пацієнта архівовано: нові випадки створювати не можна.</p>
        }
        <dl class="facts">
          <dt>ID</dt>
          <dd class="mono">{{ p.id }}</dd>
          <dt>Дата народження</dt>
          <dd>{{ p.dateOfBirth | date: 'dd.MM.yyyy' }} ({{ p.age }} р.)</dd>
          <dt>Електронна пошта</dt>
          <dd>{{ p.email ?? '—' }}</dd>
          <dt>Телефон</dt>
          <dd>{{ p.phone ?? '—' }}</dd>
          <dt>Примітка</dt>
          <dd class="pre">{{ p.notes ?? '—' }}</dd>
        </dl>
        <button mat-button type="button" (click)="toggleArchive(p)">
          <mat-icon>{{ p.isArchived ? 'unarchive' : 'archive' }}</mat-icon>
          {{ p.isArchived ? 'Повернути з архіву' : 'Архівувати' }}
        </button>
      </section>

      <section class="dl-card" aria-labelledby="c-title">
        <h2 id="c-title" class="dl-page-title">Випадки</h2>
        @if (cases().length === 0) {
          <p class="dl-muted">Випадків ще немає.</p>
        } @else {
          <ul class="cases">
            @for (c of cases(); track c.id) {
              <li>
                <a [routerLink]="['/doctor/cases', c.id]">
                  {{ c.examinedAt | date: 'dd.MM.yyyy' }} — {{ c.bodyLocation }}
                </a>
                <app-case-status [status]="c.status" />
                @if (!c.hasImage) {
                  <span class="dl-muted">без фото</span>
                }
              </li>
            }
          </ul>
        }
      </section>
    } @else if (loading()) {
      <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
    }
  `,
  styles: `
    :host {
      display: grid;
      grid-template-columns: minmax(0, 1fr);
      gap: 16px;
    }
    .facts {
      display: grid;
      grid-template-columns: max-content 1fr;
      gap: 8px 24px;
      margin: 8px 0 12px;
    }
    dt {
      color: var(--dl-text-muted);
    }
    dd {
      margin: 0;
      overflow-wrap: anywhere;
    }
    .pre {
      white-space: pre-wrap;
    }
    .cases {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }
    .cases li {
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }
  `,
})
export class PatientDetailPage implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(DoctorApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);
  private readonly dialog = inject(MatDialog);

  readonly patient = signal<Patient | null>(null);
  readonly cases = signal<CaseSummary[]>([]);
  readonly loading = signal(true);

  ngOnInit(): void {
    this.api.getPatient(this.id()).subscribe({
      next: (p) => {
        this.patient.set(p);
        this.loading.set(false);
      },
      error: (e) => {
        this.notify.error(e, 'Пацієнта не знайдено');
        void this.router.navigate(['/doctor/patients']);
      },
    });
    this.api
      .listCases({ patientId: this.id(), page: 1, pageSize: 100 })
      .subscribe({ next: (r) => this.cases.set(r.items), error: (e) => this.notify.error(e) });
  }

  toggleArchive(p: Patient): void {
    const archive = !p.isArchived;
    const data: ConfirmData = archive
      ? {
          title: 'Архівувати пацієнта?',
          message: 'Пацієнт зникне зі списку (дані не видаляються). Його можна буде повернути.',
          confirmText: 'Архівувати',
        }
      : {
          title: 'Повернути пацієнта з архіву?',
          message: 'Пацієнт знову з’явиться у списку.',
          confirmText: 'Повернути',
        };
    this.dialog
      .open(ConfirmDialog, { data })
      .afterClosed()
      .subscribe((ok) => {
        if (!ok) return;
        this.api.setPatientArchived(p.id, archive).subscribe({
          next: (updated) => {
            this.patient.set(updated);
            this.notify.success(archive ? 'Пацієнта архівовано' : 'Пацієнта повернуто');
          },
          error: (e) => this.notify.error(e),
        });
      });
  }
}
