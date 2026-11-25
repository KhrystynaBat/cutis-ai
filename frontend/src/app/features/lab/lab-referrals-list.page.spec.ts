import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { AuthService } from '../../core/auth/auth.service';
import { LabReferralsListPage } from './lab-referrals-list.page';

describe('LabReferralsListPage', () => {
  it('lists incoming referrals with the doctor, marks new ones and links to processing', async () => {
    TestBed.configureTestingModule({
      imports: [LabReferralsListPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(LabReferralsListPage);
    const row = {
      createdAt: '2026-10-25T10:00:00Z',
      patient: { id: 'p1', firstName: 'Ганна', lastName: 'Шевченко', dateOfBirth: '1980-01-01' },
      doctor: { id: 'u1', firstName: 'Світлана', lastName: 'Будак' },
      assignee: null,
      caseId: 'c1',
      bodyLocation: 'спина',
    };
    http
      .expectOne((r) => r.url === '/api/v1/referrals')
      .flush({
        items: [
          {
            ...row,
            id: 'r1',
            referralNumber: 'REF-2026-000002',
            status: 'Sent',
            labAccessionNumber: null,
          },
          {
            ...row,
            id: 'r2',
            referralNumber: 'REF-2026-000001',
            status: 'Completed',
            labAccessionNumber: 'HP-26-0042',
          },
        ],
        total: 2,
        page: 1,
        pageSize: 20,
      });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('Будак С.');
    expect(el.textContent).toContain('нове');
    expect(el.textContent).toContain('HP-26-0042');
    const links = [...el.querySelectorAll('a')].map((a) => [
      a.getAttribute('href'),
      a.textContent?.trim(),
    ]);
    expect(links).toContainEqual(['/lab/referrals/r1', 'Опрацювати']);
    expect(links).toContainEqual(['/lab/referrals/r2', 'Переглянути']);
    expect(links.some(([href]) => href?.startsWith('/doctor/'))).toBe(false); // lab has no case pages
    http.verify();
  });

  it('greets the lab specialist in the vocative case', async () => {
    TestBed.configureTestingModule({
      imports: [LabReferralsListPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(AuthService).login('t@x.test', 'x').subscribe();
    http.expectOne('/api/v1/auth/login').flush({
      id: 'l1',
      firstName: 'Тарас',
      lastName: 'Ковальчук',
      middleName: 'Миколайович',
      email: 't@x.test',
      role: 'LabSpecialist',
      greetingName: 'Тарасе Миколайовичу',
    });
    const fixture = TestBed.createComponent(LabReferralsListPage);
    http
      .expectOne((r) => r.url === '/api/v1/referrals')
      .flush({ items: [], total: 0, page: 1, pageSize: 20 });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain(
      'Вітаємо, Тарасе Миколайовичу!',
    );
  });
});
