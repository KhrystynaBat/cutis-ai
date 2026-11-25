import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { EMAIL_LINK_INVALID, EmailConfirmPage } from './email-confirm.page';

describe('EmailConfirmPage', () => {
  function setup(token?: string) {
    TestBed.configureTestingModule({
      imports: [EmailConfirmPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(EmailConfirmPage);
    if (token) fixture.componentRef.setInput('token', token);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const button = () =>
      [...el.querySelectorAll('button')].find((b) => b.textContent?.trim() === 'Підтвердити');
    return { http, fixture, el, button };
  }

  it('opening the page changes nothing: only the button confirms', () => {
    const { http, fixture, el, button } = setup('t'.repeat(43));
    http.expectNone('/api/v1/auth/email-change/confirm');
    expect(el.textContent).toContain('Підтвердження нової адреси');
    button()!.click();
    const req = http.expectOne({ method: 'POST', url: '/api/v1/auth/email-change/confirm' });
    expect(req.request.body).toEqual({ token: 't'.repeat(43) });
    req.flush({ emailMasked: 'n***@gmail.com', signedIn: false });
    http.expectOne('/api/v1/auth/me').flush(null, { status: 401, statusText: 'Unauthorized' });
    fixture.detectChanges();
    expect(el.textContent).toContain(
      'Адресу змінено. Тепер для входу використовуйте n***@gmail.com.',
    );
    expect(el.textContent).toContain('До сторінки входу');
  });

  it('a used or expired link', () => {
    const { http, fixture, el, button } = setup('t'.repeat(43));
    button()!.click();
    http
      .expectOne('/api/v1/auth/email-change/confirm')
      .flush(
        { error: { code: 'EMAIL_CHANGE_LINK_EXPIRED', message: 'x' } },
        { status: 410, statusText: 'Gone' },
      );
    fixture.detectChanges();
    expect(el.textContent).toContain(EMAIL_LINK_INVALID);
  });

  it('without a token there is nothing to confirm', () => {
    const { el, button } = setup();
    expect(el.textContent).toContain(EMAIL_LINK_INVALID);
    expect(button()).toBeUndefined();
  });
});
