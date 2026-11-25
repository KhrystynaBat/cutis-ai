import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatPaginatorModule, PageEvent } from '@angular/material/paginator';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';

import { AppNotification, NotificationApi } from '../../core/api/notification-api';
import { UnreadNotifications } from '../../core/notifications/unread-notifications';
import { NotifyService } from '../../core/notify.service';

@Component({
  selector: 'app-notifications-page',
  imports: [
    DatePipe,
    RouterLink,
    MatButtonModule,
    MatIconModule,
    MatPaginatorModule,
    MatProgressBarModule,
    MatSlideToggleModule,
  ],
  template: `
    <section class="dl-card">
      <div class="dl-list-header">
        <h2 class="dl-page-title">Сповіщення</h2>
        <button
          mat-stroked-button
          type="button"
          (click)="markAll()"
          [disabled]="unread.count() === 0 || busy()"
        >
          <mat-icon>done_all</mat-icon> Позначити всі прочитаними
        </button>
      </div>
      <mat-slide-toggle [checked]="unreadOnly()" (change)="toggleUnread($event.checked)">
        Лише непрочитані
      </mat-slide-toggle>
      @if (loading()) {
        <mat-progress-bar mode="indeterminate" aria-label="Завантаження" />
      }
      @if (loadError()) {
        <p class="dl-error-text">
          Не вдалося завантажити сповіщення.
          <button mat-button type="button" (click)="reload()">Повторити</button>
        </p>
      } @else if (!loading() && items().length === 0) {
        <p class="dl-empty">
          {{ unreadOnly() ? 'Непрочитаних сповіщень немає.' : 'Сповіщень ще немає.' }}
        </p>
      }
      <ul class="list">
        @for (n of items(); track n.id) {
          <li [class.unread]="!n.isRead">
            <mat-icon aria-hidden="true">{{ n.isRead ? 'drafts' : 'mark_email_unread' }}</mat-icon>
            <div class="body">
              <p class="title">
                {{ n.title }}
                @if (!n.isRead) {
                  <span class="visually-hidden">(непрочитане)</span>
                }
              </p>
              <p>{{ n.message }}</p>
              <p class="dl-muted small">{{ n.createdAt | date: 'dd.MM.yyyy HH:mm' }}</p>
              @if (n.referral; as r) {
                <div class="links">
                  <a mat-button [routerLink]="['/doctor/referrals', r.id]" (click)="read(n)">
                    <mat-icon>science</mat-icon> Відкрити результат {{ r.referralNumber }}
                  </a>
                  <a mat-button [routerLink]="['/doctor/cases', r.caseId]" (click)="read(n)">
                    <mat-icon>clinical_notes</mat-icon> Випадок
                  </a>
                </div>
              }
            </div>
            @if (!n.isRead) {
              <button mat-button type="button" (click)="read(n)">Позначити прочитаним</button>
            }
          </li>
        }
      </ul>
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
  styles: `
    .list {
      list-style: none;
      margin: 12px 0 0;
      padding: 0;
    }
    li {
      display: flex;
      gap: 12px;
      align-items: flex-start;
      padding: 12px 8px;
      border-bottom: 1px solid var(--dl-border);
      flex-wrap: wrap;
    }
    li.unread {
      background: #eef6f5;
    }
    li.unread .title {
      font-weight: 700;
    }
    .body {
      flex: 1;
      min-width: 0;
      p {
        margin: 0 0 4px;
        overflow-wrap: anywhere;
      }
    }
    .links {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-left: -12px;
    }
    .small {
      font: var(--mat-sys-body-small);
    }
  `,
})
export class NotificationsPage {
  private readonly api = inject(NotificationApi);
  private readonly notify = inject(NotifyService);
  protected readonly unread = inject(UnreadNotifications);

  readonly items = signal<AppNotification[]>([]);
  readonly total = signal(0);
  readonly page = signal(1);
  readonly pageSize = signal(20);
  readonly unreadOnly = signal(false);
  readonly loading = signal(false);
  readonly loadError = signal(false);
  readonly busy = signal(false);

  constructor() {
    this.reload();
  }

  reload(): void {
    this.loading.set(true);
    this.loadError.set(false);
    this.api
      .list({ unreadOnly: this.unreadOnly(), page: this.page(), pageSize: this.pageSize() })
      .subscribe({
        next: (p) => {
          this.items.set(p.items);
          this.total.set(p.total);
          this.loading.set(false);
        },
        error: (e) => {
          this.loading.set(false);
          this.loadError.set(true);
          this.notify.error(e, 'Не вдалося завантажити сповіщення');
        },
      });
  }

  read(n: AppNotification): void {
    if (n.isRead) return;
    this.api.markRead(n.id).subscribe({
      next: (updated) => {
        this.items.update((list) => list.map((x) => (x.id === n.id ? updated : x)));
        this.unread.refresh();
      },
      error: (e) => this.notify.error(e),
    });
  }

  markAll(): void {
    this.busy.set(true);
    this.api.markAllRead().subscribe({
      next: (r) => {
        this.busy.set(false);
        this.unread.set(r.unread);
        this.reload();
      },
      error: (e) => {
        this.busy.set(false);
        this.notify.error(e);
      },
    });
  }

  toggleUnread(on: boolean): void {
    this.unreadOnly.set(on);
    this.page.set(1);
    this.reload();
  }

  onPage(e: PageEvent): void {
    this.page.set(e.pageIndex + 1);
    this.pageSize.set(e.pageSize);
    this.reload();
  }
}
