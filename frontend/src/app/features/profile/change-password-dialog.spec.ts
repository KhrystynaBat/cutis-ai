import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialogRef } from '@angular/material/dialog';

import { AuthService } from '../../core/auth/auth.service';
import { ChangePasswordDialog } from './change-password-dialog';

describe('ChangePasswordDialog', () => {
  it('shows one short hint (no checklist), rejects a password with the name, then changes it', () => {
    const closed: unknown[] = [];
    TestBed.configureTestingModule({
      imports: [ChangePasswordDialog],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MatDialogRef, useValue: { close: (v: unknown) => closed.push(v) } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).login('olena@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush({
      id: 'u1',
      firstName: 'Олена',
      lastName: 'Коваленко',
      middleName: null,
      email: 'olena@x.test',
      role: 'Doctor',
    });

    const fixture = TestBed.createComponent(ChangePasswordDialog);
    fixture.detectChanges();
    http.expectOne('common-passwords.txt').flush('password\nqwerty\n');
    const dlg = fixture.componentInstance;
    dlg.form.setValue({
      currentPassword: 'Old-Pass-w0rd!',
      newPassword: 'Коваленко#26xZ',
      confirmPassword: 'Коваленко#26xZ',
    });
    fixture.detectChanges();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain("Пароль не може містити електронну пошту, ім'я чи прізвище");
    expect(text).not.toContain('Без електронної пошти, імені чи прізвища'); // no checklist
    expect(text).not.toContain('Надійність');
    dlg.save();
    expect(dlg.newPasswordError()).toBe(
      "Пароль не може містити електронну пошту, ім'я чи прізвище",
    );
    http.expectNone('/api/v1/auth/change-password');

    dlg.form.patchValue({ newPassword: 'Zx!9mLpR2tq#', confirmPassword: 'Zx!9mLpR2tq#' });
    fixture.detectChanges();
    expect(dlg.hint()).toBeNull();
    expect(fixture.nativeElement.querySelector('mat-hint')).toBeNull();
    dlg.save();
    const req = http.expectOne('/api/v1/auth/change-password');
    expect(req.request.body).toEqual({
      currentPassword: 'Old-Pass-w0rd!',
      newPassword: 'Zx!9mLpR2tq#',
    });
    req.flush(null);
    expect(closed).toEqual([true]);
    http.verify();
  });
});
