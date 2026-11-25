import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

import { AnalysisApi } from '../../core/api/analysis-api';
import { SystemApi } from '../../core/api/system-api';

export type ComponentState = 'ok' | 'loading' | 'down';

export const STATE_LABELS: Record<ComponentState, string> = {
  ok: 'Працює',
  loading: 'Завантажується',
  down: 'Недоступний',
};

function toState(status: 'ready' | 'loading' | 'unavailable'): ComponentState {
  return status === 'ready' ? 'ok' : status === 'loading' ? 'loading' : 'down';
}

interface Row {
  label: string;
  /** null while the check is in flight */
  state: ReturnType<typeof signal<ComponentState | null>>;
}

@Component({
  selector: 'app-system-status-page',
  imports: [MatButtonModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <section class="dl-card dl-narrow" aria-labelledby="status-title">
      <div class="dl-list-header">
        <h2 id="status-title" class="dl-page-title">Стан системи</h2>
        <button mat-icon-button type="button" (click)="refresh()" aria-label="Оновити">
          <mat-icon>refresh</mat-icon>
        </button>
      </div>
      <ul class="rows" aria-live="polite">
        @for (r of rows; track r.label) {
          <li>
            <span class="label">{{ r.label }}</span>
            @if (r.state(); as s) {
              <span class="value" [class]="s">
                <span class="dot" aria-hidden="true"></span>{{ labels[s] }}
              </span>
            } @else {
              <mat-progress-spinner diameter="18" mode="indeterminate" aria-label="Перевірка" />
            }
          </li>
        }
      </ul>
    </section>
  `,
  styles: `
    .rows {
      list-style: none;
      padding: 0;
      margin: 8px 0 0;
    }
    li {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 12px 0;
      border-top: 1px solid var(--dl-border);
    }
    .label {
      font-weight: 500;
    }
    .value {
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .dot {
      width: 10px;
      height: 10px;
      border-radius: 50%;
      background: currentColor;
    }
    .ok {
      color: var(--dl-ok);
    }
    .loading {
      color: #a15c00;
    }
    .down {
      color: var(--dl-error);
    }
  `,
})
export class SystemStatusPage {
  private readonly api = inject(SystemApi);
  private readonly analysisApi = inject(AnalysisApi);

  readonly labels = STATE_LABELS;
  readonly rows: Row[] = [
    { label: 'Сервер (API)', state: signal<ComponentState | null>(null) },
    { label: 'База даних', state: signal<ComponentState | null>(null) },
    { label: 'Модуль ШІ', state: signal<ComponentState | null>(null) },
    { label: 'Фільтр зображень', state: signal<ComponentState | null>(null) },
  ];

  constructor() {
    this.refresh();
  }

  refresh(): void {
    const [server, db, ai, gate] = this.rows;
    for (const r of this.rows) r.state.set(null);
    this.api.live().subscribe({
      next: () => server.state.set('ok'),
      error: () => server.state.set('down'),
    });
    this.api.ready().subscribe({
      next: () => db.state.set('ok'),
      error: () => db.state.set('down'),
    });
    this.analysisApi.aiStatus().subscribe({
      next: (s) => {
        ai.state.set(toState(s.status));
        gate.state.set(toState(s.gateStatus ?? 'unavailable'));
      },
      error: () => {
        ai.state.set('down');
        gate.state.set('down');
      },
    });
  }
}
