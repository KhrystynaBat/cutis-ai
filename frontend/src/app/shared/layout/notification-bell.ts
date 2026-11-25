import { Component, DestroyRef, OnInit, computed, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatBadgeModule } from '@angular/material/badge';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatTooltipModule } from '@angular/material/tooltip';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, interval } from 'rxjs';

import { UnreadNotifications } from '../../core/notifications/unread-notifications';

export const BELL_POLL_MS = 45_000;

@Component({
  selector: 'app-notification-bell',
  imports: [RouterLink, MatButtonModule, MatIconModule, MatBadgeModule, MatTooltipModule],
  template: `
    <a
      mat-icon-button
      routerLink="/doctor/notifications"
      [attr.aria-label]="label()"
      [matTooltip]="label()"
    >
      <mat-icon
        [matBadge]="badge()"
        [matBadgeHidden]="unread.count() === 0"
        matBadgeColor="warn"
        matBadgeSize="small"
        aria-hidden="false"
        >notifications</mat-icon
      >
    </a>
  `,
})
export class NotificationBell implements OnInit {
  protected readonly unread = inject(UnreadNotifications);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);

  readonly badge = computed(() => (this.unread.count() > 99 ? '99+' : String(this.unread.count())));
  readonly label = computed(() => {
    const n = this.unread.count();
    return n ? `Сповіщення: непрочитаних ${n}` : 'Сповіщення: непрочитаних немає';
  });

  ngOnInit(): void {
    this.unread.refresh();
    this.router.events
      .pipe(
        filter((e) => e instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.unread.refresh());
    interval(BELL_POLL_MS)
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.unread.refresh(true));
  }
}
