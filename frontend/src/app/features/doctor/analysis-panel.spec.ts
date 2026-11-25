import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AiStatus, Analysis } from '../../core/api/analysis-api';
import { CaseDetail } from '../../core/api/doctor-api';
import { AnalysisPanel, POLL_MS } from './analysis-panel';

const caseData: CaseDetail = {
  id: 'c1',
  patient: { id: 'p1', firstName: 'Син', lastName: 'Тетичний', dateOfBirth: '1980-01-01' },
  examinedAt: '2026-10-25',
  bodyLocation: 'спина',
  status: 'Open',
  hasImage: true,
  aiResult: null,
  referral: null,
  createdAt: '2026-10-25T10:00:00Z',
  clinicalDescription: 'опис',
  doctorAssessment: null,
  followUpDate: null,
  followUpNote: null,
  updatedAt: '2026-10-25T10:00:00Z',
  image: {
    id: 'img1',
    originalFilename: 'a.jpg',
    mimeType: 'image/jpeg',
    byteSize: 1000,
    uploadedAt: '2026-10-25T10:00:00Z',
    url: '/api/v1/cases/c1/images/img1',
  },
  isEditable: true,
  decision: null,
  availableActions: ['Close', 'FollowUp', 'Refer'],
};

const ready: AiStatus = {
  status: 'ready',
  code: null,
  message: 'AI-модуль працює',
  model: 'ensemble_best',
  modelVersion: '4890489c3ea6',
  preprocessingVersion: 'ham10000-bgr128-cubic-std-v1',
  components: ['AlexNet', 'ResNet', 'DenseNet'],
  xaiMethods: ['gradcam', 'gradcam_pp'],
  maxConcurrentAnalyses: 1,
  pendingAnalyses: 0,
};

function analysis(over: Partial<Analysis> = {}): Analysis {
  return {
    id: 'a1',
    caseId: 'c1',
    imageId: 'img1',
    status: 'Queued',
    model: 'ensemble_best',
    modelVersion: '4890489c3ea6',
    preprocessingVersion: 'ham10000-bgr128-cubic-std-v1',
    predictedClass: null,
    score: null,
    scores: [],
    errorCode: null,
    errorMessage: null,
    createdAt: '2026-10-25T10:01:00Z',
    startedAt: null,
    completedAt: null,
    xai: [],
    ...over,
  };
}

const completed = analysis({
  status: 'Completed',
  predictedClass: { code: 'nv', labelUk: 'Меланоцитарний невус' },
  score: 0.4,
  scores: [
    { code: 'nv', labelUk: 'Меланоцитарний невус', score: 0.4 },
    { code: 'mel', labelUk: 'Меланома', score: 0.3 },
  ],
  completedAt: '2026-10-25T10:01:05Z',
  xai: [
    {
      id: 'x1',
      method: 'gradcam',
      component: 'AlexNet',
      layerName: 'activation_5',
      gridSize: 8,
      status: 'Failed',
      errorCode: 'XAI_ZERO_GRADIENT',
      reason: 'Карта тотожно нульова',
      url: null,
    },
    {
      id: 'x2',
      method: 'gradcam_pp',
      component: 'AlexNet',
      layerName: 'activation_5',
      gridSize: 8,
      status: 'Completed',
      errorCode: null,
      reason: null,
      url: '/api/v1/analyses/a1/xai/x2',
    },
  ],
});

describe('AnalysisPanel', () => {
  let fixture: ComponentFixture<AnalysisPanel>;
  let http: HttpTestingController;
  const text = () => (fixture.nativeElement as HTMLElement).textContent ?? '';
  const button = () =>
    (fixture.nativeElement as HTMLElement).querySelector<HTMLButtonElement>('.bar button')!;

  function create(c: CaseDetail, history: Analysis[], status: AiStatus = ready): void {
    TestBed.configureTestingModule({
      imports: [AnalysisPanel],
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    http = TestBed.inject(HttpTestingController);
    fixture = TestBed.createComponent(AnalysisPanel);
    fixture.componentRef.setInput('caseData', c);
    fixture.detectChanges();
    http.expectOne('/api/v1/system/ai-status').flush(status);
    http.expectOne('/api/v1/cases/c1/analyses').flush(history);
    fixture.detectChanges();
  }

  afterEach(() => {
    http.verify();
    vi.useRealTimers();
  });

  it('starts a job, polls until Completed and shows the result with explanations', () => {
    vi.useFakeTimers();
    create(caseData, []);
    expect(text()).toContain('Не запускався');
    expect(button().disabled).toBe(false);
    expect(button().textContent).toContain('Проаналізувати зображення');

    button().click();
    const post = http.expectOne('/api/v1/cases/c1/analyses');
    expect(post.request.method).toBe('POST');
    post.flush(analysis());
    fixture.detectChanges();
    expect(text()).toContain('У черзі');
    expect(button().disabled).toBe(true);

    vi.advanceTimersByTime(POLL_MS);
    http.expectOne('/api/v1/analyses/a1').flush(analysis({ status: 'Running' }));
    fixture.detectChanges();
    expect(text()).toContain('Аналіз виконується');

    vi.advanceTimersByTime(POLL_MS);
    http.expectOne('/api/v1/analyses/a1').flush(completed);
    fixture.detectChanges();
    vi.advanceTimersByTime(POLL_MS * 3);
    http.expectNone('/api/v1/analyses/a1'); // polling stops after a final status

    const t = text();
    expect(t).toContain('Меланоцитарний невус');
    expect(t).toMatch(/0[.,]400/);
    // no technical or explanatory texts in the UI
    for (const hidden of [
      'ensemble_best',
      '4890489c3ea6',
      'ham10000',
      'не ймовірність',
      'Клас, обраний ансамблем',
      '67 із 223',
      'не діагноз',
      'Джерело пояснення',
      'Пояснення компонента',
      'activation_5',
      'Інтенсивність відносна',
    ]) {
      expect(t).not.toContain(hidden);
    }
    expect(t).toContain('Аналіз від');
    expect(t).toContain('Результат класифікації');
    expect(t).toContain('Пояснення рішення моделі');
    expect(t).toContain('низька');
    expect(t).toContain('висока');
    expect(t).toContain('Пояснення недоступне');
    expect(t).not.toContain('XAI_ZERO_GRADIENT');
    const imgs = [...(fixture.nativeElement as HTMLElement).querySelectorAll('img')];
    expect(imgs.map((i) => i.getAttribute('src'))).toEqual(['/api/v1/cases/c1/images/img1']);
    expect(button().textContent).toContain('Повторити аналіз');
  });

  it('notes a photo the doctor kept although the filter did not recognise it', () => {
    const note = 'Фільтр не розпізнав зображення як дерматоскопічне; лікар підтвердив його вручну.';
    create(caseData, [{ ...completed, imageGateOverridden: true }]);
    expect(text()).toContain(note);
    expect(text()).not.toMatch(/gate|фільтр зображень/i);
  });

  it('says nothing about the filter for an ordinary photo', () => {
    create(caseData, [completed]);
    expect(text()).not.toContain('Фільтр не розпізнав');
  });

  it('switches to the Grad-CAM++ map of the component', () => {
    create(caseData, [completed]);
    const toggles = [...(fixture.nativeElement as HTMLElement).querySelectorAll('button')];
    toggles.find((b) => b.textContent?.trim() === 'Grad-CAM++')!.click();
    fixture.detectChanges();
    const srcs = [...(fixture.nativeElement as HTMLElement).querySelectorAll('img')].map((i) =>
      i.getAttribute('src'),
    );
    expect(srcs).toContain('/api/v1/analyses/a1/xai/x2');
    expect(text()).toContain('Grad-CAM++ · AlexNet');
  });

  it('resumes polling for a job that is still running when the tab opens', () => {
    vi.useFakeTimers();
    create(caseData, [analysis({ status: 'Running' })]);
    vi.advanceTimersByTime(POLL_MS);
    http.expectOne('/api/v1/analyses/a1').flush(completed);
    fixture.detectChanges();
    expect(text()).toContain('Меланоцитарний невус');
  });

  it('shows a failed run with a retry button and keeps the last successful result', () => {
    const failed = analysis({
      id: 'a2',
      status: 'Failed',
      errorCode: 'AI_INTERNAL',
      errorMessage: 'Не вдалося виконати аналіз',
      createdAt: '2026-10-25T11:00:00Z',
    });
    create(caseData, [failed, completed]);
    expect(text()).toContain('Не вдалося виконати аналіз. Спробуйте пізніше.');
    expect(text()).not.toContain('AI_INTERNAL');
    expect(text()).toContain('останній успішний аналіз');
    expect(button().textContent).toContain('Спробувати ще раз');
    expect(button().disabled).toBe(false);
  });

  it('disables the analysis when AI is unavailable and says why', () => {
    create(caseData, [], {
      ...ready,
      status: 'unavailable',
      code: 'MODEL_FILE_MISSING',
      message: 'Файл моделі не знайдено на сервері',
      modelVersion: null,
    });
    expect(button().disabled).toBe(true);
    expect(text()).toContain('Аналіз ШІ зараз недоступний.');
    expect(text()).not.toContain('MODEL_FILE_MISSING');
  });

  it('requires a photo and an analysable case status', () => {
    create({ ...caseData, image: null, hasImage: false }, []);
    expect(button().disabled).toBe(true);
    expect(button().getAttribute('aria-label')).toContain('Спершу додайте фото');
    expect(text()).not.toContain('Спершу додайте фото');
  });

  it('warns when the result belongs to an earlier photo', () => {
    create({ ...caseData, image: { ...caseData.image!, id: 'img2' } }, [completed]);
    expect(text()).toContain('виконано для попереднього фото');
  });
});
