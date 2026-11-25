import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { PhotoPicker } from './photo-picker';

class LoadingImage {
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  set src(_: string) {
    queueMicrotask(() => this.onload?.());
  }
}

const WARNING = 'Зображення не схоже на дерматоскопічне.';

describe('PhotoPicker with the dermoscopy filter', () => {
  let fixture: ComponentFixture<PhotoPicker>;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [PhotoPicker],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(PhotoPicker);
    fixture.componentRef.setInput('checkDermoscopy', true);
    fixture.detectChanges();
    vi.stubGlobal('Image', LoadingImage);
    URL.createObjectURL = vi.fn(() => 'blob:preview');
    URL.revokeObjectURL = vi.fn();
  });

  afterEach(() => {
    http.verify();
    vi.unstubAllGlobals();
  });

  async function choose(name: string): Promise<void> {
    const file = new File([new Uint8Array(10)], name, { type: 'image/jpeg' });
    const input = { files: [file], value: 'x' } as unknown as HTMLInputElement;
    await fixture.componentInstance.onChange(input);
    fixture.detectChanges();
  }

  function text(): string {
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('checks the photo right after it is chosen and shows nothing when it passes', async () => {
    await choose('lesion.jpg');
    expect(text()).toContain('Перевіряю зображення…');
    expect(fixture.componentInstance.blocksSave()).toBe(true);
    const req = http.expectOne({ method: 'POST', url: '/api/v1/images/check' });
    expect(req.request.body instanceof FormData).toBe(true);
    req.flush({ passed: true, score: 0.98 });
    fixture.detectChanges();
    expect(text()).not.toContain('Перевіряю');
    expect(text()).not.toContain(WARNING);
    expect(fixture.componentInstance.blocksSave()).toBe(false);
    expect(fixture.componentInstance.confirmNonDermoscopic()).toBe(false);
  });

  it('warns about a non-dermoscopic photo; saving needs the checkbox', async () => {
    await choose('cat.jpg');
    http.expectOne('/api/v1/images/check').flush({ passed: false, score: 0.01 });
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    expect(text()).toContain(WARNING);
    expect(text()).toContain('Підтверджую, що це дерматоскопічне зображення');
    expect(el.querySelector('.dl-banner.gate-warning')).not.toBeNull();
    expect(el.querySelector('.dl-error-text')).toBeNull();
    expect(text()).not.toContain('0.01');
    expect(fixture.componentInstance.blocksSave()).toBe(true);

    (el.querySelector('input[type=checkbox]') as HTMLInputElement).click();
    fixture.detectChanges();
    expect(fixture.componentInstance.blocksSave()).toBe(false);
    expect(fixture.componentInstance.confirmNonDermoscopic()).toBe(true);
  });

  it('choosing another photo clears the warning and the confirmation', async () => {
    await choose('cat.jpg');
    http.expectOne('/api/v1/images/check').flush({ passed: false, score: 0.01 });
    fixture.componentInstance.confirmed.set(true);
    await choose('lesion.jpg');
    expect(fixture.componentInstance.warning()).toBe(false);
    expect(fixture.componentInstance.confirmed()).toBe(false);
    http.expectOne('/api/v1/images/check').flush({ passed: true, score: 0.99 });
    fixture.detectChanges();
    expect(text()).not.toContain(WARNING);
  });

  it('a failed check does not block (the upload decides); the upload can raise the warning', async () => {
    await choose('lesion.jpg');
    http
      .expectOne('/api/v1/images/check')
      .flush({ error: { code: 'AI', message: 'x' } }, { status: 500, statusText: 'Error' });
    expect(fixture.componentInstance.blocksSave()).toBe(false);
    fixture.componentInstance.showWarning();
    fixture.detectChanges();
    expect(text()).toContain(WARNING);
    expect(fixture.componentInstance.blocksSave()).toBe(true);
  });

  it('does not call the filter without checkDermoscopy', async () => {
    fixture.componentRef.setInput('checkDermoscopy', false);
    await choose('lesion.jpg');
    http.expectNone('/api/v1/images/check');
    expect(fixture.componentInstance.blocksSave()).toBe(false);
  });
});
