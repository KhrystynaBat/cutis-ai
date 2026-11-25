import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AppNotification } from '../../core/api/notification-api';
import { UnreadNotifications } from '../../core/notifications/unread-notifications';
import { NotificationBell } from '../../shared/layout/notification-bell';
import { NotificationsPage } from './notifications.page';

const unread: AppNotification = {
  id: 'n1',
  type: 'lab_result_ready',
  title: 'Готовий результат лабораторії',
  message: 'Затверджено результат гістопатологічного дослідження за направленням REF-2026-000001.',
  isRead: false,
  createdAt: '2026-10-25T12:00:00Z',
  readAt: null,
  referral: { id: 'r1', referralNumber: 'REF-2026-000001', caseId: 'c1' },
};

describe('Notifications', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
  });

  it('bell shows the unread count; polls in the background without extending the session', () => {
    vi.useFakeTimers();
    try {
      const http = TestBed.inject(HttpTestingController);
      const fixture = TestBed.createComponent(NotificationBell);
      fixture.detectChanges();
      const first = http.expectOne('/api/v1/notifications/unread-count');
      expect(first.request.headers.has('X-Background-Poll')).toBe(false);
      first.flush({ unread: 2 });
      fixture.detectChanges();
      const link = fixture.nativeElement.querySelector('a') as HTMLAnchorElement;
      expect(link.getAttribute('href')).toBe('/doctor/notifications');
      expect(link.getAttribute('aria-label')).toBe('Сповіщення: непрочитаних 2');

      vi.advanceTimersByTime(45_000);
      const poll = http.expectOne('/api/v1/notifications/unread-count');
      expect(poll.request.headers.get('X-Background-Poll')).toBe('1');
      poll.flush({ unread: 0 });
      fixture.detectChanges();
      expect(link.getAttribute('aria-label')).toBe('Сповіщення: непрочитаних немає');
    } finally {
      vi.useRealTimers();
    }
  });

  it('lists notifications with links and marks them read', async () => {
    const http = TestBed.inject(HttpTestingController);
    const counter = TestBed.inject(UnreadNotifications);
    counter.set(1);
    const fixture = TestBed.createComponent(NotificationsPage);
    http
      .expectOne((r) => r.url === '/api/v1/notifications')
      .flush({
        items: [unread],
        total: 1,
        page: 1,
        pageSize: 20,
      });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Готовий результат лабораторії');
    const hrefs = [...el.querySelectorAll('a')].map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/doctor/referrals/r1');
    expect(hrefs).toContain('/doctor/cases/c1');

    const markBtn = [...el.querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Позначити прочитаним'),
    )!;
    markBtn.click();
    http
      .expectOne('/api/v1/notifications/n1/read')
      .flush({ ...unread, isRead: true, readAt: '2026-10-25T12:05:00Z' });
    http.expectOne('/api/v1/notifications/unread-count').flush({ unread: 0 });
    await fixture.whenStable();
    expect(counter.count()).toBe(0);
    expect(el.textContent).not.toContain('Позначити прочитаним');
    http.verify();
  });
});
