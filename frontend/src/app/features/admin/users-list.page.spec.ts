import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AdminUser } from '../../core/api/admin-users-api';
import { UsersListPage } from './users-list.page';

const user = (over: Partial<AdminUser>): AdminUser => ({
  id: 'u1',
  firstName: 'Олена',
  lastName: 'Гончаренко',
  middleName: 'Віталіївна',
  phone: '+380 (44) 200-11-01',
  email: 'olena@x.test',
  role: 'Doctor',
  status: 'Active',
  hasPassword: true,
  createdAt: '2026-11-01T10:00:00Z',
  lastLoginAt: null,
  ...over,
});
const empty = { items: [], total: 0, page: 1, pageSize: 20 };

describe('UsersListPage', () => {
  function setup(confirm = true) {
    const opened: { data: { message?: string } }[] = [];
    TestBed.configureTestingModule({
      imports: [UsersListPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: MatDialog,
          useValue: {
            open: (_: unknown, cfg: { data: { message?: string } }) => {
              opened.push(cfg);
              return { afterClosed: () => of(confirm) };
            },
          },
        },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UsersListPage);
    const list = () => http.expectOne((r) => r.url === '/api/v1/admin/users');
    return { http, fixture, opened, list };
  }

  it('shows the phone column, «—» without a phone and a hint without a password', async () => {
    const { http, fixture, list } = setup();
    list().flush({
      items: [user({}), user({ id: 'u2', phone: null, hasPassword: false, role: 'LabSpecialist' })],
      total: 2,
      page: 1,
      pageSize: 20,
    });
    await fixture.whenStable();
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Телефон');
    expect(text).toContain('+380 (44) 200-11-01');
    expect(text).toContain('—');
    expect(text).toContain('пароль не встановлено');
    expect(text).toContain('Гончаренко Олена Віталіївна');
    http.verify();
  });

  it('deletes after a short confirmation (no how-to text) and reloads', () => {
    const { http, fixture, opened, list } = setup();
    list().flush(empty);
    fixture.componentInstance.remove(user({}));
    expect(opened[0].data.message).toBe(
      'Обліковий запис Гончаренко Олена Віталіївна буде видалено назавжди.',
    );
    http.expectOne({ method: 'DELETE', url: '/api/v1/admin/users/u1' }).flush(null);
    list().flush(empty);
    http.verify();
  });

  it('blocks a user after confirmation; a cancelled dialog sends nothing', () => {
    const { http, fixture, opened, list } = setup(true);
    list().flush(empty);
    fixture.componentInstance.changeStatus(user({}), 'block');
    expect(opened[0].data.message).toContain('не зможе увійти');
    http
      .expectOne({ method: 'POST', url: '/api/v1/admin/users/u1/block' })
      .flush(user({ status: 'Blocked' }));
    list().flush(empty);
    http.verify();

    TestBed.resetTestingModule();
    const second = setup(false);
    second.list().flush(empty);
    second.fixture.componentInstance.changeStatus(user({}), 'deactivate');
    second.http.expectNone('/api/v1/admin/users/u1/deactivate');
    second.http.verify();
  });

  it('pages and filters go to the API; a filter resets to page 1', () => {
    const { http, fixture, list } = setup();
    list().flush(empty);
    const page = fixture.componentInstance;
    page.onPage({ pageIndex: 2, pageSize: 50, length: 200 });
    const p3 = list();
    expect(p3.request.params.get('page')).toBe('3');
    expect(p3.request.params.get('pageSize')).toBe('50');
    p3.flush(empty);
    page.role.setValue('LabSpecialist');
    const req = list();
    expect(req.request.params.get('role')).toBe('LabSpecialist');
    expect(req.request.params.get('page')).toBe('1');
    req.flush(empty);
    expect(page.hasFilters()).toBe(true);
    http.verify();
  });
});
