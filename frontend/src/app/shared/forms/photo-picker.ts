import { Component, OnDestroy, computed, inject, input, output, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Subscription } from 'rxjs';

import { DoctorApi } from '../../core/api/doctor-api';
import { ACCEPT_ATTR, checkImageFile, loadPreview } from './image-file';

@Component({
  selector: 'app-photo-picker',
  imports: [MatButtonModule, MatCheckboxModule, MatIconModule, MatProgressSpinnerModule],
  template: `
    <div class="picker">
      <input
        #input
        class="visually-hidden"
        type="file"
        [id]="inputId()"
        [accept]="accept"
        (change)="onChange(input)"
      />
      <button mat-stroked-button type="button" (click)="input.click()">
        <mat-icon>add_photo_alternate</mat-icon>
        {{ previewUrl() ? 'Вибрати інше фото' : label() }}
      </button>
      @if (error(); as e) {
        <p class="dl-error-text" role="alert">{{ e }}</p>
      }
      @if (previewUrl(); as url) {
        <figure class="preview">
          <img [src]="url" alt="Попередній перегляд вибраного фото" />
          <figcaption class="dl-muted">{{ fileName() }}</figcaption>
        </figure>
      }
      @if (checking()) {
        <p class="checking dl-muted" role="status">
          <mat-progress-spinner diameter="16" mode="indeterminate" aria-hidden="true" />
          Перевіряю зображення…
        </p>
      }
      @if (warning()) {
        <div class="dl-banner gate-warning" role="alert">
          <p>
            <strong>Зображення не схоже на дерматоскопічне.</strong> Аналіз ШІ розрахований лише на
            дерматоскопічні знімки, тому для цього фото результат може бути недостовірним.
            Завантажте інше фото або підтвердіть, що це дерматоскопічне зображення.
          </p>
          <mat-checkbox [checked]="confirmed()" (change)="confirmed.set($event.checked)">
            Підтверджую, що це дерматоскопічне зображення
          </mat-checkbox>
        </div>
      }
    </div>
  `,
  styles: `
    .preview {
      margin: 12px 0 0;
    }
    .preview img {
      display: block;
      max-width: 100%;
      max-height: 280px;
      border-radius: 8px;
      border: 1px solid var(--dl-border);
    }
    .checking {
      display: flex;
      align-items: center;
      gap: 8px;
      margin: 8px 0 0;
    }
    .gate-warning {
      margin: 12px 0 0;
    }
    .gate-warning p {
      margin: 0 0 4px;
    }
  `,
})
export class PhotoPicker implements OnDestroy {
  private readonly api = inject(DoctorApi);

  readonly label = input('Вибрати фото');
  readonly inputId = input('photo-input');
  readonly checkDermoscopy = input(false);
  readonly fileChange = output<File | null>();

  readonly accept = ACCEPT_ATTR;
  readonly previewUrl = signal<string | null>(null);
  readonly fileName = signal('');
  readonly error = signal<string | null>(null);
  readonly checking = signal(false);
  readonly warning = signal(false);
  readonly confirmed = signal(false);

  readonly blocksSave = computed(() => this.checking() || (this.warning() && !this.confirmed()));
  readonly confirmNonDermoscopic = computed(() => this.warning() && this.confirmed());

  private check?: Subscription;

  async onChange(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    input.value = ''; // allow re-selecting the same file
    if (!file) return;
    this.clearPreview();
    this.clearGate();
    const problem = checkImageFile(file);
    if (problem) {
      this.reject(problem);
      return;
    }
    try {
      this.previewUrl.set(await loadPreview(file));
      this.fileName.set(file.name);
      this.error.set(null);
      this.fileChange.emit(file);
    } catch {
      this.reject('Не вдалося прочитати зображення: файл пошкоджений або це не фото');
      return;
    }
    if (this.checkDermoscopy()) this.runCheck(file);
  }

  showWarning(): void {
    this.warning.set(true);
    this.confirmed.set(false);
  }

  reset(): void {
    this.clearPreview();
    this.clearGate();
    this.error.set(null);
  }

  ngOnDestroy(): void {
    this.clearPreview();
    this.check?.unsubscribe();
  }

  private runCheck(file: File): void {
    this.checking.set(true);
    this.check = this.api.checkImage(file).subscribe({
      next: (r) => {
        this.checking.set(false);
        this.warning.set(!r.passed);
      },
      error: () => this.checking.set(false),
    });
  }

  private reject(message: string): void {
    this.error.set(message);
    this.fileChange.emit(null);
  }

  private clearGate(): void {
    this.check?.unsubscribe();
    this.checking.set(false);
    this.warning.set(false);
    this.confirmed.set(false);
  }

  private clearPreview(): void {
    const url = this.previewUrl();
    if (url) URL.revokeObjectURL(url);
    this.previewUrl.set(null);
    this.fileName.set('');
  }
}
