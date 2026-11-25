import { DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';

import { LabResult } from '../core/api/referral-api';
import { FullNamePipe } from './names';
import { PdfActions } from './pdf-actions';

@Component({
  selector: 'app-lab-result-view',
  imports: [DatePipe, FullNamePipe, PdfActions],
  template: `
    @let r = result();
    <dl class="dl-kv">
      <dt>№ дослідження</dt>
      <dd class="mono">{{ r.labAccessionNumber }}</dd>
      <dt>Дата дослідження</dt>
      <dd>{{ r.examinedAt | date: 'dd.MM.yyyy' }}</dd>
      <dt>Затверджено</dt>
      <dd>{{ r.approvedAt | date: 'dd.MM.yyyy HH:mm' }} · {{ r.labSpecialist | fullName }}</dd>
    </dl>
    <h4>Гістопатологічний висновок</h4>
    <p class="pre diagnosis">{{ r.histopathologyDiagnosis }}</p>
    <h4>Мікроскопічний опис</h4>
    <p class="pre">{{ r.histopathologyDescription }}</p>
    @if (r.comment) {
      <h4>Коментар</h4>
      <p class="pre">{{ r.comment }}</p>
    }
    @if (showPdf() && r.pdfUrl) {
      <div class="dl-actions">
        <app-pdf-actions [url]="r.pdfUrl" />
      </div>
    }
  `,
  styles: `
    :host {
      display: block;
    }
    h4 {
      margin: 12px 0 4px;
      font: var(--mat-sys-title-small);
    }
    .pre {
      margin: 0 0 8px;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }
    .diagnosis {
      font-weight: 600;
    }
  `,
})
export class LabResultView {
  readonly result = input.required<LabResult>();
  readonly showPdf = input(true);
}
