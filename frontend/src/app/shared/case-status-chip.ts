import { Component, computed, input } from '@angular/core';

import { CASE_STATUS_LABELS, CaseStatus } from '../core/api/doctor-api';

@Component({
  selector: 'app-case-status',
  template: `<span class="chip" [attr.data-status]="status()">{{ label() }}</span>`,
  styles: `
    .chip {
      display: inline-block;
      padding: 2px 10px;
      border-radius: 999px;
      font: var(--mat-sys-label-medium);
      background: #e3f2fd;
      color: #0b4f8a;
      white-space: nowrap;
    }
    .chip[data-status='FollowUpPlanned'] {
      background: var(--dl-warn-bg);
      color: var(--dl-warn-text);
    }
    .chip[data-status='Referred'] {
      background: #ede7f6;
      color: #4527a0;
    }
    .chip[data-status='Closed'] {
      background: #eceff1;
      color: var(--dl-text-muted);
    }
  `,
})
export class CaseStatusChip {
  readonly status = input.required<CaseStatus>();
  readonly label = computed(() => CASE_STATUS_LABELS[this.status()]);
}
