import { Component, inject } from '@angular/core';
import { FormControl, ReactiveFormsModule, Validators } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';

import { PersonRef } from '../../core/api/referral-api';
import { FullNamePipe } from '../../shared/names';

export interface ReassignData {
  referralNumber: string;
  colleagues: PersonRef[];
}

@Component({
  selector: 'app-reassign-dialog',
  imports: [
    FullNamePipe,
    MatDialogModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    ReactiveFormsModule,
  ],
  template: `
    <h2 mat-dialog-title>Передати колезі</h2>
    <mat-dialog-content>
      @if (data.colleagues.length) {
        <p>
          Направлення {{ data.referralNumber }} буде закріплено за обраним лаборантом; чернетка
          зберігається.
        </p>
        <mat-form-field appearance="outline" class="full">
          <mat-label>Лаборант</mat-label>
          <mat-select [formControl]="target">
            @for (c of data.colleagues; track c.id) {
              <mat-option [value]="c.id">{{ c | fullName }}</mat-option>
            }
          </mat-select>
          <mat-error>Оберіть лаборанта</mat-error>
        </mat-form-field>
      } @else {
        <p>Немає інших активних лаборантів, яким можна передати направлення.</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" [mat-dialog-close]="null">Скасувати</button>
      @if (data.colleagues.length) {
        <button mat-flat-button type="button" (click)="submit()">Передати</button>
      }
    </mat-dialog-actions>
  `,
  styles: `
    .full {
      width: 100%;
      min-width: 260px;
    }
  `,
})
export class ReassignDialog {
  readonly data = inject<ReassignData>(MAT_DIALOG_DATA);
  private readonly ref = inject(MatDialogRef<ReassignDialog, string | null>);
  readonly target = new FormControl<string | null>(null, Validators.required);

  submit(): void {
    if (this.target.invalid) {
      this.target.markAsTouched();
      return;
    }
    this.ref.close(this.target.value);
  }
}
