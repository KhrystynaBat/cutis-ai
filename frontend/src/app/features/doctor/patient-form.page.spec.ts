import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { PatientFormPage } from './patient-form.page';

describe('PatientFormPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PatientFormPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
  });

  afterEach(() => http.verify());

  const valid = {
    firstName: ' Ганна ',
    lastName: 'Пацієнт',
    dateOfBirth: '1985-04-12',
    email: '',
    phone: '',
    notes: '',
  };

  it('does not submit without the required fields', () => {
    const page = TestBed.createComponent(PatientFormPage).componentInstance;
    page.form.patchValue({ ...valid, lastName: '' });
    page.save();
    http.expectNone('/api/v1/patients');
  });

  it('rejects a future date of birth', () => {
    const page = TestBed.createComponent(PatientFormPage).componentInstance;
    page.form.patchValue({ ...valid, dateOfBirth: '2999-01-01' });
    expect(page.form.controls.dateOfBirth.hasError('future')).toBe(true);
  });

  it('sends trimmed values and nulls for empty optional fields', () => {
    const page = TestBed.createComponent(PatientFormPage).componentInstance;
    page.form.patchValue(valid);
    page.save();
    const req = http.expectOne('/api/v1/patients');
    expect(req.request.body).toEqual({
      firstName: 'Ганна',
      lastName: 'Пацієнт',
      middleName: null,
      dateOfBirth: '1985-04-12',
      email: null,
      phone: null,
      notes: null,
    });
    req.flush({ id: 'p1' });
  });

  it('sends the patronymic (по батькові) trimmed', () => {
    const page = TestBed.createComponent(PatientFormPage).componentInstance;
    page.form.patchValue({ ...valid, middleName: '  Василівна ' });
    page.save();
    const req = http.expectOne('/api/v1/patients');
    expect(req.request.body.middleName).toBe('Василівна');
    req.flush({ id: 'p1' });
  });
});
