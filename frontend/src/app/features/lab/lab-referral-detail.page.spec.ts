import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { signal } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { Analysis } from '../../core/api/analysis-api';
import { LabResult, PersonRef, Referral } from '../../core/api/referral-api';
import { AuthService } from '../../core/auth/auth.service';
import { todayIso } from '../../shared/forms/validators';
import { LabReferralDetailPage } from './lab-referral-detail.page';

const analysis: Analysis = {
  id: 'a1',
  caseId: 'c1',
  imageId: 'img1',
  status: 'Completed',
  model: 'ensemble_best',
  modelVersion: '4890489c3ea6',
  preprocessingVersion: 'ham10000-bgr128-cubic-std-v1',
  predictedClass: { code: 'bcc', labelUk: 'Базальноклітинна карцинома' },
  score: 0.66,
  scores: [{ code: 'bcc', labelUk: 'Базальноклітинна карцинома', score: 0.66 }],
  errorCode: null,
  errorMessage: null,
  createdAt: '2026-10-25T10:01:00Z',
  startedAt: null,
  completedAt: '2026-10-25T10:01:05Z',
  xai: [
    {
      id: 'x1',
      method: 'gradcam',
      component: 'AlexNet',
      layerName: 'activation_5',
      gridSize: 8,
      status: 'Completed',
      errorCode: null,
      reason: null,
      url: '/api/v1/referrals/r1/xai/x1',
    },
  ],
};

const draft: LabResult = {
  id: 'l1',
  labAccessionNumber: 'HP-26-0042',
  histopathologyDiagnosis: null,
  histopathologyDescription: null,
  examinedAt: null,
  comment: null,
  isApproved: false,
  approvedAt: null,
  labSpecialist: { id: 'u2', firstName: 'Тарас', lastName: 'Франко' },
  updatedAt: '2026-10-25T11:00:00Z',
  pdfUrl: null,
};

const me: PersonRef = { id: 'u2', firstName: 'Тарас', lastName: 'Франко' };
const colleague: PersonRef = { id: 'u3', firstName: 'Леся', lastName: 'Українка' };

function mine(over: Partial<Referral> = {}): Referral {
  return referral({
    status: 'InProgress',
    assignee: me,
    assignedAt: '2026-10-25T11:00:00Z',
    ...over,
  });
}

function referral(over: Partial<Referral> = {}): Referral {
  return {
    id: 'r1',
    referralNumber: 'REF-2026-000001',
    status: 'Sent',
    reason: 'Виключити BCC',
    createdAt: '2026-10-01T10:00:00Z',
    startedAt: null,
    completedAt: null,
    patient: { id: 'p1', firstName: 'Ганна', lastName: 'Шевченко', dateOfBirth: '1980-01-01' },
    doctor: { id: 'u1', firstName: 'Світлана', lastName: 'Будак' },
    assignee: null,
    assignedAt: null,
    case: {
      id: 'c1',
      status: 'Referred',
      examinedAt: '2026-10-01',
      bodyLocation: 'спина',
      clinicalDescription: 'Пігментне утворення 6 мм',
      doctorAssessment: 'Підозра на BCC',
      image: {
        id: 'img1',
        originalFilename: 'a.jpg',
        mimeType: 'image/jpeg',
        byteSize: 1000,
        uploadedAt: '2026-10-01T10:00:00Z',
        url: '/api/v1/referrals/r1/images/img1',
      },
    },
    analysis,
    analysisImageUrl: '/api/v1/referrals/r1/images/img1',
    labAccessionNumber: null,
    labResult: null,
    ...over,
  };
}

describe('LabReferralDetailPage', () => {
  let fixture: ComponentFixture<LabReferralDetailPage>;
  let http: HttpTestingController;
  let dialogs: string[];
  let confirmed: unknown;
  const el = () => fixture.nativeElement as HTMLElement;
  const text = () => el().textContent ?? '';
  const form = () => fixture.componentInstance.form;
  const button = (label: string) =>
    [...el().querySelectorAll<HTMLButtonElement>('button')].find((b) =>
      b.textContent?.includes(label),
    )!;
  const click = (label: string) => {
    button(label).click();
    fixture.detectChanges();
  };

  function open(r: Referral): void {
    dialogs = [];
    confirmed = true;
    TestBed.configureTestingModule({
      imports: [LabReferralDetailPage],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: AuthService,
          useValue: { user: signal({ ...me, email: 'l@x.test', role: 'LabSpecialist' }) },
        },
        {
          provide: MatDialog,
          useValue: {
            open: (_: unknown, cfg: { data: { title?: string; referralNumber?: string } }) => {
              dialogs.push(cfg.data.title ?? `reassign ${cfg.data.referralNumber}`);
              return { afterClosed: () => of(confirmed) };
            },
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(LabReferralDetailPage);
    fixture.componentRef.setInput('id', 'r1');
    fixture.detectChanges();
    http.expectOne('/api/v1/referrals/r1').flush(r);
    fixture.detectChanges();
  }

  it('shows photo and the doctor’s description, and no AI block', () => {
    open(referral({ analysis: null, analysisImageUrl: null }));
    expect(text()).toContain('Будак Світлана');
    expect(text()).toContain('Пігментне утворення 6 мм');
    expect(text()).toContain('Виключити BCC');
    const srcs = [...el().querySelectorAll('img')].map((i) => i.getAttribute('src'));
    expect(srcs).toEqual(['/api/v1/referrals/r1/images/img1']);
    expect(text()).not.toContain('Аналіз ШІ');
    expect(text()).toContain('Направлення ще не взято в роботу');
  });

  it('shows no AI result to the lab, even if the data carries one', () => {
    open(referral());
    expect(text()).not.toContain('Аналіз ШІ');
    expect(text()).not.toContain('Базальноклітинна карцинома');
    expect(el().querySelector('app-analysis-result')).toBeNull();
    expect(el().querySelector('#ai-explanation-title')).toBeNull();
  });

  it('starts processing: Sent -> InProgress', () => {
    open(referral());
    click('Почати опрацювання');
    const req = http.expectOne('/api/v1/referrals/r1/start');
    expect(req.request.method).toBe('POST');
    req.flush(mine({ startedAt: '2026-10-25T11:00:00Z' }));
    fixture.detectChanges();
    expect(text()).not.toContain('Почати опрацювання');
    expect(text()).toContain('Направлення закріплене за вами');
    expect(el().querySelector('form')).not.toBeNull();
  });

  it('saves a partial draft without requiring the approval fields', () => {
    open(mine());
    form().controls.labAccessionNumber.setValue(' hp-26-0042 ');
    click('Зберегти чернетку');
    const req = http.expectOne('/api/v1/referrals/r1/lab-result/draft');
    expect(req.request.method).toBe('PUT');
    expect(req.request.body).toEqual({
      labAccessionNumber: 'hp-26-0042',
      histopathologyDiagnosis: null,
      histopathologyDescription: null,
      examinedAt: null,
      comment: null,
    });
    req.flush(mine({ labResult: draft }));
    fixture.detectChanges();
    expect(text()).toContain('Чернетку збережено');
    expect(form().controls.labAccessionNumber.value).toBe('HP-26-0042');
  });

  it('approval checks the fields, asks for confirmation, then shows the read-only result', () => {
    open(mine({ labResult: draft }));
    click('Затвердити результат');
    expect(dialogs).toEqual([]); // incomplete: no dialog, no request
    expect(text()).toContain('Вкажіть гістопатологічний висновок');

    form().patchValue({
      histopathologyDiagnosis: 'Базальноклітинна карцинома',
      histopathologyDescription: 'Гнізда базалоїдних клітин',
      examinedAt: todayIso(),
    });
    confirmed = false;
    click('Затвердити результат');
    expect(dialogs).toEqual(['Затвердити результат?']);
    http.expectNone('/api/v1/referrals/r1/lab-result/approve'); // cancelled

    confirmed = true;
    click('Затвердити результат');
    const req = http.expectOne('/api/v1/referrals/r1/lab-result/approve');
    expect(req.request.body.histopathologyDiagnosis).toBe('Базальноклітинна карцинома');
    req.flush(
      referral({
        status: 'Completed',
        completedAt: '2026-10-25T12:00:00Z',
        labResult: {
          ...draft,
          histopathologyDiagnosis: 'Базальноклітинна карцинома',
          histopathologyDescription: 'Гнізда базалоїдних клітин',
          examinedAt: todayIso(),
          isApproved: true,
          approvedAt: '2026-10-25T12:00:00Z',
          pdfUrl: '/api/v1/referrals/r1/lab-result.pdf',
        },
      }),
    );
    fixture.detectChanges();
    expect(text()).toContain('Результат затверджено');
    expect(el().querySelector('form')).toBeNull(); // read-only
    const open_ = [...el().querySelectorAll<HTMLAnchorElement>('a')].find((a) =>
      a.textContent?.includes('Відкрити PDF'),
    );
    expect(open_?.getAttribute('href')).toBe('/api/v1/referrals/r1/lab-result.pdf');
    expect(open_?.getAttribute('target')).toBe('_blank');
    expect(el().querySelector('a[download]')).toBeNull();
    expect(text()).not.toContain('Завантажити PDF');
  });

  it('rejects an examination date before the referral', () => {
    open(mine());
    form().controls.examinedAt.setValue('2026-09-01');
    expect(form().controls.examinedAt.hasError('range')).toBe(true);
    form().controls.examinedAt.setValue('2026-10-01');
    expect(form().controls.examinedAt.valid).toBe(true);
  });

  it('cancel drops unsaved edits', () => {
    open(mine({ labResult: draft }));
    form().controls.labAccessionNumber.setValue('X-1');
    form().markAsDirty();
    click('Скасувати');
    expect(form().controls.labAccessionNumber.value).toBe('HP-26-0042');
  });

  it('a referral taken by a colleague is read-only ("В роботі: …"), without the form', () => {
    open(mine({ assignee: colleague, labResult: draft }));
    expect(text()).toContain('В роботі: Українка Леся');
    expect(el().querySelector('form')).toBeNull();
    expect(text()).not.toContain('Передати колезі');
    expect(text()).not.toContain('Почати опрацювання');
  });

  it('hands the referral over to a colleague', () => {
    open(mine({ labResult: draft }));
    confirmed = 'u3';
    click('Передати колезі');
    http.expectOne('/api/v1/lab/specialists').flush([me, colleague]);
    expect(dialogs).toEqual(['reassign REF-2026-000001']);
    const req = http.expectOne('/api/v1/referrals/r1/reassign');
    expect(req.request.body).toEqual({ labSpecialistId: 'u3' });
    req.flush(mine({ assignee: colleague, labResult: draft }));
    fixture.detectChanges();
    expect(text()).toContain('В роботі: Українка Леся');
  });

  it('declining returns the referral to the queue after a confirmation', () => {
    open(mine({ labResult: draft }));
    click('Відмовитися');
    expect(dialogs).toEqual(['Відмовитися від направлення?']);
    http.expectOne('/api/v1/referrals/r1/release').flush(referral({ labResult: draft }));
    fixture.detectChanges();
    expect(text()).toContain('Почати опрацювання');
    expect(el().querySelector('form')).toBeNull();
  });
});
