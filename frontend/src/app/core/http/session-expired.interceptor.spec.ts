import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AuthService } from '../auth/auth.service';
import { sessionExpiredInterceptor } from './session-expired.interceptor';

describe('sessionExpiredInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([]),
        provideHttpClient(withInterceptors([sessionExpiredInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  const unauthorized = { status: 401, statusText: 'Unauthorized' };

  it('signs out locally and redirects on 401 from a protected call', () => {
    const clear = vi.spyOn(TestBed.inject(AuthService), 'clear');
    http.get('/api/v1/admin/users').subscribe({ error: () => undefined });
    ctrl.expectOne('/api/v1/admin/users').flush({}, unauthorized);
    expect(clear).toHaveBeenCalled();
    expect(navigate).toHaveBeenCalledWith(['/login'], { queryParams: { expired: 1 } });
  });

  it('ignores 401 from the login and session-probe endpoints', () => {
    http.post('/api/v1/auth/login', {}).subscribe({ error: () => undefined });
    ctrl.expectOne('/api/v1/auth/login').flush({}, unauthorized);
    http.get('/api/v1/auth/me').subscribe({ error: () => undefined });
    ctrl.expectOne('/api/v1/auth/me').flush({}, unauthorized);
    expect(navigate).not.toHaveBeenCalled();
  });
});
