import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { ReferralsListPage } from './referrals-list.page';

describe('ReferralsListPage', () => {
  it('lists the doctor’s referrals from the API with status and links', async () => {
    TestBed.configureTestingModule({
      imports: [ReferralsListPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const http = TestBed.inject(HttpTestingController);
    const fixture = TestBed.createComponent(ReferralsListPage);
    const req = http.expectOne((r) => r.url === '/api/v1/referrals');
    expect(req.request.params.get('page')).toBe('1');
    req.flush({
      items: [
        {
          id: 'r1',
          referralNumber: 'REF-2026-000007',
          status: 'Sent',
          createdAt: '2026-10-25T10:00:00Z',
          patient: { id: 'p1', firstName: 'Син', lastName: 'Тетичний', dateOfBirth: '1980-01-01' },
          caseId: 'c1234567-0000',
          bodyLocation: 'спина',
          labAccessionNumber: null,
        },
      ],
      total: 1,
      page: 1,
      pageSize: 20,
    });
    await fixture.whenStable();
    const el = fixture.nativeElement as HTMLElement;
    expect(el.textContent).toContain('REF-2026-000007');
    expect(el.textContent).toContain('Надіслано');
    expect(el.textContent).toContain('Тетичний С.');
    const hrefs = [...el.querySelectorAll('a')].map((a) => a.getAttribute('href'));
    expect(hrefs).toContain('/doctor/referrals/r1');
    expect(hrefs).toContain('/doctor/cases/c1234567-0000');
    http.verify();
  });
});
