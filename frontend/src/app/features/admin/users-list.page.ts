import { DatePipe } from '@angular/common';
import { Component, DestroyRef, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormControl, ReactiveFormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatIconModule } from '@angular/material/icon';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { debounceTime, distinctUntilChanged, filter } from 'rxjs';

import {
  AdminUser,
  AdminUsersApi,
  STATUS_LABELS,
  StaffRole,
  StatusAction,
  UserStatus,
} from '../../core/api/admin-users-api';
import { ROLE_LABELS } from '../../core/auth/auth.models';
import { NotifyService } from '../../core/notify.service';
import { ConfirmData, ConfirmDialog } from '../../shared/dialogs/confirm-dialog';
import { PasswordLinkDialog } from './password-link-dialog';
import { FullNamePipe, fullName } from '../../shared/names';

const ACTION_TEXT: Record<
  StatusAction,
  Omit<ConfirmData, 'message'> & { done: string; verb: string }
> = {
  block: {
    title: 'Заблокувати користувача?',
    confirmText: 'Заблокувати',
    danger: true,
    done: 'Користувача заблоковано',
    verb: 'не зможе увійти до розблокування. Активні сесії завершаться',
  },
  unblock: {
    title: 'Розблокувати користувача?',
    confirmText: 'Розблокувати',
    done: 'Користувача розблоковано',
    verb: 'знову зможе входити в систему',
  },
  deactivate: {
    title: 'Деактивувати користувача?',
    confirmText: 'Деактивувати',
    danger: true,
    done: 'Користувача деактивовано',
    verb: 'буде деактивований: вхід неможливий, записи зберігаються',
  },
  reactivate: {
    title: 'Відновити користувача?',
    confirmText: 'Відновити',
    done: 'Користувача відновлено',
    verb: 'знову стане активним',
  },
};

@Component({
  selector: 'app-users-list-page',
  imports: [
    FullNamePipe,
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
    MatMenuModule,
    MatProgressBarModule,
  ],
  templateUrl: './users-list.page.html',
  styleUrl: './users-list.page.scss',
})
export class UsersListPage {
  private readonly api = inject(AdminUsersApi);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotifyService);

  readonly roleLabels = ROLE_LABELS;
  readonly statusLabels = STATUS_LABELS;
  readonly columns = ['name', 'email', 'phone', 'role', 'status', 'createdAt', 'actions'];

  readonly search = new FormControl('', { nonNullable: true });
  readonly role = new FormControl<StaffRole | ''>('', { nonNullable: true });
  readonly status = new FormControl<UserStatus | ''>('', { nonNullable: true });

  readonly rows = signal<AdminUser[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(20);
  readonly loading = signal(false);
  readonly loadError = signal(false);

  constructor() {
    const destroyRef = inject(DestroyRef);
    this.search.valueChanges
      .pipe(
        debounceTime(300),
        distinctUntilChanged(),
        filter((v) => v.length !== 1),
        takeUntilDestroyed(destroyRef),
      )
      .subscribe(() => this.reload(true));
    this.role.valueChanges.pipe(takeUntilDestroyed(destroyRef)).subscribe(() => this.reload(true));
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
        role: this.role.value,
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
          this.notify.error(e, 'Не вдалося завантажити користувачів');
        },
      });
  }

  onPage(e: PageEvent): void {
    this.page.set(e.pageIndex + 1);
    this.pageSize.set(e.pageSize);
    this.reload();
  }

  roleText(u: AdminUser): string {
    return this.roleLabels[u.role];
  }

  statusText(u: AdminUser): string {
    return this.statusLabels[u.status];
  }

  hasFilters(): boolean {
    return !!(this.search.value || this.role.value || this.status.value);
  }

  changeStatus(u: AdminUser, action: StatusAction): void {
    const t = ACTION_TEXT[action];
    this.dialog
      .open(ConfirmDialog, {
        data: { ...t, message: `${fullName(u)} ${t.verb}.` } satisfies ConfirmData,
      })
      .afterClosed()
      .subscribe((ok) => {
        if (!ok) return;
        this.api.setStatus(u.id, action).subscribe({
          next: () => {
            this.notify.success(t.done);
            this.reload();
          },
          error: (e) => this.notify.error(e),
        });
      });
  }

  issueLink(u: AdminUser): void {
    this.api.issuePasswordLink(u.id).subscribe({
      next: (token) =>
        this.dialog.open(PasswordLinkDialog, {
          data: { userName: fullName(u), token },
          width: '560px',
        }),
      error: (e) => this.notify.error(e),
    });
  }

  remove(u: AdminUser): void {
    this.dialog
      .open(ConfirmDialog, {
        data: {
          title: 'Видалити обліковий запис?',
          message: `Обліковий запис ${fullName(u)} буде видалено назавжди.`,
          confirmText: 'Видалити',
          danger: true,
        } satisfies ConfirmData,
      })
      .afterClosed()
      .subscribe((ok) => {
        if (!ok) return;
        this.api.delete(u.id).subscribe({
          next: () => {
            this.notify.success('Обліковий запис видалено');
            this.reload();
          },
          error: (e) => this.notify.error(e),
        });
      });
  }
}
