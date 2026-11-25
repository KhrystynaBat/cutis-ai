import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { LoginConfirmPage } from './login-confirm.page';

describe('LoginConfirmPage', () => {
  let fixture: ComponentFixture<LoginConfirmPage>;
  let http: HttpTestingController;
  let navigateByUrl: ReturnType<typeof vi.spyOn>;

  function setup(token?: string): HTMLElement {
    TestBed.configureTestingModule({
      imports: [LoginConfirmPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    navigateByUrl = vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    fixture = TestBed.createComponent(LoginConfirmPage);
    if (token) fixture.componentRef.setInput('token', token);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  afterEach(() => http.verify());

  it('opening the page sends nothing; the button confirms and goes to the role home', () => {
    const el = setup('t'.repeat(43));
    http.expectNone('/api/v1/auth/login/confirm');
    expect(el.textContent).toContain('Підтвердити вхід');
    (el.querySelector('button') as HTMLButtonElement).click();
    const req = http.expectOne({ method: 'POST', url: '/api/v1/auth/login/confirm' });
    expect(req.request.body).toEqual({ token: 't'.repeat(43) });
    req.flush({ id: '1', firstName: 'Т', lastName: 'Ф', email: 'l@x.test', role: 'LabSpecialist' });
    expect(TestBed.inject(AuthService).user()?.role).toBe('LabSpecialist');
    expect(navigateByUrl).toHaveBeenCalledWith('/lab/referrals');
  });

  it.each([
    [410, 'LOGIN_LINK_EXPIRED', 'Посилання недійсне або прострочене. Увійдіть ще раз.'],
    [400, 'LOGIN_LINK_INVALID', 'Посилання недійсне або прострочене. Увійдіть ще раз.'],
    [409, 'LOGIN_OTHER_BROWSER', 'Відкрийте посилання в тому браузері, де ви вводили пароль.'],
  ])('shows a short message for %s %s', async (status, code, text) => {
    const el = setup('t'.repeat(43));
    fixture.componentInstance.confirm();
    http
      .expectOne('/api/v1/auth/login/confirm')
      .flush({ error: { code, message: 'x' } }, { status, statusText: 'Error' });
    fixture.detectChanges();
    await fixture.whenStable();
    expect(el.textContent).toContain(text);
    expect(el.querySelector('a[href="/login"]')).not.toBeNull();
    expect(navigateByUrl).not.toHaveBeenCalled();
  });

  it('without a token shows the invalid-link message', () => {
    const el = setup();
    expect(el.textContent).toContain('Посилання недійсне або прострочене');
    expect(el.querySelector('button')).toBeNull();
  });
});
