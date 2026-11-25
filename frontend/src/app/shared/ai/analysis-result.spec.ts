import { TestBed } from '@angular/core/testing';
import { MatDialog } from '@angular/material/dialog';
import { vi } from 'vitest';

import { Analysis } from '../../core/api/analysis-api';
import { ImageViewerDialog } from '../dialogs/image-viewer-dialog';
import { AnalysisResult } from './analysis-result';

const analysis: Analysis = {
  id: 'a1',
  caseId: 'c1',
  imageId: 'i1',
  status: 'Completed',
  model: 'ensemble',
  modelVersion: 'v1',
  preprocessingVersion: 'p1',
  predictedClass: { code: 'nv', labelUk: 'Меланоцитарний невус' },
  score: 0.9,
  scores: [{ code: 'nv', labelUk: 'Меланоцитарний невус', score: 0.9 }],
  errorCode: null,
  errorMessage: null,
  createdAt: '2026-11-15T10:00:00Z',
  startedAt: '2026-11-15T10:00:00Z',
  completedAt: '2026-11-15T10:00:05Z',
  xai: [
    {
      id: 'x1',
      method: 'gradcam',
      component: 'AlexNet',
      layerName: 'gradcam_target',
      gridSize: 7,
      status: 'Completed',
      errorCode: null,
      reason: null,
      url: '/api/v1/xai/x1/image',
    },
  ],
};

describe('AnalysisResult', () => {
  function setup() {
    TestBed.configureTestingModule({ imports: [AnalysisResult] });
    const dialog = TestBed.inject(MatDialog);
    const open = vi.spyOn(dialog, 'open').mockReturnValue({} as never);
    const fixture = TestBed.createComponent(AnalysisResult);
    fixture.componentRef.setInput('analysis', analysis);
    fixture.componentRef.setInput('originalUrl', '/api/v1/images/i1');
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    return { el, open };
  }

  it('shows the original and the map side by side, each as a zoom button', () => {
    const { el } = setup();
    const buttons = el.querySelectorAll<HTMLButtonElement>('.pair button.zoom');
    expect(buttons.length).toBe(2);
    expect(buttons[0].getAttribute('aria-label')).toBe('Відкрити оригінал на весь екран');
    expect(buttons[1].getAttribute('aria-label')).toBe('Відкрити теплову карту на весь екран');
  });

  it('a click opens the image full screen in the shared viewer', () => {
    const { el, open } = setup();
    const [original, map] = Array.from(el.querySelectorAll<HTMLButtonElement>('button.zoom'));
    original.click();
    expect(open).toHaveBeenLastCalledWith(
      ImageViewerDialog,
      expect.objectContaining({
        data: { url: '/api/v1/images/i1', alt: 'Оригінальне фото, яке аналізувалось' },
        width: '100vw',
      }),
    );
    map.click();
    expect(open).toHaveBeenLastCalledWith(
      ImageViewerDialog,
      expect.objectContaining({
        data: expect.objectContaining({ url: '/api/v1/xai/x1/image' }),
      }),
    );
  });
});
