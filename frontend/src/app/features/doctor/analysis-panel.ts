import { DatePipe } from '@angular/common';
import { Component, DestroyRef, computed, effect, inject, input, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatTooltipModule } from '@angular/material/tooltip';
import { Subscription, finalize, switchMap, takeWhile, timer } from 'rxjs';

import {
  ANALYSIS_STATUS_LABELS,
  AiStatus,
  Analysis,
  AnalysisApi,
  isActive,
} from '../../core/api/analysis-api';
import { parseApiError } from '../../core/api/api-error';
import { CaseDetail } from '../../core/api/doctor-api';
import { NotifyService } from '../../core/notify.service';
import { AnalysisResult } from '../../shared/ai/analysis-result';

export const POLL_MS = 1500;
const AI_STATUS_RETRY_MS = 5000;

@Component({
  selector: 'app-analysis-panel',
  imports: [
    DatePipe,
    MatButtonModule,
    MatIconModule,
    MatProgressSpinnerModule,
    MatTooltipModule,
    AnalysisResult,
  ],
  template: `
    <div class="bar">
      <p class="state" aria-live="polite">
        Стан: <strong>{{ statusLabel() }}</strong>
        @if (latest(); as l) {
          <span class="dl-muted"> · запуск {{ l.createdAt | date: 'dd.MM.yyyy HH:mm' }}</span>
        }
      </p>
      <!-- a disabled button gets no pointer events: the tooltip sits on a wrapper -->
      <span [matTooltip]="blockReason() ?? ''" [matTooltipDisabled]="!blockReason()">
        <button
          mat-flat-button
          type="button"
          (click)="start()"
          [disabled]="!canStart() || starting()"
          [attr.aria-label]="blockReason() ? startLabel() + '. ' + blockReason() : null"
        >
          <mat-icon>{{ latest()?.status === 'Failed' ? 'refresh' : 'biotech' }}</mat-icon>
          {{ startLabel() }}
        </button>
      </span>
    </div>

    @if (aiStatus(); as s) {
      @if (s.status !== 'ready') {
        <p class="dl-banner" role="status">
          @if (s.status === 'loading') {
            Модуль ШІ запускається. Спробуйте за хвилину.
          } @else {
            Аналіз ШІ зараз недоступний.
          }
        </p>
      }
    } @else if (aiStatusError()) {
      <p class="dl-banner" role="status">Не вдалося перевірити стан модуля ШІ.</p>
    }

    @if (isActive(latest())) {
      <div class="progress" role="status">
        <mat-progress-spinner diameter="28" mode="indeterminate" aria-hidden="true" />
        <span>
          @if (latest()?.status === 'Queued') {
            Аналіз у черзі…
          } @else {
            Аналіз виконується…
          }
        </span>
      </div>
    }

    @if (latest(); as l) {
      @if (l.status === 'Failed') {
        <div class="failed" role="alert">
          <p><strong>Не вдалося виконати аналіз. Спробуйте пізніше.</strong></p>
        </div>
      }
    }

    @if (current(); as cur) {
      @if (cur.id !== latest()?.id) {
        <p class="dl-muted">Нижче — останній успішний аналіз.</p>
      }
      @if (cur.imageId !== caseData().image?.id) {
        <p class="dl-banner" role="status">Цей аналіз виконано для попереднього фото випадку.</p>
      }
      <app-analysis-result
        [analysis]="cur"
        [originalUrl]="'/api/v1/cases/' + cur.caseId + '/images/' + cur.imageId"
      />
    } @else if (loaded() && !latest()) {
      <p class="dl-muted">Аналіз ще не запускався.</p>
    }

    @if (history().length > 1) {
      <details class="history">
        <summary>Історія запусків ({{ history().length }})</summary>
        <ul>
          @for (h of history(); track h.id) {
            <li>
              {{ h.createdAt | date: 'dd.MM.yyyy HH:mm' }} — {{ labels[h.status] }}
              @if (h.predictedClass) {
                · {{ h.predictedClass.labelUk }}
              }
            </li>
          }
        </ul>
      </details>
    }
  `,
  styles: `
    :host {
      display: grid;
      gap: 12px;
      grid-template-columns: minmax(0, 1fr);
    }
    .bar {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }
    .state {
      margin: 0;
    }
    .progress {
      display: flex;
      align-items: center;
      gap: 12px;
    }
    .failed {
      padding: 10px 14px;
      border-radius: 8px;
      background: #fdecea;
      color: var(--dl-error);
    }
    .failed p {
      margin: 0;
    }
    .history ul {
      margin: 8px 0 0;
      padding-left: 20px;
    }
  `,
})
export class AnalysisPanel {
  readonly caseData = input.required<CaseDetail>();

  private readonly api = inject(AnalysisApi);
  private readonly notify = inject(NotifyService);
  private readonly destroyRef = inject(DestroyRef);

  readonly labels = ANALYSIS_STATUS_LABELS;
  readonly isActive = isActive;
  readonly history = signal<Analysis[]>([]);
  readonly loaded = signal(false);
  readonly starting = signal(false);
  readonly aiStatus = signal<AiStatus | null>(null);
  readonly aiStatusError = signal(false);

  readonly latest = computed<Analysis | null>(() => this.history()[0] ?? null);
  readonly current = computed<Analysis | null>(
    () => this.history().find((a) => a.status === 'Completed') ?? null,
  );
  readonly statusLabel = computed(() => this.labels[this.latest()?.status ?? 'NotStarted']);

  readonly blockReason = computed<string | null>(() => {
    const c = this.caseData();
    if (!c.image) return 'Спершу додайте фото';
    if (c.status !== 'Open' && c.status !== 'FollowUpPlanned') {
      return 'Недоступно для випадку в цьому статусі';
    }
    if (isActive(this.latest())) return null;
    const s = this.aiStatus();
    if (s && s.status !== 'ready') return 'Модуль ШІ зараз недоступний';
    return null;
  });
  readonly canStart = computed(
    () =>
      this.loaded() &&
      this.aiStatus()?.status === 'ready' &&
      !this.blockReason() &&
      !isActive(this.latest()),
  );
  readonly startLabel = computed(() => {
    const l = this.latest();
    if (l?.status === 'Failed') return 'Спробувати ще раз';
    return this.current() ? 'Повторити аналіз' : 'Проаналізувати зображення';
  });

  private poll?: Subscription;
  private aiStatusRetry?: Subscription;

  constructor() {
    effect(() => {
      const id = this.caseData().id;
      this.loadHistory(id);
    });
    this.loadAiStatus();
    this.destroyRef.onDestroy(() => {
      this.poll?.unsubscribe();
      this.aiStatusRetry?.unsubscribe();
    });
  }

  private loadHistory(caseId: string): void {
    this.api.list(caseId).subscribe({
      next: (items) => {
        this.history.set(items);
        this.loaded.set(true);
        const l = items[0];
        if (isActive(l)) this.follow(l.id);
      },
      error: (e) => {
        this.loaded.set(true);
        this.notify.error(e, 'Не вдалося завантажити результати аналізу ШІ');
      },
    });
  }

  private loadAiStatus(): void {
    this.api
      .aiStatus()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (s) => {
          this.aiStatus.set(s);
          this.aiStatusError.set(false);
          if (s.status === 'loading') {
            this.aiStatusRetry = timer(AI_STATUS_RETRY_MS).subscribe(() => this.loadAiStatus());
          }
        },
        error: () => this.aiStatusError.set(true),
      });
  }

  start(): void {
    if (!this.canStart()) return;
    this.starting.set(true);
    this.api
      .start(this.caseData().id)
      .pipe(finalize(() => this.starting.set(false)))
      .subscribe({
        next: (a) => {
          this.upsert(a);
          this.follow(a.id);
        },
        error: (e) => {
          const err = parseApiError(e);
          if (err.code === 'AI_UNAVAILABLE' || err.code === 'AI_LOADING') this.loadAiStatus();
          if (err.code === 'ANALYSIS_IN_PROGRESS') this.loadHistory(this.caseData().id);
          this.notify.error(e, 'Не вдалося запустити аналіз. Спробуйте пізніше');
        },
      });
  }

  /** Poll one job until it is Completed or Failed. */
  private follow(id: string): void {
    this.poll?.unsubscribe();
    this.poll = timer(POLL_MS, POLL_MS)
      .pipe(
        switchMap(() => this.api.get(id)),
        takeWhile((a) => isActive(a), true),
      )
      .subscribe({
        next: (a) => {
          this.upsert(a);
          if (a.status === 'Completed') this.notify.success('Аналіз ШІ завершено');
        },
        error: (e) => this.notify.error(e, 'Не вдалося отримати стан аналізу'),
      });
  }

  private upsert(a: Analysis): void {
    const rest = this.history().filter((h) => h.id !== a.id);
    this.history.set(
      [a, ...rest].sort((x, y) =>
        x.createdAt < y.createdAt ? 1 : x.createdAt > y.createdAt ? -1 : 0,
      ),
    );
  }
}
