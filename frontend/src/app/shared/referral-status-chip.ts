import { Component, computed, input } from '@angular/core';

import { REFERRAL_STATUS_LABELS, ReferralStatus } from '../core/api/doctor-api';

@Component({
  selector: 'app-referral-status',
  template: `<span class="chip" [attr.data-status]="status()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      line-height: 16px;
      background: var(--dl-violet-bg);
      color: var(--dl-violet-text);
      white-space: nowrap;
    }
    .chip[data-status='InProgress'] {
      background: var(--dl-warn-bg);
      color: var(--dl-warn-text);
    }
    .chip[data-status='Completed'] {
      background: var(--dl-ok-bg);
      color: #17673f;
    }
  `,
})
export class ReferralStatusChip {
  readonly status = input.required<ReferralStatus>();
  readonly label = computed(() => REFERRAL_STATUS_LABELS[this.status()]);
}
