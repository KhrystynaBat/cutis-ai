import { Injectable, inject, signal } from '@angular/core';

import { NotificationApi } from '../api/notification-api';

@Injectable({ providedIn: 'root' })
export class UnreadNotifications {
  private readonly api = inject(NotificationApi);
  readonly count = signal(0);

  refresh(background = false): void {
    this.api.unreadCount(background).subscribe({
      next: (r) => this.count.set(r.unread),
      error: () => undefined,
    });
  }

  set(n: number): void {
    this.count.set(n);
  }
}
