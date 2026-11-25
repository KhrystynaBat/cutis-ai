import { Clipboard } from '@angular/cdk/clipboard';
import { DatePipe } from '@angular/common';
import { Component, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

import { PasswordToken, passwordLink } from '../../core/api/admin-users-api';

export interface PasswordLinkData {
  userName: string;
  token: PasswordToken;
}

@Component({
  selector: 'app-password-link-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule, DatePipe],
  template: `
    <h2 mat-dialog-title>
      {{ data.token.purpose === 'Invitation' ? 'Запрошення' : 'Скидання пароля' }}
    </h2>
    <mat-dialog-content>
      <p>
        Посилання для встановлення пароля користувачем <strong>{{ data.userName }}</strong
        >:
      </p>
      <p class="link" data-testid="password-link">{{ link }}</p>
      @if (data.token.emailQueued) {
        <p class="sent" role="status">
          <mat-icon aria-hidden="true">mark_email_read</mat-icon>
          Посилання також надіслано на електронну пошту
        </p>
      }
      <p class="dl-muted">
        Діє до {{ data.token.expiresAt | date: 'dd.MM.yyyy HH:mm' }}, одноразове.
      </p>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-stroked-button type="button" (click)="copy()">
        <mat-icon>{{ copied() ? 'check' : 'content_copy' }}</mat-icon>
        {{ copied() ? 'Скопійовано' : 'Копіювати' }}
      </button>
      <button mat-flat-button type="button" mat-dialog-close cdkFocusInitial>Готово</button>
    </mat-dialog-actions>
  `,
  styles: `
    .sent {
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--dl-ok);
    }
    .link {
      padding: 10px 12px;
      border-radius: 8px;
      background: var(--dl-bg);
      border: 1px solid var(--dl-border);
      font-family: Consolas, 'Courier New', monospace;
      word-break: break-all;
      user-select: all;
    }
  `,
})
export class PasswordLinkDialog {
  readonly data = inject<PasswordLinkData>(MAT_DIALOG_DATA);
  private readonly clipboard = inject(Clipboard);
  readonly link = passwordLink(this.data.token.token);
  readonly copied = signal(false);

  copy(): void {
    this.copied.set(this.clipboard.copy(this.link));
  }
}
