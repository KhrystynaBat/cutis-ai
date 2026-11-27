import { Component, computed, input } from '@angular/core';

import { CASE_STATUS_LABELS, CaseStatus } from '../core/api/doctor-api';

@Component({
  selector: 'app-case-status',
  template: `<span class="chip" [attr.data-status]="status()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 600;
      line-height: 16px;
      background: #e6f0fb;
      color: #1d5fa8;
      white-space: nowrap;
    }
    .chip[data-status='FollowUpPlanned'] {
      background: var(--dl-warn-bg);
      color: var(--dl-warn-text);
    }
    .chip[data-status='Referred'] {
      background: var(--dl-violet-bg);
      color: var(--dl-violet-text);
    }
    .chip[data-status='Closed'] {
      background: #f1f3f6;
      color: #3f4b5a;
    }
  `,
})
export class CaseStatusChip {
  readonly status = input.required<CaseStatus>();
  readonly label = computed(() => CASE_STATUS_LABELS[this.status()]);
}
