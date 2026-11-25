import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { DoctorDashboardPage } from './dashboard.page';

const patient = {
  id: 'p1',
  firstName: 'Оксана',
  lastName: 'Мороз',
  middleName: 'Сергіївна',
  dateOfBirth: '1990-01-01',
};
const emptyDashboard = {
  patients: 0,
  activeCases: 0,
  pendingReferrals: 0,
  readyResults: 0,
  recentCases: [],
};

describe('DoctorDashboardPage', () => {
  function setup(greetingName: string | null = 'Олено Віталіївно') {
    TestBed.configureTestingModule({
      imports: [DoctorDashboardPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).login('o@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush({
      id: 'd1',
      firstName: 'Олена',
      lastName: 'Гончаренко',
      middleName: 'Віталіївна',
      email: 'o@x.test',
      role: 'Doctor',
      greetingName,
    });
    const fixture = TestBed.createComponent(DoctorDashboardPage);
    fixture.detectChanges();
    const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
    return { http, fixture, text };
  }

  it('greets with name and по батькові, shows counters, new lab results and recent cases', () => {
    const { http, fixture, text } = setup();
    http.expectOne('/api/v1/doctor/dashboard').flush({
      patients: 5,
      activeCases: 3,
      pendingReferrals: 2,
      readyResults: 1,
      recentCases: [
        { id: 'c1', patient, examinedAt: '2026-11-09', bodyLocation: 'спина', status: 'Referred' },
      ],
    });
    const req = http.expectOne((r) => r.url === '/api/v1/referrals');
    expect(req.request.params.get('status')).toBe('Completed');
    expect(req.request.params.get('caseStatus')).toBe('Referred');
    req.flush({
      items: [
        {
          id: 'r1',
          referralNumber: 'REF-2026-000004',
          status: 'Completed',
          patient,
          caseId: 'c1',
          bodyLocation: 'тулуб',
        },
      ],
      total: 1,
      page: 1,
      pageSize: 5,
    });
    fixture.detectChanges();
    expect(text()).toContain('Вітаємо, Олено Віталіївно!');
    expect(text()).toContain('Мої пацієнти');
    expect(text()).toContain('REF-2026-000004');
    expect(text()).toContain('Мороз');
    expect(text()).not.toContain('Затверджені результати; випадок ще не завершено');
    http.verify();
  });

  it('greets without a name when the vocative could not be formed', () => {
    const { http, fixture, text } = setup(null);
    http.expectOne('/api/v1/doctor/dashboard').flush(emptyDashboard);
    fixture.detectChanges();
    expect(text()).toContain('Вітаємо!');
    expect(text()).not.toContain('Вітаємо, ');
    http.match(() => true);
  });

  it('empty states are one short sentence; no extra request without ready results', () => {
    const { http, fixture, text } = setup();
    http.expectOne('/api/v1/doctor/dashboard').flush(emptyDashboard);
    fixture.detectChanges();
    expect(text()).toContain('Результатів, що очікують ознайомлення, немає.');
    expect(text()).toContain('Випадків ще немає.');
    http.verify();
  });

  it('a failed load offers «Повторити»', () => {
    const { http, fixture, text } = setup();
    http.expectOne('/api/v1/doctor/dashboard').flush(null, { status: 500, statusText: 'Error' });
    fixture.detectChanges();
    expect(text()).toContain('Не вдалося завантажити дані.');
    fixture.componentInstance.load();
    http.expectOne('/api/v1/doctor/dashboard').flush({ ...emptyDashboard, patients: 1 });
    fixture.detectChanges();
    expect(text()).toContain('Мої пацієнти');
    http.verify();
  });
});
