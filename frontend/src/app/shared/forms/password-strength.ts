import { Component, computed, inject, input } from '@angular/core';

import {
  CommonPasswords,
  PasswordContext,
  passwordRequirements,
  passwordStrength,
} from './password';

@Component({
  selector: 'app-password-strength',
  template: `
    @if (password()) {
      <div class="meter" aria-hidden="true">
        @for (i of [1, 2, 3, 4]; track i) {
          <span [class.on]="strength() >= i" [attr.data-level]="strength()"></span>
        }
      </div>
    }
  `,
  styles: `
    :host {
      display: block;
      margin: 4px 0 12px;
      min-height: 3px;
    }
    .meter {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 3px;
    }
    .meter span {
      height: 3px;
      border-radius: 2px;
      background: var(--dl-border);
    }
    .meter span.on[data-level='1'] {
      background: var(--dl-error);
    }
    .meter span.on[data-level='2'] {
      background: #d18a00;
    }
    .meter span.on[data-level='3'],
    .meter span.on[data-level='4'] {
      background: var(--dl-ok);
    }
  `,
})
export class PasswordStrength {
  readonly password = input('');
  readonly context = input<PasswordContext | null>(null);

  private readonly common = inject(CommonPasswords);
  readonly strength = computed(() => {
    const pw = this.password();
    return passwordStrength(pw, passwordRequirements(pw, this.context(), this.common.list()));
  });

  constructor() {
    this.common.load();
  }
}
