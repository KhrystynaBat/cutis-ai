import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import { Analysis, XAI_METHOD_LABELS, XaiArtifact, XaiMethod } from '../../core/api/analysis-api';
import {
  IMAGE_VIEWER_CONFIG,
  ImageViewerData,
  ImageViewerDialog,
} from '../dialogs/image-viewer-dialog';

@Component({
  selector: 'app-analysis-result',
  imports: [DatePipe, DecimalPipe, MatButtonToggleModule, MatIconModule],
  template: `
    @let a = analysis();
    @if (a.imageGateOverridden) {
      <p class="dl-banner gate-note" role="note">
        Фільтр не розпізнав зображення як дерматоскопічне; лікар підтвердив його вручну.
      </p>
    }
    <div class="layout">
      <section class="panel" aria-labelledby="cls-title">
        <div class="panel-head">
          <h3 id="cls-title" class="section">Результат класифікації</h3>
          <span class="date dl-muted"
            >Аналіз від {{ a.completedAt | date: 'dd.MM.yyyy HH:mm' }}</span
          >
        </div>
        <div class="summary">
          <div class="ring" [style.--pct]="(a.score ?? 0) * 100" aria-hidden="true">
            <span>{{ (a.score ?? 0) * 100 | number: '1.0-0' }}%</span>
          </div>
          <div>
            <p class="class">{{ a.predictedClass?.labelUk }}</p>
            <p class="dl-muted">
              Оцінка моделі: <strong>{{ a.score | number: '1.3-3' }}</strong>
            </p>
          </div>
        </div>

        <table class="scores">
          <caption class="visually-hidden">
            Оцінки моделі для всіх 7 класів
          </caption>
          <thead>
            <tr>
              <th scope="col">Клас</th>
              <th scope="col">Оцінка</th>
              <th scope="col"><span class="visually-hidden">Діаграма</span></th>
            </tr>
          </thead>
          <tbody>
            @for (s of a.scores; track s.code) {
              <tr [class.top]="s.code === a.predictedClass?.code">
                <td>{{ s.labelUk }}</td>
                <td class="num">{{ s.score | number: '1.3-3' }}</td>
                <td class="bar-cell" aria-hidden="true">
                  <span class="bar" [style.width.%]="s.score * 100"></span>
                </td>
              </tr>
            }
          </tbody>
        </table>
      </section>

      <section class="panel xai" aria-labelledby="xai-title">
        <h3 id="xai-title" class="section">Пояснення рішення моделі</h3>
        <div class="toggles">
          <mat-button-toggle-group
            [value]="method()"
            (change)="method.set($event.value)"
            aria-label="Метод пояснення"
            hideSingleSelectionIndicator
          >
            @for (m of methods; track m) {
              <mat-button-toggle [value]="m">{{ methodLabels[m] }}</mat-button-toggle>
            }
          </mat-button-toggle-group>
          <mat-button-toggle-group
            [value]="component()"
            (change)="component.set($event.value)"
            aria-label="Компонент ансамблю"
            hideSingleSelectionIndicator
          >
            @for (c of components(); track c) {
              <mat-button-toggle [value]="c">{{ c }}</mat-button-toggle>
            }
          </mat-button-toggle-group>
        </div>

        @if (selected(); as x) {
          <div class="pair">
            <figure>
              <div class="frame">
                <button
                  type="button"
                  class="zoom"
                  (click)="open(originalUrl(), originalAlt)"
                  aria-label="Відкрити оригінал на весь екран"
                >
                  <img [src]="originalUrl()" [alt]="originalAlt" />
                </button>
              </div>
              <figcaption>Оригінал</figcaption>
            </figure>
            <figure>
              <div class="frame">
                @if (x.status === 'Completed' && x.url) {
                  <button
                    type="button"
                    class="zoom"
                    (click)="open(x.url, mapAlt(x))"
                    aria-label="Відкрити теплову карту на весь екран"
                  >
                    <img [src]="x.url" [alt]="mapAlt(x)" />
                  </button>
                } @else {
                  <div class="unavailable" role="status">
                    <mat-icon aria-hidden="true">visibility_off</mat-icon>
                    <p>Пояснення недоступне</p>
                  </div>
                }
              </div>
              <figcaption>{{ methodLabels[x.method] }} · {{ x.component }}</figcaption>
            </figure>
          </div>
          <div class="legend" aria-label="Легенда інтенсивності">
            <span>низька</span>
            <span class="gradient" aria-hidden="true"></span>
            <span>висока</span>
          </div>
        } @else {
          <p class="dl-banner" role="status">Пояснення недоступне</p>
        }
      </section>
    </div>
  `,
  styleUrl: './analysis-result.scss',
})
export class AnalysisResult {
  private readonly dialog = inject(MatDialog);
  readonly analysis = input.required<Analysis>();
  readonly originalUrl = input.required<string>();

  readonly methods: XaiMethod[] = ['gradcam', 'gradcam_pp'];
  readonly methodLabels = XAI_METHOD_LABELS;
  readonly method = signal<XaiMethod>('gradcam');
  readonly component = signal<string>('AlexNet');

  readonly components = computed(() => [...new Set(this.analysis().xai.map((x) => x.component))]);
  readonly selected = computed<XaiArtifact | undefined>(() =>
    this.analysis().xai.find((x) => x.method === this.method() && x.component === this.component()),
  );

  readonly originalAlt = 'Оригінальне фото, яке аналізувалось';

  mapAlt(x: XaiArtifact): string {
    return `Теплова карта ${this.methodLabels[x.method]} компонента ${x.component} поверх фото`;
  }

  open(url: string, alt: string): void {
    this.dialog.open<ImageViewerDialog, ImageViewerData>(ImageViewerDialog, {
      ...IMAGE_VIEWER_CONFIG,
      data: { url, alt },
    });
  }
}
