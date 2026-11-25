import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { CASE_STATUS_LABELS, CaseStatus, CaseSummary, DoctorApi } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { CaseStatusChip } from '../../shared/case-status-chip';
import { ReferralStatusChip } from '../../shared/referral-status-chip';
import { ShortNamePipe } from '../../shared/names';

@Component({
  selector: 'app-cases-list-page',
  imports: [
    ShortNamePipe,
    DatePipe,
    DecimalPipe,
    ReactiveFormsModule,
    RouterLink,
    MatTableModule,
    MatPaginatorModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    CaseStatusChip,
    ReferralStatusChip,
  ],
  template: `
    <section class="dl-card">
      <div class="dl-list-header">
        <h2 class="dl-page-title">Усі мої випадки</h2>
        <a mat-flat-button routerLink="/doctor/cases/new">
          <mat-icon>note_add</mat-icon> Створити випадок
        </a>
      </div>
      <div class="dl-filters" role="search">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Пошук за пацієнтом</mat-label>
          <mat-icon matPrefix aria-hidden="true">search</mat-icon>
          <input matInput type="search" [formControl]="search" />
        </mat-form-field>
        <mat-form-field appearance="outline" subscriptSizing="dynamic">
          <mat-label>Статус</mat-label>
          <mat-select [formControl]="status">
            <mat-option value="">Усі статуси</mat-option>
            @for (s of statuses; track s) {
              <mat-option [value]="s">{{ statusLabels[s] }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
      </div>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
      }
      <div class="dl-table-wrap">
        <table mat-table [dataSource]="rows()" aria-label="Випадки">
          <ng-container matColumnDef="id">
            <th mat-header-cell *matHeaderCellDef>ID</th>
            <td mat-cell *matCellDef="let c" class="mono">{{ shortId(c) }}</td>
          </ng-container>
          <ng-container matColumnDef="patient">
            <th mat-header-cell *matHeaderCellDef>Пацієнт</th>
            <td mat-cell *matCellDef="let c">{{ c.patient | shortName }}</td>
          </ng-container>
          <ng-container matColumnDef="date">
            <th mat-header-cell *matHeaderCellDef>Дата огляду</th>
            <td mat-cell *matCellDef="let c">{{ c.examinedAt | date: 'dd.MM.yyyy' }}</td>
          </ng-container>
          <ng-container matColumnDef="location">
            <th mat-header-cell *matHeaderCellDef>Локалізація</th>
            <td mat-cell *matCellDef="let c">{{ c.bodyLocation }}</td>
          </ng-container>
          <ng-container matColumnDef="status">
            <th mat-header-cell *matHeaderCellDef>Статус</th>
            <td mat-cell *matCellDef="let c"><app-case-status [status]="c.status" /></td>
          </ng-container>
          <ng-container matColumnDef="ai">
            <th mat-header-cell *matHeaderCellDef>Результат ШІ</th>
            <td mat-cell *matCellDef="let c">
              @if (c.aiResult; as r) {
                {{ r.labelUk }} <span class="dl-muted">({{ r.score | number: '1.2-2' }})</span>
              } @else {
                <span class="dl-muted">—</span>
              }
            </td>
          </ng-container>
          <ng-container matColumnDef="referral">
            <th mat-header-cell *matHeaderCellDef>Направлення</th>
            <td mat-cell *matCellDef="let c">
              @if (c.referral; as r) {
                <a [routerLink]="['/doctor/referrals', r.id]" class="mono">{{
                  r.referralNumber
                }}</a>
                <app-referral-status [status]="r.status" />
              } @else {
                <span class="dl-muted">—</span>
              }
            </td>
          </ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef><span class="visually-hidden">Дії</span></th>
            <td mat-cell *matCellDef="let c" class="dl-row-actions">
              <a mat-button [routerLink]="['/doctor/cases', c.id]">Відкрити</a>
            </td>
          </ng-container>
          <tr mat-header-row *matHeaderRowDef="columns"></tr>
          <tr mat-row *matRowDef="let row; columns: columns"></tr>
          <tr class="mat-mdc-row" *matNoDataRow>
            <td class="dl-empty" [attr.colspan]="columns.length">
              @if (loadError()) {
                Не вдалося завантажити список.
                <button mat-button type="button" (click)="reload()">Повторити</button>
              } @else if (!loading()) {
                {{
                  search.value || status.value
                    ? 'Нічого не знайдено за цими умовами.'
                    : 'Випадків ще немає.'
                }}
              }
            </td>
          </tr>
        </table>
      </div>
      <mat-paginator
        [length]="total()"
        [pageIndex]="page() - 1"
        [pageSize]="pageSize()"
        [pageSizeOptions]="[10, 20, 50]"
        (page)="onPage($event)"
        aria-label="Сторінки списку"
      />
    </section>
  `,
})
export class CasesListPage {
  private readonly api = inject(DoctorApi);
  private readonly notify = inject(NotifyService);

  readonly statusLabels = CASE_STATUS_LABELS;
  readonly statuses = Object.keys(CASE_STATUS_LABELS) as CaseStatus[];
  readonly columns = ['id', 'patient', 'date', 'location', 'status', 'ai', 'referral', 'actions'];
  readonly search = new FormControl('', { nonNullable: true });
  readonly status = new FormControl<CaseStatus | ''>('', { nonNullable: true });
  readonly rows = signal<CaseSummary[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(20);
  readonly loading = signal(false);
  readonly loadError = signal(false);

  constructor() {
    const destroyRef = inject(DestroyRef);
    this.search.valueChanges
      .pipe(debounceTime(300), distinctUntilChanged(), takeUntilDestroyed(destroyRef))
      .subscribe(() => this.reload(true));
    this.status.valueChanges
      .pipe(takeUntilDestroyed(destroyRef))
      .subscribe(() => this.reload(true));
    this.reload();
  }

  shortId(c: CaseSummary): string {
    return c.id.slice(0, 8);
  }

  reload(resetPage = false): void {
    if (resetPage) this.page.set(1);
    this.loading.set(true);
    this.loadError.set(false);
    this.api
      .listCases({
        search: this.search.value,
        status: this.status.value,
        page: this.page(),
        pageSize: this.pageSize(),
      })
      .subscribe({
        next: (p) => {
          this.rows.set(p.items);
          this.total.set(p.total);
          this.loading.set(false);
        },
        error: (e) => {
          this.loading.set(false);
          this.loadError.set(true);
          this.notify.error(e, 'Не вдалося завантажити випадки');
        },
      });
  }

  onPage(e: PageEvent): void {
    this.page.set(e.pageIndex + 1);
    this.pageSize.set(e.pageSize);
    this.reload();
  }
}
