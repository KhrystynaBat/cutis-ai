import { Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { HOME_BY_ROLE } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';

export const LINK_INVALID = 'Посилання недійсне або прострочене. Увійдіть ще раз.';
export const OTHER_BROWSER = 'Відкрийте посилання в тому браузері, де ви вводили пароль.';

@Component({
  selector: 'app-login-confirm-page',
  imports: [RouterLink, MatButtonModule, MatProgressSpinnerModule],
  template: `
    <main class="page">
      <section class="dl-card dl-narrow" aria-labelledby="lc-title">
        <div class="brand">
          <img class="brand-logo" src="favicon.svg" alt="" width="32" height="32" />
          <span>CutisAI</span>
        </div>
        <h1 id="lc-title" class="dl-page-title">Підтвердження входу</h1>
        @if (!token() || error()) {
          <p class="dl-banner" role="alert">{{ error() ?? linkInvalid }}</p>
          <div class="dl-actions">
            <a mat-flat-button routerLink="/login">До сторінки входу</a>
          </div>
        } @else {
          <p>Щоб завершити вхід до системи, натисніть кнопку.</p>
          <div class="dl-actions">
            <button
              mat-flat-button
              type="button"
              class="submit"
              (click)="confirm()"
              [disabled]="submitting()"
            >
              @if (submitting()) {
                <mat-progress-spinner diameter="20" mode="indeterminate" aria-label="Вхід…" />
              } @else {
                Підтвердити вхід
              }
            </button>
          </div>
        }
      </section>
    </main>
  `,
  styleUrl: './login.page.scss',
})
export class LoginConfirmPage {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly token = input<string | undefined>();
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly linkInvalid = LINK_INVALID;

  confirm(): void {
    const token = this.token();
    if (!token || this.submitting()) return;
    this.submitting.set(true);
    this.auth
      .confirmLogin(token)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: (user) => void this.router.navigateByUrl(HOME_BY_ROLE[user.role]),
        error: (e) => {
          const err = parseApiError(e);
          if (err.code === 'LOGIN_OTHER_BROWSER') this.error.set(OTHER_BROWSER);
          else if (err.code === 'ACCOUNT_DISABLED') this.error.set(err.message);
          else this.error.set(LINK_INVALID);
        },
      });
  }
}
