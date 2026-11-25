import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { UserFormPage } from './user-form.page';

@Component({ template: '' })
class Blank {}

describe('UserFormPage', () => {
  function setup(id?: string) {
    const dialogs: unknown[] = [];
    TestBed.configureTestingModule({
      imports: [UserFormPage],
      providers: [
        provideRouter([{ path: 'admin/users', component: Blank }]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: MatDialog,
          useValue: {
            open: (_: unknown, cfg: unknown) => {
              dialogs.push(cfg);
              return { afterClosed: () => of(true) };
            },
          },
        },
      ],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(UserFormPage);
    if (id) fixture.componentRef.setInput('id', id);
    fixture.detectChanges();
    return { http, fixture, dialogs };
  }

  it('accepts Gmail sub-addresses with "+"', () => {
    const { fixture } = setup();
    const email = fixture.componentInstance.form.controls.email;
    email.setValue('katerynakalyna2026+doctor1@gmail.com');
    expect(email.hasError('email')).toBe(false);
    email.setValue('not an address');
    expect(email.hasError('email')).toBe(true);
  });

  it('creates a user with по батькові and phone; empty optional fields are sent as null', () => {
    const { http, fixture, dialogs } = setup();
    const page = fixture.componentInstance;
    page.form.patchValue({
      firstName: ' Олена ',
      lastName: 'Гончаренко',
      middleName: 'Віталіївна',
      phone: '+380 (44) 200-11-01',
      email: 'olena@x.test',
      role: 'Doctor',
    });
    page.save();
    const req = http.expectOne({ method: 'POST', url: '/api/v1/admin/users' });
    expect(req.request.body).toEqual({
      firstName: 'Олена',
      lastName: 'Гончаренко',
      middleName: 'Віталіївна',
      phone: '+380 (44) 200-11-01',
      birthDate: null,
      sex: null,
      email: 'olena@x.test',
      role: 'Doctor',
      isActive: true,
    });
    req.flush({
      user: { id: 'u1', firstName: 'Олена', lastName: 'Гончаренко', middleName: 'Віталіївна' },
      invitation: {
        token: 't'.repeat(40),
        expiresAt: '2026-11-12T10:00:00Z',
        purpose: 'Invitation',
      },
    });
    expect(dialogs.length).toBe(1);

    page.form.patchValue({ middleName: '', phone: '' });
    page.save();
    const req2 = http.expectOne({ method: 'POST', url: '/api/v1/admin/users' });
    expect(req2.request.body.middleName).toBeNull();
    expect(req2.request.body.phone).toBeNull();
    http.verify();
  });

  it('rejects an invalid phone and shows EMAIL_TAKEN on the email field', () => {
    const { http, fixture } = setup();
    const page = fixture.componentInstance;
    page.form.patchValue({
      firstName: 'Олена',
      lastName: 'Гончаренко',
      email: 'o@x.test',
      phone: 'abc',
    });
    page.save();
    http.expectNone('/api/v1/admin/users');
    expect(page.form.controls.phone.hasError('pattern')).toBe(true);

    page.form.patchValue({ phone: '' });
    page.save();
    http
      .expectOne({ method: 'POST', url: '/api/v1/admin/users' })
      .flush(
        { error: { code: 'EMAIL_TAKEN', message: 'зайнято', correlationId: 'x' } },
        { status: 409, statusText: 'Conflict' },
      );
    expect(page.form.controls.email.hasError('taken')).toBe(true);
    http.verify();
  });

  it('edits: loads the user (null phone → empty field) and saves with PATCH', () => {
    const { http, fixture } = setup('u1');
    http.expectOne('/api/v1/admin/users/u1').flush({
      id: 'u1',
      firstName: 'Тарас',
      lastName: 'Франко',
      middleName: null,
      phone: null,
      email: 't@x.test',
      role: 'LabSpecialist',
    });
    const page = fixture.componentInstance;
    expect(page.form.controls.phone.value).toBe('');
    expect(page.form.controls.middleName.value).toBe('');
    page.form.patchValue({ phone: '+380501112233' });
    page.save();
    const req = http.expectOne({ method: 'PATCH', url: '/api/v1/admin/users/u1' });
    expect(req.request.body.phone).toBe('+380501112233');
    expect(req.request.body.isActive).toBeUndefined();
    req.flush({});
    http.verify();
  });
});
