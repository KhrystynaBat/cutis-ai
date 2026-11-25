import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

import { parseApiError } from './api/api-error';

@Injectable({ providedIn: 'root' })
export class NotifyService {
  private readonly snack = inject(MatSnackBar);

  success(message: string): void {
    this.snack.open(message, 'OK', { duration: 4000, politeness: 'polite' });
  }

  info(message: string): void {
    this.snack.open(message, 'OK', { duration: 6000, politeness: 'polite' });
  }

  error(err: unknown, fallback = 'Сталася помилка'): void {
    const e = parseApiError(err);
    const id = e.correlationId ? ` (код: ${e.correlationId.slice(0, 8)})` : '';
    this.snack.open(`${e.message || fallback}${id}`, 'Закрити', {
      duration: 8000,
      politeness: 'assertive',
    });
  }
}
