import { DatePipe } from '@angular/common';
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

import { REFERRAL_STATUS_LABELS, ReferralStatus } from '../../core/api/doctor-api';
import { ReferralApi, ReferralSummary } from '../../core/api/referral-api';
import { NotifyService } from '../../core/notify.service';
import { ReferralStatusChip } from '../../shared/referral-status-chip';
import { ShortNamePipe } from '../../shared/names';

@Component({
  selector: 'app-referrals-list-page',
  imports: [
    ShortNamePipe,
    DatePipe,
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
    ReferralStatusChip,
  ],
  template: `
    <section class="dl-card">
      <div class="dl-list-header">
        <h2 class="dl-page-title">Направлення</h2>
      </div>
      <div class="dl-filters" role="search">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Пошук за пацієнтом або номером</mat-label>
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
        <table mat-table [dataSource]="rows()" aria-label="Направлення">
          <ng-container matColumnDef="number">
            <th mat-header-cell *matHeaderCellDef>REF-ID</th>
            <td mat-cell *matCellDef="let r" class="mono">{{ r.referralNumber }}</td>
          </ng-container>
          <ng-container matColumnDef="patient">
            <th mat-header-cell *matHeaderCellDef>Пацієнт</th>
            <td mat-cell *matCellDef="let r">{{ r.patient | shortName }}</td>
          </ng-container>
          <ng-container matColumnDef="case">
            <th mat-header-cell *matHeaderCellDef>Випадок</th>
            <td mat-cell *matCellDef="let r">
              <a [routerLink]="['/doctor/cases', r.caseId]">
                <span class="mono">{{ r.caseId.slice(0, 8) }}</span> · {{ r.bodyLocation }}
              </a>
            </td>
          </ng-container>
          <ng-container matColumnDef="date">
            <th mat-header-cell *matHeaderCellDef>Дата</th>
            <td mat-cell *matCellDef="let r">{{ r.createdAt | date: 'dd.MM.yyyy' }}</td>
          </ng-container>
          <ng-container matColumnDef="status">
            <th mat-header-cell *matHeaderCellDef>Статус</th>
            <td mat-cell *matCellDef="let r"><app-referral-status [status]="r.status" /></td>
          </ng-container>
          <ng-container matColumnDef="accession">
            <th mat-header-cell *matHeaderCellDef>№ дослідження</th>
            <td mat-cell *matCellDef="let r">{{ r.labAccessionNumber || '—' }}</td>
          </ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef><span class="visually-hidden">Дії</span></th>
            <td mat-cell *matCellDef="let r" class="dl-row-actions">
              <a mat-button [routerLink]="['/doctor/referrals', r.id]">Відкрити</a>
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
                    : 'Направлень ще немає.'
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
export class ReferralsListPage {
  private readonly api = inject(ReferralApi);
  private readonly notify = inject(NotifyService);

  readonly statusLabels = REFERRAL_STATUS_LABELS;
  readonly statuses = Object.keys(REFERRAL_STATUS_LABELS) as ReferralStatus[];
  readonly columns = ['number', 'patient', 'case', 'date', 'status', 'accession', 'actions'];
  readonly search = new FormControl('', { nonNullable: true });
  readonly status = new FormControl<ReferralStatus | ''>('', { nonNullable: true });
  readonly rows = signal<ReferralSummary[]>([]);
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

  reload(resetPage = false): void {
    if (resetPage) this.page.set(1);
    this.loading.set(true);
    this.loadError.set(false);
    this.api
      .list({
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
          this.notify.error(e, 'Не вдалося завантажити направлення');
        },
      });
  }

  onPage(e: PageEvent): void {
    this.page.set(e.pageIndex + 1);
    this.pageSize.set(e.pageSize);
    this.reload();
  }
}
