import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';

import { routes } from './app.routes';
import { Profile } from './core/auth/auth.models';
import { AuthService } from './core/auth/auth.service';

const users: Record<string, Profile> = {
  admin: { id: '1', firstName: 'Адмін', lastName: 'Тест', email: 'a@x.test', role: 'Admin' },
  doctor: { id: '2', firstName: 'Олена', lastName: 'Коваль', email: 'd@x.test', role: 'Doctor' },
  lab: {
    id: '3',
    firstName: 'Марта',
    lastName: 'Шевчук',
    email: 'l@x.test',
    role: 'LabSpecialist',
  },
};

describe('App routes and guards', () => {
  let http: HttpTestingController;

  async function signIn(user: Profile | null): Promise<void> {
    const auth = TestBed.inject(AuthService);
    const loaded = auth.load();
    const req = http.expectOne('/api/v1/auth/me');
    if (user) {
      req.flush(user);
    } else {
      req.flush({ error: { code: 'UNAUTHORIZED' } }, { status: 401, statusText: 'Unauthorized' });
    }
    await loaded;
  }

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  it('sends anonymous users to /login with a return URL', async () => {
    await signIn(null);
    await RouterTestingHarness.create('/admin/users');
    expect(TestBed.inject(Router).url).toBe('/login?returnUrl=%2Fadmin%2Fusers');
  });

  it.each([
    ['admin', '/admin/users'],
    ['doctor', '/doctor/dashboard'],
    ['lab', '/lab/referrals'],
  ])('redirects %s from / to the role landing page', async (key, url) => {
    await signIn(users[key]);
    await RouterTestingHarness.create('/');
    expect(TestBed.inject(Router).url).toBe(url);
    http.match(() => true);
  });

  it.each([
    ['doctor', '/admin/users'],
    ['lab', '/doctor/dashboard'],
    ['admin', '/lab/referrals'],
  ])('shows 403 when %s opens %s', async (key, url) => {
    await signIn(users[key]);
    const harness = await RouterTestingHarness.create(url);
    expect(TestBed.inject(Router).url).toBe('/403');
    expect(harness.routeNativeElement?.textContent).toContain('Доступ заборонено');
  });

  it('keeps a signed-in user away from /login', async () => {
    await signIn(users['doctor']);
    await RouterTestingHarness.create('/login');
    expect(TestBed.inject(Router).url).toBe('/doctor/dashboard');
  });

  it('shows the 404 page for unknown routes', async () => {
    await signIn(null);
    const harness = await RouterTestingHarness.create('/no/such/page');
    expect(harness.routeNativeElement?.textContent).toContain('Сторінку не знайдено');
  });
});
