import { AbstractControl, ValidationErrors } from '@angular/forms';

export function todayIso(now = new Date()): string {
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

export function notBlank(c: AbstractControl): ValidationErrors | null {
  return typeof c.value === 'string' && c.value.length > 0 && !c.value.trim()
    ? { required: true }
    : null;
}

export function notFutureDate(c: AbstractControl): ValidationErrors | null {
  return typeof c.value === 'string' && c.value && c.value > todayIso() ? { future: true } : null;
}

export const PHONE = /^\+?[0-9 ()-]{5,32}$/;

export const STAFF_MIN_AGE = 18;
export const STAFF_MAX_AGE = 100;

/** Full years between two yyyy-mm-dd dates. */
export function ageOn(born: string, day: string): number {
  const [by, bm, bd] = born.split('-').map(Number);
  const [y, m, d] = day.split('-').map(Number);
  return y - by - (m < bm || (m === bm && d < bd) ? 1 : 0);
}

export function staffBirthDate(c: AbstractControl): ValidationErrors | null {
  const v = c.value;
  if (typeof v !== 'string' || !v) return null;
  const today = todayIso();
  if (v > today) return { future: true };
  const age = ageOn(v, today);
  return age < STAFF_MIN_AGE || age > STAFF_MAX_AGE ? { age: true } : null;
}
