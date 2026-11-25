import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { ChangePasswordDialog } from './change-password-dialog';
import { ProfilePage } from './profile.page';

const doctor = {
  id: 'u1',
  firstName: 'Олена',
  lastName: 'Гончаренко',
  middleName: 'Віталіївна',
  email: 'olena@x.test',
  phone: '+380 (44) 200-11-01',
  role: 'Doctor',
  birthDate: '1990-12-14',
  sex: 'Female',
  lastLoginAt: '2026-11-15T21:31:00Z',
};

describe('ProfilePage', () => {
  function setup(me: object) {
    const opened: unknown[] = [];
    TestBed.configureTestingModule({
      imports: [ProfilePage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: MatDialog, useValue: { open: (c: unknown) => opened.push(c) } },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).login('x@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush(me);
    const fixture = TestBed.createComponent(ProfilePage);
    fixture.detectChanges();
    http.expectOne('/api/v1/auth/me').flush(me);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const text = () => el.textContent ?? '';
    const value = (label: string) =>
      [...el.querySelectorAll('dt')]
        .find((dt) => dt.textContent?.trim() === label)
        ?.nextElementSibling?.textContent?.trim();
    return { fixture, opened, text, value, el, http };
  }

  it('header: initials, full name and the role as text; one «Редагувати профіль»', () => {
    const { el } = setup(doctor);
    expect(el.querySelector('.avatar')?.textContent?.trim()).toBe('ОГ');
    expect(el.querySelector('h2')?.textContent?.trim()).toBe('Гончаренко Олена Віталіївна');
    expect(el.querySelector('.sub')?.textContent?.trim()).toBe('Лікар');
    expect(el.querySelector('.role')).toBeNull(); // no separate role chip
    expect(el.textContent).not.toContain('Посада');
    const links = [...el.querySelectorAll('a')].map((a) => a.textContent?.trim());
    expect(links).toEqual(['edit Редагувати профіль']);
    expect(el.textContent).not.toContain('Змінити електронну пошту');
  });

  it('blocks with formatted values', () => {
    const { text, value } = setup(doctor);
    for (const h of ['Особисті дані', 'Контактні дані', 'Безпека']) expect(text()).toContain(h);
    expect(value('Прізвище')).toBe('Гончаренко');
    expect(value('По батькові')).toBe('Віталіївна');
    expect(value('Дата народження')).toBe('14 грудня 1990');
    expect(value('Стать')).toBe('Жіноча');
    expect(value('Електронна пошта')).toBe('olena@x.test');
    expect(value('Телефон')).toBe('+380 44 200 11 01');
    expect(value('Вхід')).toBe('Підтвердження через електронну пошту');
    expect(value('Останній вхід')).toBe('15 листопада 2026, 23:31');
  });

  it('«Змінити» in the password row opens the password dialog', () => {
    const { el, opened } = setup(doctor);
    const change = [...el.querySelectorAll('button')].find(
      (b) => b.textContent?.trim() === 'Змінити',
    )!;
    expect(change.closest('div')?.textContent).toContain('••••••••');
    change.click();
    expect(opened).toEqual([ChangePasswordDialog]);
  });

  it('empty values are «Не вказано»; an administrator without a name', () => {
    const { el, value } = setup({
      id: 'a1',
      firstName: null,
      lastName: null,
      email: 'admin@x.test',
      role: 'Admin',
    });
    expect(el.querySelector('h2')?.textContent?.trim()).toBe('Адміністратор');
    expect(el.querySelector('.sub')?.textContent?.trim()).toBe('Адміністратор');
    expect(el.querySelector('.avatar mat-icon')).not.toBeNull();
    for (const label of ['Прізвище', "Ім'я", 'Дата народження', 'Стать', 'Телефон']) {
      expect(value(label)).toBe('Не вказано');
    }
  });

  it('a pending e-mail change under the address, and cancelling it', () => {
    const { fixture, el, text, http } = setup({ ...doctor, pendingEmailMasked: 'n***@gmail.com' });
    expect(el.querySelector('.pending')?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
      'Очікує підтвердження: n***@gmail.com · Скасувати',
    );
    (el.querySelector('.pending button') as HTMLButtonElement).click();
    http.expectOne({ method: 'DELETE', url: '/api/v1/auth/me/email-change' }).flush(null);
    fixture.detectChanges();
    expect(text()).not.toContain('Очікує підтвердження');
  });
});
