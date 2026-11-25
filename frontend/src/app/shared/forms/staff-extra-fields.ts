import { Component, input } from '@angular/core';
import {
  FormControl,
  FormGroup,
  NonNullableFormBuilder,
  ReactiveFormsModule,
} from '@angular/forms';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';

import { SEX_LABELS, Sex } from '../../core/auth/auth.models';
import { STAFF_MAX_AGE, STAFF_MIN_AGE, staffBirthDate, todayIso } from './validators';

export type StaffExtraGroup = FormGroup<{
  birthDate: FormControl<string>;
  sex: FormControl<Sex | ''>;
}>;

export interface StaffExtra {
  birthDate?: string | null;
  sex?: Sex | null;
}

export function staffExtraGroup(fb: NonNullableFormBuilder): StaffExtraGroup {
  return fb.group({
    birthDate: ['', [staffBirthDate]],
    sex: ['' as Sex | ''],
  });
}

export function staffExtraFormValue(u: StaffExtra) {
  return { birthDate: u.birthDate ?? '', sex: u.sex ?? ('' as const) };
}

export function staffExtraBody(g: StaffExtraGroup): Required<StaffExtra> {
  const { birthDate, sex } = g.getRawValue();
  return { birthDate: birthDate || null, sex: sex || null };
}

@Component({
  selector: 'app-staff-extra-fields',
  imports: [ReactiveFormsModule, MatFormFieldModule, MatInputModule, MatSelectModule],
  template: `
    <ng-container [formGroup]="group()">
      <mat-form-field appearance="outline">
        <mat-label>Дата народження</mat-label>
        <input matInput type="date" formControlName="birthDate" [max]="today" />
        @if (group().controls.birthDate.hasError('future')) {
          <mat-error>Дата народження не може бути в майбутньому</mat-error>
        } @else {
          <mat-error>Вік має бути від {{ minAge }} до {{ maxAge }} років</mat-error>
        }
      </mat-form-field>
      <mat-form-field appearance="outline">
        <mat-label>Стать</mat-label>
        <mat-select formControlName="sex">
          <mat-option value="">Не вказано</mat-option>
          @for (s of sexes; track s) {
            <mat-option [value]="s">{{ sexLabels[s] }}</mat-option>
          }
        </mat-select>
      </mat-form-field>
    </ng-container>
  `,
  styles: `
    :host {
      display: contents;
    }
  `,
})
export class StaffExtraFields {
  readonly group = input.required<StaffExtraGroup>();
  readonly today = todayIso();
  readonly minAge = STAFF_MIN_AGE;
  readonly maxAge = STAFF_MAX_AGE;
  readonly sexes: Sex[] = ['Female', 'Male'];
  readonly sexLabels = SEX_LABELS;
}
