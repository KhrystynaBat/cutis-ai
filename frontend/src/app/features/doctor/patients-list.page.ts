import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged } from 'rxjs';

import { DoctorApi, Patient } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { FullNamePipe } from '../../shared/names';

@Component({
  selector: 'app-patients-list-page',
  imports: [
    FullNamePipe,
    DatePipe,
    ReactiveFormsModule,
    RouterLink,
    MatTableModule,
    MatPaginatorModule,
    MatFormFieldModule,
    MatInputModule,
    MatCheckboxModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
  ],
  template: `
    <section class="dl-card">
      <div class="dl-list-header">
        <h2 class="dl-page-title">Мої пацієнти</h2>
        <a mat-flat-button routerLink="/doctor/patients/new">
          <mat-icon>person_add</mat-icon> Додати пацієнта
        </a>
      </div>
      <div class="dl-filters" role="search">
        <mat-form-field appearance="outline" subscriptSizing="dynamic" class="grow">
          <mat-label>Пошук за ПІБ або електронною поштою</mat-label>
          <mat-icon matPrefix aria-hidden="true">search</mat-icon>
          <input matInput type="search" [formControl]="search" />
        </mat-form-field>
        <mat-checkbox [formControl]="includeArchived">Показати архівованих</mat-checkbox>
      </div>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
      }
      <div class="dl-table-wrap">
        <table mat-table [dataSource]="rows()" aria-label="Пацієнти">
          <ng-container matColumnDef="id">
            <th mat-header-cell *matHeaderCellDef>ID</th>
            <td mat-cell *matCellDef="let p" class="mono">{{ shortId(p) }}</td>
          </ng-container>
          <ng-container matColumnDef="name">
            <th mat-header-cell *matHeaderCellDef>ПІБ</th>
            <td mat-cell *matCellDef="let p">
              <a [routerLink]="['/doctor/patients', p.id]">{{ p | fullName }}</a>
              @if (p.isArchived) {
                <span class="dl-hint">в архіві</span>
              }
            </td>
          </ng-container>
          <ng-container matColumnDef="dob">
            <th mat-header-cell *matHeaderCellDef>Дата народження (вік)</th>
            <td mat-cell *matCellDef="let p">
              {{ p.dateOfBirth | date: 'dd.MM.yyyy' }} ({{ p.age }})
            </td>
          </ng-container>
          <ng-container matColumnDef="email">
            <th mat-header-cell *matHeaderCellDef>Електронна пошта</th>
            <td mat-cell *matCellDef="let p">{{ p.email ?? '—' }}</td>
          </ng-container>
          <ng-container matColumnDef="cases">
            <th mat-header-cell *matHeaderCellDef>Випадків</th>
            <td mat-cell *matCellDef="let p">{{ p.casesCount }}</td>
          </ng-container>
          <ng-container matColumnDef="lastVisit">
            <th mat-header-cell *matHeaderCellDef>Останній візит</th>
            <td mat-cell *matCellDef="let p">
              {{ p.lastVisit ? (p.lastVisit | date: 'dd.MM.yyyy') : '—' }}
            </td>
          </ng-container>
          <ng-container matColumnDef="actions">
            <th mat-header-cell *matHeaderCellDef><span class="visually-hidden">Дії</span></th>
            <td mat-cell *matCellDef="let p" class="dl-row-actions">
              <a
                mat-icon-button
                [routerLink]="['/doctor/patients', p.id, 'edit']"
                [attr.aria-label]="'Редагувати ' + (p | fullName)"
              >
                <mat-icon>edit</mat-icon>
              </a>
              @if (!p.isArchived) {
                <a
                  mat-icon-button
                  [routerLink]="['/doctor/cases/new']"
                  [queryParams]="{ patientId: p.id }"
                  [attr.aria-label]="'Новий випадок для ' + (p | fullName)"
                >
                  <mat-icon>note_add</mat-icon>
                </a>
              }
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
                {{ search.value ? 'Нікого не знайдено.' : 'Ще немає пацієнтів. Додайте першого.' }}
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
export class PatientsListPage {
  private readonly api = inject(DoctorApi);
  private readonly notify = inject(NotifyService);

  readonly columns = ['id', 'name', 'dob', 'email', 'cases', 'lastVisit', 'actions'];
  readonly search = new FormControl('', { nonNullable: true });
  readonly includeArchived = new FormControl(false, { nonNullable: true });
  readonly rows = signal<Patient[]>([]);
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
    this.includeArchived.valueChanges
      .pipe(takeUntilDestroyed(destroyRef))
      .subscribe(() => this.reload(true));
    this.reload();
  }

  shortId(p: Patient): string {
    return p.id.slice(0, 8);
  }

  reload(resetPage = false): void {
    if (resetPage) this.page.set(1);
    this.loading.set(true);
    this.loadError.set(false);
    this.api
      .listPatients({
        search: this.search.value,
        includeArchived: this.includeArchived.value,
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
          this.notify.error(e, 'Не вдалося завантажити пацієнтів');
        },
      });
  }

  onPage(e: PageEvent): void {
    this.page.set(e.pageIndex + 1);
    this.pageSize.set(e.pageSize);
    this.reload();
  }
}
