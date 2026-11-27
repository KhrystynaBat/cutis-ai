import { Component, input, output } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { Explanation } from '../../core/api/analysis-api';

@Component({
  selector: 'app-ai-explanation',
  imports: [MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    @let e = explanation();
    <section class="explanation" aria-labelledby="ai-explanation-title">
      <div class="head">
        <span class="head-ico"><mat-icon aria-hidden="true" fontIcon="auto_awesome" /></span>
        <h3 id="ai-explanation-title">Пояснення</h3>
      </div>
      @switch (e.status) {
        @case ('Pending') {
          <div class="progress" role="status">
            <mat-progress-spinner diameter="24" mode="indeterminate" aria-hidden="true" />
            <span>Готується пояснення…</span>
          </div>
        }
        @case ('Failed') {
          <div class="failed" role="alert">
            <p>{{ e.errorMessage || 'Не вдалося отримати пояснення' }}</p>
            <button mat-stroked-button type="button" (click)="retry.emit()" [disabled]="busy()">
              <mat-icon>refresh</mat-icon>
              Спробувати ще раз
            </button>
          </div>
        }
        @default {
          @if (e.classification; as c) {
            <div class="panel accent">
              <h4><mat-icon aria-hidden="true" fontIcon="insights" />Пояснення класифікації</h4>
              <p>{{ c.result }}</p>
              <p>{{ c.heatmaps }}</p>
            </div>
          }
          @if (e.discrepancy?.trim(); as warning) {
            <div class="panel warn" role="note">
              <h4><mat-icon aria-hidden="true" fontIcon="warning" />Зверніть увагу</h4>
              <p>{{ warning }}</p>
            </div>
          }
          @if (e.description; as d) {
            <div class="panel">
              <h4>
                <mat-icon aria-hidden="true" fontIcon="search" />Дерматоскопічний опис новоутворення
              </h4>
              <p>{{ d.intro }}</p>
              <ul class="features">
                @for (f of d.features; track $index) {
                  <li>
                    <strong>{{ f.label }}:</strong> {{ f.value }}
                  </li>
                }
              </ul>
            </div>
          }
          <div class="pair">
            @if (e.assessment; as s) {
              <div class="panel">
                <h4><mat-icon aria-hidden="true" fontIcon="fact_check" />Попередня оцінка</h4>
                <p>{{ s.intro }}</p>
                <ul class="options">
                  @for (x of s.differential; track $index) {
                    <li>{{ x }}</li>
                  }
                </ul>
              </div>
            }
            @if (e.recommendations) {
              <div class="panel">
                <h4><mat-icon aria-hidden="true" fontIcon="assignment" />Рекомендації</h4>
                <p>{{ e.recommendations }}</p>
              </div>
            }
          </div>
          @if (e.conclusion) {
            <p class="conclusion"><strong>Висновок:</strong> {{ e.conclusion }}</p>
          }
          <p class="note">
            <em>
              Оцінка сформована виключно на основі представленого зображення. Вона має допоміжний
              характер і не є остаточним клінічним діагнозом.
            </em>
          </p>
        }
      }
    </section>
  `,
  styles: `
    .explanation {
      display: grid;
      gap: 14px;
      grid-template-columns: minmax(0, 1fr);
      padding: 24px;
      border: 1px solid var(--dl-border);
      border-radius: 16px;
      background: var(--dl-surface);
    }
    .head {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .head-ico {
      display: grid;
      place-items: center;
      width: 40px;
      height: 40px;
      border-radius: 12px;
      background: var(--dl-violet-bg);
      color: #5a45c7;
    }
    h3 {
      margin: 0;
      font-size: 18px;
      font-weight: 600;
    }
    h4 {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 0 0 8px;
      font: var(--mat-sys-title-small);
      font-weight: 600;
    }
    h4 mat-icon {
      width: 20px;
      height: 20px;
      font-size: 20px;
      color: var(--mat-sys-primary);
    }
    p {
      margin: 0;
      line-height: 1.6;
    }
    p + p {
      margin-top: 6px;
    }
    .panel {
      padding: 16px 20px;
      border: 1px solid var(--dl-border-soft);
      border-radius: 14px;
      background: #f7f9fb;
      min-width: 0;
    }
    .panel.accent {
      border-color: #cfe6ec;
      background: #f2f9fb;
    }
    .panel.warn {
      border-color: #f6d9ad;
      background: var(--dl-warn-bg);
      color: var(--dl-warn-text);
    }
    .panel.warn h4 mat-icon {
      color: #b26a00;
    }
    ul {
      margin: 8px 0 0;
      padding: 0;
      list-style: none;
      line-height: 1.5;
    }
    .features {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 0 32px;
    }
    .features li {
      padding: 7px 0;
      border-bottom: 1px solid var(--dl-border);
    }
    .features strong {
      font-weight: 600;
    }
    .options li {
      position: relative;
      padding: 4px 0 4px 18px;
    }
    .options li::before {
      content: '';
      position: absolute;
      left: 2px;
      top: 0.85em;
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--mat-sys-primary);
    }
    .pair {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .pair:empty {
      display: none;
    }
    @media (max-width: 899.98px) {
      .pair {
        grid-template-columns: minmax(0, 1fr);
      }
    }
    .conclusion {
      padding: 16px 20px;
      border-radius: 14px;
      background: var(--dl-primary-soft);
      color: #0b3d4c;
    }
    .note {
      font: var(--mat-sys-body-small);
      color: var(--dl-text-muted);
    }
    .progress {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .failed {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 8px 16px;
      padding: 10px 14px;
      border-radius: 12px;
      background: #fdecea;
      color: var(--dl-error);
    }
  `,
})
export class AiExplanation {
  readonly explanation = input.required<Explanation>();
  readonly busy = input(false);
  readonly retry = output<void>();
}
