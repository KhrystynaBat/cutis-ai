import { Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { AuthService, EmailChangeConfirmed } from '../../core/auth/auth.service';

export const EMAIL_LINK_INVALID =
  'Посилання недійсне або прострочене. Надішліть запит на зміну адреси ще раз.';

@Component({
  selector: 'app-email-confirm-page',
  imports: [RouterLink, MatButtonModule, MatProgressSpinnerModule],
  template: `
    <main class="page">
      <section class="dl-card dl-narrow" aria-labelledby="ec-title">
        <div class="brand">
          <img class="brand-logo" src="favicon.svg" alt="" width="32" height="32" />
          <span>CutisAI</span>
        </div>
        <h1 id="ec-title" class="dl-page-title">Підтвердження нової адреси</h1>
        @if (done(); as d) {
          <p class="dl-banner ok" role="status">
            Адресу змінено. Тепер для входу використовуйте {{ d.emailMasked }}.
          </p>
          <div class="dl-actions">
            @if (d.signedIn) {
              <a mat-flat-button routerLink="/profile">До профілю</a>
            } @else {
              <a mat-flat-button routerLink="/login">До сторінки входу</a>
            }
          </div>
        } @else if (!token() || error()) {
          <p class="dl-banner" role="alert">{{ error() ?? linkInvalid }}</p>
          <div class="dl-actions">
            <a mat-flat-button routerLink="/">На головну</a>
          </div>
        } @else {
          <p>Щоб зробити цю адресу адресою для входу в CutisAI, натисніть кнопку.</p>
          <div class="dl-actions">
            <button
              mat-flat-button
              type="button"
              class="submit"
              (click)="confirm()"
              [disabled]="submitting()"
            >
              @if (submitting()) {
                <mat-progress-spinner
                  diameter="20"
                  mode="indeterminate"
                  aria-label="Підтвердження…"
                />
              } @else {
                Підтвердити
              }
            </button>
          </div>
        }
      </section>
    </main>
  `,
  styleUrl: '../auth/login.page.scss',
})
export class EmailConfirmPage {
  private readonly auth = inject(AuthService);

  readonly token = input<string | undefined>();
  readonly submitting = signal(false);
  readonly error = signal<string | null>(null);
  readonly done = signal<EmailChangeConfirmed | null>(null);
  readonly linkInvalid = EMAIL_LINK_INVALID;

  confirm(): void {
    const token = this.token();
    if (!token || this.submitting()) return;
    this.submitting.set(true);
    this.auth
      .confirmEmailChange(token)
      .pipe(finalize(() => this.submitting.set(false)))
      .subscribe({
        next: (r) => {
          this.done.set(r);
          void this.auth.load();
        },
        error: (e) => {
          const err = parseApiError(e);
          const keep = ['EMAIL_TAKEN', 'ACCOUNT_DISABLED'];
          this.error.set(keep.includes(err.code) ? err.message : EMAIL_LINK_INVALID);
        },
      });
  }
}
