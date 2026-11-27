import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';

import { AiStatus, Analysis, Explanation } from '../../core/api/analysis-api';
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

  describe('AI explanation', () => {
    const ready: Explanation = {
      status: 'Completed',
      errorCode: null,
      errorMessage: null,
      model: 'gemini-test',
      classification: {
        result:
          'Система віднесла утворення до меланоцитарного невусу (40%), меланома близько (30%).',
        heatmaps: 'Найбільше уваги система приділила темнішій центральній ділянці.',
      },
      discrepancy: '',
      description: {
        intro: 'Візуалізується пігментоване новоутворення з такими характеристиками:',
        features: [
          { label: 'Форма', value: 'видовжена, асиметрична' },
          { label: 'Пігментна сітка', value: 'виражена, неоднорідна' },
        ],
      },
      assessment: {
        intro: 'Диференційну діагностику доцільно проводити між такими утвореннями:',
        differential: ['меланоцитарний невус (NV)', 'меланома (MEL)'],
      },
      recommendations: 'Рекомендовано клінічний огляд і дерматоскопію в динаміці.',
      conclusion: 'пігментоване новоутворення з ознаками неоднорідності.',
    };
    const pending: Explanation = {
      ...ready,
      status: 'Pending',
      classification: null,
      discrepancy: null,
      description: null,
      assessment: null,
      recommendations: null,
      conclusion: null,
    };
    const failed: Explanation = {
      ...pending,
      status: 'Failed',
      errorCode: 'EXPLAIN_RATE_LIMIT',
      errorMessage: 'Перевищено ліміт запитів до Gemini. Спробуйте пізніше',
    };
    const block = () => (fixture.nativeElement as HTMLElement).querySelector('app-ai-explanation');
    const retry = () =>
      [
        ...(fixture.nativeElement as HTMLElement).querySelectorAll<HTMLButtonElement>(
          'app-ai-explanation button',
        ),
      ].find((b) => b.textContent?.includes('Спробувати ще раз'));

    it('shows the sections under the heat maps with a closing note', () => {
      create(caseData, [{ ...completed, explanation: ready }]);
      const t = text();
      expect(block()!.querySelector('h3')!.textContent?.trim()).toBe('Пояснення');
      expect(t.indexOf('Пояснення рішення моделі')).toBeLessThan(
        t.indexOf('Пояснення класифікації'),
      );
      const heads = [...block()!.querySelectorAll('h4')].map((h) => h.textContent?.trim());
      expect(heads).toEqual([
        'Пояснення класифікації',
        'Дерматоскопічний опис новоутворення',
        'Попередня оцінка',
        'Рекомендації',
      ]);
      const items = [...block()!.querySelectorAll('li')].map((li) =>
        li.textContent?.replace(/\s+/g, ' ').trim(),
      );
      expect(items).toEqual([
        'Форма: видовжена, асиметрична',
        'Пігментна сітка: виражена, неоднорідна',
        'меланоцитарний невус (NV)',
        'меланома (MEL)',
      ]);
      expect(t).toContain('Система віднесла утворення до меланоцитарного невусу');
      expect(t).toContain('Найбільше уваги система приділила темнішій центральній ділянці.');
      expect(t).toContain('Рекомендовано клінічний огляд');
      expect(block()!.querySelector('.conclusion')!.textContent?.replace(/\s+/g, ' ').trim()).toBe(
        'Висновок: пігментоване новоутворення з ознаками неоднорідності.',
      );
      // the closing note is last and in italics
      const last = block()!.querySelector('section > p:last-of-type em');
      expect(last?.textContent?.replace(/\s+/g, ' ').trim()).toBe(
        'Оцінка сформована виключно на основі представленого зображення. ' +
          'Вона має допоміжний характер і не є остаточним клінічним діагнозом.',
      );
      expect(t).not.toMatch(/підказка|gemini/i);
    });

    it('warns right after the classification when the photo disagrees with the system', () => {
      const warning = 'Система віднесла утворення до невусу, але видно атипову сітку й регресію.';
      create(caseData, [{ ...completed, explanation: { ...ready, discrepancy: warning } }]);
      const heads = [...block()!.querySelectorAll('h4')].map((h) => h.textContent?.trim());
      expect(heads.slice(0, 3)).toEqual([
        'Пояснення класифікації',
        'Зверніть увагу',
        'Дерматоскопічний опис новоутворення',
      ]);
      expect(block()!.querySelector('.warn')!.textContent).toContain(warning);
    });

    it('shows no warning when the photo agrees with the system', () => {
      create(caseData, [{ ...completed, explanation: { ...ready, discrepancy: '  ' } }]);
      expect(block()!.querySelector('.warn')).toBeNull();
      expect(text()).not.toContain('Зверніть увагу');
    });

    it('shows the closing note only with a ready explanation', () => {
      create(caseData, [{ ...completed, explanation: pending }]);
      expect(block()!.textContent).not.toContain('допоміжний характер');
    });

    it('shows a waiting text and polls until the explanation is ready', () => {
      vi.useFakeTimers();
      create(caseData, [{ ...completed, explanation: pending }]);
      expect(block()!.textContent).toContain('Готується пояснення…');
      vi.advanceTimersByTime(POLL_MS);
      http.expectOne('/api/v1/analyses/a1').flush({ ...completed, explanation: ready });
      fixture.detectChanges();
      expect(text()).toContain('Попередня оцінка');
      vi.advanceTimersByTime(POLL_MS * 3);
      http.expectNone('/api/v1/analyses/a1');
    });

    it('a ready explanation is not requested again', () => {
      vi.useFakeTimers();
      create(caseData, [{ ...completed, explanation: ready }]);
      vi.advanceTimersByTime(POLL_MS * 3);
      http.expectNone('/api/v1/analyses/a1');
      http.expectNone('/api/v1/analyses/a1/explanation');
    });

    it('on error shows a short message and a retry button; the rest of the analysis stays', () => {
      vi.useFakeTimers();
      create(caseData, [{ ...completed, explanation: failed }]);
      expect(block()!.textContent).toContain('Перевищено ліміт запитів');
      expect(text()).not.toContain('EXPLAIN_RATE_LIMIT');
      expect(text()).toContain('Меланоцитарний невус');
      expect(text()).toContain('Пояснення рішення моделі');

      retry()!.click();
      const post = http.expectOne('/api/v1/analyses/a1/explanation');
      expect(post.request.method).toBe('POST');
      post.flush({ ...completed, explanation: pending });
      fixture.detectChanges();
      expect(block()!.textContent).toContain('Готується пояснення…');
      vi.advanceTimersByTime(POLL_MS);
      http.expectOne('/api/v1/analyses/a1').flush({ ...completed, explanation: ready });
      fixture.detectChanges();
      expect(text()).toContain('Рекомендації');
    });

    it('is absent when the analysis has no explanation', () => {
      create(caseData, [completed]);
      expect(block()).toBeNull();
      expect(
        (fixture.nativeElement as HTMLElement).querySelector('#ai-explanation-title'),
      ).toBeNull();
    });
  });
});
