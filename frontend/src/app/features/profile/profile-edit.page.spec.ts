import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import { EmailChangeDialog } from './email-change-dialog';
import { ProfileEditPage } from './profile-edit.page';

const me = {
  id: 'u1',
  firstName: 'Олена',
  lastName: 'Гончаренко',
  middleName: 'Віталіївна',
  phone: null,
  birthDate: null,
  sex: null,
  email: 'o@x.test',
  role: 'Doctor',
};

describe('ProfileEditPage', () => {
  function setup(dialogResult: unknown = undefined) {
    const opened: { component: unknown; data: unknown }[] = [];
    TestBed.configureTestingModule({
      imports: [ProfileEditPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: MatDialog,
          useValue: {
            open: (component: unknown, cfg: { data: unknown }) => {
              opened.push({ component, data: cfg.data });
              return { afterClosed: () => of(dialogResult) };
            },
          },
        },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).login('o@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush(me);
    const navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    const notify = TestBed.inject(NotifyService);
    const info = vi.spyOn(notify, 'info').mockImplementation(() => undefined);
    const success = vi.spyOn(notify, 'success').mockImplementation(() => undefined);
    const fixture = TestBed.createComponent(ProfileEditPage);
    fixture.detectChanges();
    const page = fixture.componentInstance;
    const el = fixture.nativeElement as HTMLElement;
    return { http, fixture, page, el, opened, navigate, info, success };
  }

  it('one form: personal and contact blocks, the e-mail included; no role', () => {
    const { page, el } = setup();
    expect(page.form.controls.lastName.value).toBe('Гончаренко');
    expect(page.form.controls.email.value).toBe('o@x.test');
    expect(el.textContent).not.toContain('Посада');
    expect(el.textContent).toContain('Особисті дані');
    expect(el.textContent).toContain('Контактні дані');
    expect(el.querySelector('input[type=email]')).not.toBeNull();
    expect(el.textContent).not.toContain('Роль');
    const actions = [...el.querySelectorAll('.form-actions a, .form-actions button')].map((b) =>
      b.textContent?.trim(),
    );
    expect(actions).toEqual(['Скасувати', 'Зберегти']);
  });

  it('the same e-mail: saved at once, no password dialog', () => {
    const { http, page, opened, navigate, success } = setup();
    page.form.patchValue({
      email: 'O@x.test',
      phone: '+380 (50) 111-22-33',
      extra: { birthDate: '1985-04-12', sex: 'Female' },
    });
    page.save();
    expect(opened).toEqual([]);
    const req = http.expectOne({ method: 'PATCH', url: '/api/v1/auth/me' });
    expect(req.request.body).toEqual({
      firstName: 'Олена',
      lastName: 'Гончаренко',
      middleName: 'Віталіївна',
      phone: '+380 (50) 111-22-33',
      birthDate: '1985-04-12',
      sex: 'Female',
    });
    req.flush(me);
    expect(success).toHaveBeenCalledWith('Зміни збережено');
    expect(navigate).toHaveBeenCalledWith(['/profile']);
  });

  it('a new e-mail: the password dialog, then the other fields; the e-mail waits for the letter', () => {
    const { http, page, opened, navigate, info } = setup({
      sent: true,
      pendingEmailMasked: 'n***@gmail.com',
    });
    page.form.patchValue({ email: 'nadia@gmail.com', phone: '+380 (50) 111-22-33' });
    page.save();
    expect(opened).toEqual([
      { component: EmailChangeDialog, data: { newEmail: 'nadia@gmail.com' } },
    ]);
    const req = http.expectOne({ method: 'PATCH', url: '/api/v1/auth/me' });
    expect(req.request.body.email).toBeUndefined();
    req.flush(me);
    expect(info).toHaveBeenCalledWith(
      'Інші дані збережено. Щоб змінити електронну пошту, перейдіть за посиланням у листі, який ми надіслали на n***@gmail.com.',
    );
    expect(navigate).toHaveBeenCalledWith(['/profile']);
  });

  it('a cancelled dialog saves nothing', () => {
    const { http, page, navigate } = setup(undefined);
    page.form.patchValue({ email: 'nadia@gmail.com' });
    page.save();
    http.expectNone('/api/v1/auth/me');
    expect(navigate).not.toHaveBeenCalled();
  });

  it('a busy address is shown on the e-mail field, nothing saved', () => {
    const { http, page, fixture, el } = setup({
      sent: false,
      code: 'EMAIL_TAKEN',
      message: 'Ця адреса вже використовується',
    });
    page.form.patchValue({ email: 'taken@gmail.com' });
    page.save();
    http.expectNone('/api/v1/auth/me');
    fixture.detectChanges();
    expect(page.form.controls.email.hasError('taken')).toBe(true);
    expect(el.textContent).toContain('Ця адреса вже використовується');
  });

  it('checks the birth date like the backend (not in the future, 18–100 years)', () => {
    const { http, page } = setup();
    const birth = page.form.controls.extra.controls.birthDate;
    birth.setValue('2999-01-01');
    expect(birth.hasError('future')).toBe(true);
    birth.setValue(`${new Date().getFullYear() - 10}-01-01`);
    expect(birth.hasError('age')).toBe(true);
    page.save();
    http.expectNone('/api/v1/auth/me');
    birth.setValue('1985-04-12');
    expect(birth.valid).toBe(true);
  });
});
