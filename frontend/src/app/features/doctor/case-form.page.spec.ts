import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';

import { checkImageFile } from '../../shared/forms/image-file';
import { CaseFormPage } from './case-form.page';

const patient = {
  id: 'p1',
  firstName: 'Син',
  lastName: 'Тетичний',
  dateOfBirth: '1980-01-01',
  age: 46,
  email: null,
  phone: null,
  notes: null,
  isArchived: false,
  casesCount: 0,
  lastVisit: null,
  createdAt: '',
  updatedAt: '',
};

describe('checkImageFile', () => {
  const file = (name: string, type: string, size: number) =>
    new File([new Uint8Array(size)], name, { type });

  it('accepts JPG/PNG/WebP within the size limit', () => {
    expect(checkImageFile(file('a.jpg', 'image/jpeg', 1000))).toBeNull();
    expect(checkImageFile(file('a.webp', 'image/webp', 1000))).toBeNull();
  });

  it('rejects other types, empty and too large files', () => {
    expect(checkImageFile(file('a.pdf', 'application/pdf', 1000))).toContain('JPG, PNG або WebP');
    expect(checkImageFile(file('a.png', 'image/png', 0))).toBe('Файл порожній');
    expect(checkImageFile(file('a.png', 'image/png', 10 * 1024 * 1024 + 1))).toContain('завеликий');
  });
});

describe('CaseFormPage (new case)', () => {
  let fixture: ComponentFixture<CaseFormPage>;
  let http: HttpTestingController;
  let navigate: ReturnType<typeof vi.spyOn>;
  const photo = new File([new Uint8Array(10)], 'photo.jpg', { type: 'image/jpeg' });

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [CaseFormPage],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    navigate = vi.spyOn(TestBed.inject(Router), 'navigate').mockResolvedValue(true);
    fixture = TestBed.createComponent(CaseFormPage);
    fixture.componentRef.setInput('patientId', 'p1');
    fixture.detectChanges();
    http
      .expectOne((r) => r.url === '/api/v1/patients')
      .flush({ items: [patient], total: 1, page: 1, pageSize: 100 });
  });

  afterEach(() => http.verify());

  function fill(): void {
    fixture.componentInstance.form.patchValue({
      bodyLocation: 'Спина',
      clinicalDescription: 'Пігментне утворення',
    });
  }

  it('preselects the patient from the query parameter', () => {
    expect(fixture.componentInstance.form.controls.patientId.value).toBe('p1');
  });

  it('requires a photo before creating anything', () => {
    fill();
    fixture.componentInstance.save();
    expect(fixture.componentInstance.photoMissing()).toBe(true);
    http.expectNone('/api/v1/cases');
  });

  it('creates the case, then uploads the photo, then opens the case', () => {
    fill();
    fixture.componentInstance.photo.set(photo);
    fixture.componentInstance.save();
    const create = http.expectOne('/api/v1/cases');
    expect(create.request.body).toMatchObject({ patientId: 'p1', bodyLocation: 'Спина' });
    create.flush({ id: 'c1' });
    const upload = http.expectOne('/api/v1/cases/c1/images');
    expect(upload.request.body instanceof FormData).toBe(true);
    upload.flush({ id: 'i1' });
    expect(navigate).toHaveBeenCalledWith(['/doctor/cases', 'c1']);
  });

  it('still opens the created case when only the photo upload fails', () => {
    fill();
    fixture.componentInstance.photo.set(photo);
    fixture.componentInstance.save();
    http.expectOne('/api/v1/cases').flush({ id: 'c1' });
    http
      .expectOne('/api/v1/cases/c1/images')
      .flush(
        { error: { code: 'UNSUPPORTED_FILE_TYPE', message: 'Підтримуються лише зображення' } },
        { status: 415, statusText: 'Unsupported Media Type' },
      );
    expect(navigate).toHaveBeenCalledWith(['/doctor/cases', 'c1']);
  });
});
