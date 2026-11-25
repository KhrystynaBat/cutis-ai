import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';

import { CaseAction, CaseDetail, CaseStatus } from '../../core/api/doctor-api';
import { todayIso } from '../../shared/forms/validators';
import { AssessmentPanel } from './assessment-panel';

function caseData(
  status: CaseStatus,
  actions: CaseAction[],
  over: Partial<CaseDetail> = {},
): CaseDetail {
  return {
    id: 'c1',
    patient: { id: 'p1', firstName: 'Син', lastName: 'Тетичний', dateOfBirth: '1980-01-01' },
    examinedAt: '2026-10-25',
    bodyLocation: 'спина',
    status,
    hasImage: true,
    aiResult: { code: 'nv', labelUk: 'Меланоцитарний невус', score: 0.4 },
    referral: null,
    createdAt: '2026-10-25T10:00:00Z',
    clinicalDescription: 'опис',
    doctorAssessment: null,
    followUpDate: null,
    followUpNote: null,
    updatedAt: '2026-10-25T10:00:00Z',
    image: null,
    isEditable: status === 'Open',
    decision: null,
    availableActions: actions,
    ...over,
  };
}

describe('AssessmentPanel', () => {
  let fixture: ComponentFixture<AssessmentPanel>;
  let http: HttpTestingController;
  let confirmed: boolean;
  let dialogs: string[];
  let emitted: CaseDetail[];
  const el = () => fixture.nativeElement as HTMLElement;
  const text = () => el().textContent ?? '';
  const submit = () => {
    el().querySelector<HTMLButtonElement>('button[type=submit]')!.click();
    fixture.detectChanges();
  };

  function create(c: CaseDetail): void {
    confirmed = true;
    dialogs = [];
    emitted = [];
    TestBed.configureTestingModule({
      imports: [AssessmentPanel],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        {
          provide: MatDialog,
          useValue: {
            open: (_: unknown, cfg: { data: { title: string } }) => {
              dialogs.push(cfg.data.title);
              return { afterClosed: () => of(confirmed) };
            },
          },
        },
      ],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AssessmentPanel);
    fixture.componentRef.setInput('caseData', c);
    fixture.componentInstance.changed.subscribe((x) => emitted.push(x));
    fixture.detectChanges();
  }

  const form = () => fixture.componentInstance.form;
  const choose = (d: 'Close' | 'FollowUp' | 'Refer') => {
    form().controls.decision.setValue(d);
    fixture.detectChanges();
  };

  afterEach(() => http.verify());

  it('offers exactly the decisions the backend allows', () => {
    create(caseData('Open', ['Close', 'FollowUp', 'Refer']));
    const radios = [...el().querySelectorAll('mat-radio-button')].map((r) => r.textContent?.trim());
    expect(radios).toEqual([
      'Завершити випадок',
      'Запланувати контроль',
      'Направити на гістопатологію',
    ]);
  });

  it('closing requires an assessment and a confirmation', () => {
    create(caseData('Open', ['Close', 'FollowUp', 'Refer']));
    choose('Close');
    submit();
    expect(dialogs).toEqual([]); // invalid: no dialog, no request
    expect(text()).toContain('заповніть оцінку лікаря');

    form().controls.doctorAssessment.setValue('Себорейний кератоз');
    confirmed = false;
    submit();
    expect(dialogs).toEqual(['Завершити випадок?']);
    http.expectNone('/api/v1/cases/c1/assessment'); // cancelled

    confirmed = true;
    submit();
    const req = http.expectOne('/api/v1/cases/c1/assessment');
    expect(req.request.method).toBe('PATCH');
    expect(req.request.body).toEqual({ doctorAssessment: 'Себорейний кератоз', decision: 'Close' });
    req.flush(
      caseData('Closed', [], { doctorAssessment: 'Себорейний кератоз', decision: 'Close' }),
    );
    expect(emitted[0].status).toBe('Closed');
  });

  it('follow-up requires a date that is not in the past', () => {
    create(caseData('Open', ['Close', 'FollowUp', 'Refer']));
    choose('FollowUp');
    submit();
    expect(text()).toContain('Вкажіть дату контролю');
    form().controls.followUpDate.setValue('2000-01-01');
    submit();
    expect(text()).toContain('не може бути в минулому');
    http.expectNone('/api/v1/cases/c1/assessment');

    const day = todayIso();
    form().controls.followUpDate.setValue(day);
    form().controls.followUpNote.setValue('дерматоскопія');
    submit();
    expect(dialogs).toEqual([]); // follow-up is reversible: no confirmation
    expect(http.expectOne('/api/v1/cases/c1/assessment').request.body).toEqual({
      doctorAssessment: '',
      decision: 'FollowUp',
      followUpDate: day,
      followUpNote: 'дерматоскопія',
    });
  });

  it('referral requires a reason and is confirmed', () => {
    create(caseData('Open', ['Close', 'FollowUp', 'Refer']));
    choose('Refer');
    expect(text()).not.toContain("прив'язано");
    submit();
    expect(text()).toContain('Вкажіть підставу направлення');
    form().controls.referralReason.setValue('Виключити меланому');
    submit();
    expect(dialogs).toEqual(['Направити на гістопатологію?']);
    const req = http.expectOne('/api/v1/cases/c1/assessment');
    expect(req.request.body).toEqual({
      doctorAssessment: '',
      decision: 'Refer',
      referralReason: 'Виключити меланому',
    });
  });

  it('follow-up planned: no repeated follow-up, reopen is available', () => {
    create(
      caseData('FollowUpPlanned', ['Close', 'Refer', 'Reopen'], {
        followUpDate: '2026-11-25',
        followUpNote: 'повтор',
        decision: 'FollowUp',
      }),
    );
    expect(text()).toContain('Контроль заплановано на');
    expect(text()).not.toContain('Запланувати контроль');
    const reopen = [...el().querySelectorAll('button')].find((b) =>
      b.textContent?.includes('Повторний огляд'),
    )!;
    reopen.click();
    expect(dialogs).toEqual(['Повторний огляд']);
    const req = http.expectOne('/api/v1/cases/c1/reopen');
    expect(req.request.method).toBe('POST');
  });

  it('referred: no decisions until the lab result is approved', () => {
    create(
      caseData('Referred', [], {
        referral: {
          id: 'r1',
          referralNumber: 'REF-2026-000001',
          status: 'Sent',
          createdAt: '2026-10-25T10:00:00Z',
          reason: 'x',
          analysisId: null,
        },
      }),
    );
    expect(el().querySelectorAll('mat-radio-button').length).toBe(0);
    expect(text()).toContain('REF-2026-000001');
    expect(text()).not.toContain('Результат лабораторії затверджено'); // no how-to text
    expect(text()).not.toContain('Повторний огляд');
  });

  it('referred with an approved lab result: the doctor closes the case (Referred -> Closed)', () => {
    const referral = {
      id: 'r1',
      referralNumber: 'REF-2026-000001',
      status: 'Completed' as const,
      createdAt: '2026-10-25T10:00:00Z',
      reason: 'x',
      analysisId: null,
    };
    create(caseData('Referred', ['Close'], { referral, doctorAssessment: 'Підозра на BCC' }));
    const radios = [...el().querySelectorAll('mat-radio-button')].map((r) => r.textContent?.trim());
    expect(radios).toEqual(['Завершити випадок']);
    expect(text()).toContain('Результат лабораторії затверджено');

    choose('Close');
    form().controls.doctorAssessment.setValue('Гістологія: BCC. Направлено до онколога.');
    submit();
    expect(dialogs).toEqual(['Завершити випадок?']);
    const req = http.expectOne('/api/v1/cases/c1/assessment');
    expect(req.request.body).toEqual({
      doctorAssessment: 'Гістологія: BCC. Направлено до онколога.',
      decision: 'Close',
    });
    req.flush(caseData('Closed', [], { referral, decision: 'Close' }));
    expect(emitted[0].status).toBe('Closed');
  });

  it('closed: read-only', () => {
    create(caseData('Closed', [], { doctorAssessment: 'Висновок', decision: 'Close' }));
    expect(el().querySelector('form')).toBeNull();
    expect(text()).toContain('лише для перегляду');
    expect(text()).toContain('Рішення: Завершити випадок');
  });
});
