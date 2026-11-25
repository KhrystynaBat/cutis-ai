import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';

import { AuthService } from '../../core/auth/auth.service';
import { EmailChangeDialog } from './email-change-dialog';

describe('EmailChangeDialog («Підтвердіть зміну електронної пошти»)', () => {
  function setup() {
    const close = vi.fn();
    TestBed.configureTestingModule({
      imports: [EmailChangeDialog],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MatDialogRef, useValue: { close } },
        { provide: MAT_DIALOG_DATA, useValue: { newEmail: 'nadia@gmail.com' } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const auth = TestBed.inject(AuthService);
    auth.login('olena@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush({
      id: 'u1',
      firstName: 'Олена',
      lastName: 'Гончаренко',
      email: 'olena@x.test',
      role: 'Doctor',
    });
    const fixture = TestBed.createComponent(EmailChangeDialog);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { http, fixture, dialog: fixture.componentInstance, close, auth, el };
  }

  it('shows the new address and needs the current password', () => {
    const { http, dialog, el } = setup();
    expect(el.textContent).toContain('Підтвердіть зміну електронної пошти');
    expect(el.textContent).toContain('nadia@gmail.com');
    dialog.confirm();
    expect(dialog.form.controls.currentPassword.hasError('required')).toBe(true);
    http.expectNone('/api/v1/auth/me/email-change');
  });

  it('sends the request and closes with the masked address', () => {
    const { http, dialog, close, auth } = setup();
    dialog.form.setValue({ currentPassword: 'secret' });
    dialog.confirm();
    const req = http.expectOne({ method: 'POST', url: '/api/v1/auth/me/email-change' });
    expect(req.request.body).toEqual({ newEmail: 'nadia@gmail.com', currentPassword: 'secret' });
    req.flush({ pendingEmailMasked: 'n***@gmail.com', expiresAt: '2026-11-17T10:00:00Z' });
    expect(close).toHaveBeenCalledWith({ sent: true, pendingEmailMasked: 'n***@gmail.com' });
    expect(auth.user()?.pendingEmailMasked).toBe('n***@gmail.com');
    expect(auth.user()?.email).toBe('olena@x.test'); // unchanged until confirmed
  });

  it('a wrong password stays in the dialog; a busy address closes it for the form', () => {
    const { http, dialog, fixture, close, el } = setup();
    dialog.form.setValue({ currentPassword: 'bad' });
    dialog.confirm();
    http
      .expectOne('/api/v1/auth/me/email-change')
      .flush(
        { error: { code: 'WRONG_PASSWORD', message: 'Поточний пароль невірний' } },
        { status: 400, statusText: 'Bad Request' },
      );
    fixture.detectChanges();
    expect(close).not.toHaveBeenCalled();
    expect(el.textContent).toContain('Поточний пароль невірний');

    dialog.form.setValue({ currentPassword: 'secret' });
    dialog.confirm();
    http
      .expectOne('/api/v1/auth/me/email-change')
      .flush(
        { error: { code: 'EMAIL_TAKEN', message: 'Ця адреса вже використовується' } },
        { status: 409, statusText: 'Conflict' },
      );
    expect(close).toHaveBeenCalledWith({
      sent: false,
      code: 'EMAIL_TAKEN',
      message: 'Ця адреса вже використовується',
    });
  });
});
