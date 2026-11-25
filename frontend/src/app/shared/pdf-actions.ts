import { Component, input } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';

@Component({
  selector: 'app-pdf-actions',
  imports: [MatButtonModule, MatIconModule],
  template: `
    <a mat-stroked-button [href]="url()" target="_blank" rel="noopener">
      <mat-icon>picture_as_pdf</mat-icon> Відкрити PDF
    </a>
  `,
  styles: `
    :host {
      display: contents;
    }
  `,
})
export class PdfActions {
  readonly url = input.required<string>();
}
