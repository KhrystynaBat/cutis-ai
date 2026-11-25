import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentRef } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { LoginPage } from './login.page';

describe('LoginPage', () => {
  let fixture: ComponentFixture<LoginPage>;
  let ref: ComponentRef<LoginPage>;
  let http: HttpTestingController;
  let navigateByUrl: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [LoginPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    navigateByUrl = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginPage);
    ref = fixture.componentRef;
  });

  afterEach(() => http.verify());

  function submit(email = 'doc@x.test', password = 'Secret-pass-1'): void {
    fixture.componentInstance.form.setValue({ email, password });
    fixture.componentInstance.submit();
  }

  it('does not call the API when the form is invalid', () => {
    submit('not-an-email', '');
    http.expectNone('/api/v1/auth/login');
  });

  it('logs in and goes to the role landing page', () => {
    submit();
    http.expectOne('/api/v1/auth/login').flush({
      id: '1',
      firstName: 'О',
      lastName: 'К',
      email: 'doc@x.test',
      role: 'Doctor',
    });
    expect(TestBed.inject(AuthService).user()?.role).toBe('Doctor');
    expect(navigateByUrl).toHaveBeenCalledWith('/doctor/dashboard');
  });

  it('honours a same-app return URL but never an external one', () => {
    ref.setInput('returnUrl', '//evil.example/x');
    submit();
    http
      .expectOne('/api/v1/auth/login')
      .flush({ id: '1', firstName: 'A', lastName: 'B', email: 'a@x.test', role: 'Admin' });
    expect(navigateByUrl).toHaveBeenLastCalledWith('/admin/users');

    ref.setInput('returnUrl', '/admin/users/42/edit');
    submit();
    http
      .expectOne('/api/v1/auth/login')
      .flush({ id: '1', firstName: 'A', lastName: 'B', email: 'a@x.test', role: 'Admin' });
    expect(navigateByUrl).toHaveBeenLastCalledWith('/admin/users/42/edit');
  });

  it('shows the backend message and clears the password on failure', async () => {
    submit();
    http
      .expectOne('/api/v1/auth/login')
      .flush(
        { error: { code: 'INVALID_CREDENTIALS', message: 'Невірна електронна пошта або пароль' } },
        { status: 401, statusText: 'Unauthorized' },
      );
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Невірна електронна пошта або пароль',
    );
    expect(fixture.componentInstance.form.controls.password.value).toBe('');
    expect(navigateByUrl).not.toHaveBeenCalled();
  });

  describe('confirmation by e-mail', () => {
    const pending = {
      status: 'confirmation_required',
      emailMasked: 'k***@gmail.com',
      expiresInMinutes: 10,
    };

    afterEach(() => vi.useRealTimers());

    it('shows "check your e-mail" instead of signing in', async () => {
      submit();
      http.expectOne('/api/v1/auth/login').flush(pending);
      await fixture.whenStable();
      const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
      expect(text).toContain('Перевірте пошту');
      expect(text).toContain('Ми надіслали посилання для входу на k***@gmail.com');
      expect(text).toContain('Посилання дійсне 10 хвилин');
      expect(text).not.toContain('Відкрийте його в цьому браузері');
      expect(text).not.toContain('папку «Спам»');
      expect(TestBed.inject(AuthService).user()).toBeNull();
      expect(navigateByUrl).not.toHaveBeenCalled();
      expect(fixture.componentInstance.form.controls.password.value).toBe('');
    });

    it('allows a resend only after the 60 s countdown', () => {
      vi.useFakeTimers();
      submit();
      http.expectOne('/api/v1/auth/login').flush(pending);
      const page = fixture.componentInstance;
      expect(page.resendIn()).toBe(60);
      page.resend();
      http.expectNone('/api/v1/auth/login/resend');
      vi.advanceTimersByTime(30_000);
      expect(page.resendIn()).toBe(30);
      vi.advanceTimersByTime(30_000);
      expect(page.resendIn()).toBe(0);
      page.resend();
      http.expectOne({ method: 'POST', url: '/api/v1/auth/login/resend' }).flush(pending);
      expect(page.resendInfo()).toBe('Лист надіслано ще раз.');
      expect(page.resendIn()).toBe(60);
    });

    it('shows the limit message from the backend and goes back to the form', () => {
      vi.useFakeTimers();
      submit();
      http.expectOne('/api/v1/auth/login').flush(pending);
      const page = fixture.componentInstance;
      vi.advanceTimersByTime(60_000);
      page.resend();
      http.expectOne('/api/v1/auth/login/resend').flush(
        {
          error: {
            code: 'TOO_MANY_LETTERS',
            message: 'Забагато листів для входу. Спробуйте через 15 хв',
          },
        },
        { status: 429, statusText: 'Too Many Requests' },
      );
      expect(page.error()).toContain('Забагато листів');
      page.backToLogin();
      expect(page.pending()).toBeNull();
      expect(page.error()).toBeNull();
    });
  });
});
