import { Component, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';

@Component({
  selector: 'app-error-page',
  imports: [RouterLink, MatButtonModule, MatIconModule],
  template: `
    <main class="page">
      <section class="dl-card box" [attr.aria-labelledby]="'err-' + code()">
        <mat-icon class="icon" aria-hidden="true">{{ icon() }}</mat-icon>
        <p class="code">{{ code() }}</p>
        <h1 [id]="'err-' + code()" class="dl-page-title">{{ title() }}</h1>
        <p class="dl-muted">{{ text() }}</p>
        <a mat-flat-button routerLink="/">Повернутися на головну</a>
      </section>
    </main>
  `,
  styles: `
    .page {
      min-height: calc(100vh / var(--dl-zoom));
      display: grid;
      place-items: center;
      padding: 16px;
      box-sizing: border-box;
    }
    .box {
      max-width: 440px;
      text-align: center;
    }
    .icon {
      font-size: 48px;
      width: 48px;
      height: 48px;
      color: var(--mat-sys-primary);
    }
    .code {
      margin: 8px 0 0;
      font: var(--mat-sys-display-small);
      color: var(--dl-text-muted);
    }
  `,
})
export class ErrorPage {
  readonly code = input.required<string>();
  readonly icon = input.required<string>();
  readonly title = input.required<string>();
  readonly text = input.required<string>();
}
