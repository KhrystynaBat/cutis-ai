import { Component, computed, input } from '@angular/core';

import { REFERRAL_STATUS_LABELS, ReferralStatus } from '../core/api/doctor-api';

@Component({
  selector: 'app-referral-status',
  template: `<span class="chip" [attr.data-status]="status()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font: var(--mat-sys-label-medium);
      background: #ede7f6;
      color: #4527a0;
      white-space: nowrap;
    }
    .chip[data-status='InProgress'] {
      background: var(--dl-warn-bg);
      color: var(--dl-warn-text);
    }
    .chip[data-status='Completed'] {
      background: #e6f4ea;
      color: var(--dl-ok);
    }
  `,
})
export class ReferralStatusChip {
  readonly status = input.required<ReferralStatus>();
  readonly label = computed(() => REFERRAL_STATUS_LABELS[this.status()]);
}
