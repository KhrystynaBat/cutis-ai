import { HttpClient, provideHttpClient, withInterceptors } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { requestIdInterceptor } from './request-id.interceptor';

describe('requestIdInterceptor', () => {
  let http: HttpClient;
  let ctrl: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([requestIdInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    ctrl = TestBed.inject(HttpTestingController);
  });

  it('adds a UUID X-Request-ID to API calls', () => {
    http.get('/api/v1/health/live').subscribe();
    const id = ctrl.expectOne('/api/v1/health/live').request.headers.get('X-Request-ID');
    expect(id).toMatch(/^[0-9a-f-]{36}$/);
  });

  it('leaves non-API requests untouched', () => {
    http.get('/assets/x.json').subscribe();
    expect(ctrl.expectOne('/assets/x.json').request.headers.has('X-Request-ID')).toBe(false);
  });
});
