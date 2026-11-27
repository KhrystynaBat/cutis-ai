import { Injectable, Provider } from '@angular/core';
import { DateAdapter, MAT_DATE_FORMATS, MatDateFormats } from '@angular/material/core';

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
const TYPED = /^(\d{1,2})[./-](\d{1,2})[./-](\d{4})$/;
const pad = (n: number) => String(n).padStart(2, '0');

function iso(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function intl(options: Intl.DateTimeFormatOptions): Intl.DateTimeFormat {
  return new Intl.DateTimeFormat('uk', { ...options, timeZone: 'UTC' });
}

/** Datepicker over plain yyyy-mm-dd strings, the form values the API already uses. */
@Injectable()
export class IsoDateAdapter extends DateAdapter<string> {
  getYear(d: string): number {
    return +d.slice(0, 4);
  }

  getMonth(d: string): number {
    return +d.slice(5, 7) - 1;
  }

  getDate(d: string): number {
    return +d.slice(8, 10);
  }

  getDayOfWeek(d: string): number {
    return new Date(this.getYear(d), this.getMonth(d), this.getDate(d)).getDay();
  }

  getMonthNames(style: 'long' | 'short' | 'narrow'): string[] {
    const f = intl({ month: style });
    return Array.from({ length: 12 }, (_, m) => f.format(Date.UTC(2017, m, 1)));
  }

  getDateNames(): string[] {
    return Array.from({ length: 31 }, (_, i) => String(i + 1));
  }

  getDayOfWeekNames(style: 'long' | 'short' | 'narrow'): string[] {
    const f = intl({ weekday: style });
    // 1 January 2017 was a Sunday
    return Array.from({ length: 7 }, (_, i) => f.format(Date.UTC(2017, 0, i + 1)));
  }

  getYearName(d: string): string {
    return String(this.getYear(d));
  }

  getFirstDayOfWeek(): number {
    return 1;
  }

  getNumDaysInMonth(d: string): number {
    return new Date(this.getYear(d), this.getMonth(d) + 1, 0).getDate();
  }

  clone(d: string): string {
    return d;
  }

  createDate(year: number, month: number, date: number): string {
    const d = new Date(year, month, date);
    if (d.getMonth() !== month) throw Error(`Invalid date ${date} for month ${month}`);
    return iso(d);
  }

  today(): string {
    return iso(new Date());
  }

  parse(value: unknown): string | null {
    if (typeof value !== 'string' || !value.trim()) return null;
    const s = value.trim();
    if (ISO.test(s)) return this.isValid(s) ? s : this.invalid();
    const m = TYPED.exec(s);
    if (!m) return this.invalid();
    const d = new Date(+m[3], +m[2] - 1, +m[1]);
    return d.getDate() === +m[1] && d.getMonth() === +m[2] - 1 ? iso(d) : this.invalid();
  }

  format(d: string, display: unknown): string {
    if (!this.isValid(d)) return '';
    if (display === 'input') return `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}`;
    const utc = Date.UTC(this.getYear(d), this.getMonth(d), this.getDate(d));
    return intl(display as Intl.DateTimeFormatOptions).format(utc);
  }

  addCalendarYears(d: string, years: number): string {
    return this.addCalendarMonths(d, years * 12);
  }

  addCalendarMonths(d: string, months: number): string {
    const first = new Date(this.getYear(d), this.getMonth(d) + months, 1);
    const last = new Date(first.getFullYear(), first.getMonth() + 1, 0).getDate();
    first.setDate(Math.min(this.getDate(d), last));
    return iso(first);
  }

  addCalendarDays(d: string, days: number): string {
    return iso(new Date(this.getYear(d), this.getMonth(d), this.getDate(d) + days));
  }

  toIso8601(d: string): string {
    return d;
  }

  isDateInstance(obj: unknown): boolean {
    return typeof obj === 'string';
  }

  isValid(d: string): boolean {
    const m = ISO.exec(d);
    if (!m) return false;
    const x = new Date(+m[1], +m[2] - 1, +m[3]);
    return x.getFullYear() === +m[1] && x.getMonth() === +m[2] - 1 && x.getDate() === +m[3];
  }

  // empty value: required/other validators then show the usual message
  invalid(): string {
    return '';
  }

  override deserialize(value: unknown): string | null {
    return typeof value === 'string' && this.isValid(value) ? value : null;
  }
}

const FORMATS: MatDateFormats = {
  parse: { dateInput: 'input' },
  display: {
    dateInput: 'input',
    monthYearLabel: { month: 'long', year: 'numeric' },
    dateA11yLabel: { day: 'numeric', month: 'long', year: 'numeric' },
    monthYearA11yLabel: { month: 'long', year: 'numeric' },
  },
};

export function provideIsoDates(): Provider[] {
  return [
    { provide: DateAdapter, useClass: IsoDateAdapter },
    { provide: MAT_DATE_FORMATS, useValue: FORMATS },
  ];
}
