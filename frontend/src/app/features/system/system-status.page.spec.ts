import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';

import { SystemStatusPage } from './system-status.page';

describe('SystemStatusPage', () => {
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [SystemStatusPage],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('shows a coloured status of the server, the database and the AI module, no details', async () => {
    const fixture = TestBed.createComponent(SystemStatusPage);
    http.expectOne('/api/v1/health/live').flush({ status: 'ok' });
    http
      .expectOne('/api/v1/health/ready')
      .flush(
        { error: { code: 'DB_UNAVAILABLE', message: 'Database is not available' } },
        { status: 503, statusText: 'Service Unavailable' },
      );
    http.expectOne('/api/v1/system/ai-status').flush({
      status: 'unavailable',
      code: 'MODEL_FILE_MISSING',
      message: 'Файл моделі не знайдено на сервері',
      model: 'ensemble_best',
      modelVersion: null,
      preprocessingVersion: 'ham10000-bgr128-cubic-std-v1',
      components: ['AlexNet', 'ResNet', 'DenseNet'],
      xaiMethods: ['gradcam', 'gradcam_pp'],
      maxConcurrentAnalyses: 1,
      pendingAnalyses: 0,
    });
    await fixture.whenStable();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    const el = fixture.nativeElement as HTMLElement;
    const rows = [...el.querySelectorAll('li')].map((li) => li.textContent?.trim());
    expect(rows).toEqual([
      'Сервер (API)Працює',
      'База данихНедоступний',
      'Модуль ШІНедоступний',
      'Фільтр зображеньНедоступний',
    ]);
    expect(el.querySelector('.ok')).not.toBeNull();
    for (const hidden of ['DB_UNAVAILABLE', 'MODEL_FILE_MISSING', 'ensemble_best', 'Файл моделі']) {
      expect(text).not.toContain(hidden);
    }
  });

  it('shows a loading AI module as «Завантажується»', async () => {
    const fixture = TestBed.createComponent(SystemStatusPage);
    http.expectOne('/api/v1/health/live').flush({ status: 'ok' });
    http.expectOne('/api/v1/health/ready').flush({ status: 'ok', database: 'ok' });
    http.expectOne('/api/v1/system/ai-status').flush({ status: 'loading' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Модуль ШІЗавантажується');
  });

  it('shows the image filter separately from the AI module', async () => {
    const fixture = TestBed.createComponent(SystemStatusPage);
    http.expectOne('/api/v1/health/live').flush({ status: 'ok' });
    http.expectOne('/api/v1/health/ready').flush({ status: 'ok', database: 'ok' });
    http
      .expectOne('/api/v1/system/ai-status')
      .flush({ status: 'ready', gateStatus: 'unavailable' });
    await fixture.whenStable();
    const text = (fixture.nativeElement as HTMLElement).textContent ?? '';
    expect(text).toContain('Модуль ШІПрацює');
    expect(text).toContain('Фільтр зображеньНедоступний');
  });

  it('shows a working image filter', async () => {
    const fixture = TestBed.createComponent(SystemStatusPage);
    http.expectOne('/api/v1/health/live').flush({ status: 'ok' });
    http.expectOne('/api/v1/health/ready').flush({ status: 'ok', database: 'ok' });
    http.expectOne('/api/v1/system/ai-status').flush({ status: 'ready', gateStatus: 'ready' });
    await fixture.whenStable();
    expect((fixture.nativeElement as HTMLElement).textContent).toContain('Фільтр зображеньПрацює');
  });
});
