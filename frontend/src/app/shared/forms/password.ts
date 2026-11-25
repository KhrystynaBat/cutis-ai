import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { AbstractControl, ValidationErrors, ValidatorFn } from '@angular/forms';

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;
const RUN = 4;
const SEQUENCES = [
  '1234567890',
  'qwertyuiop',
  'asdfghjkl',
  'zxcvbnm',
  'йцукенгшщзхї',
  'фівапролджє',
  'ячсмитьбю',
  'abcdefghijklmnopqrstuvwxyz',
  'абвгґдеєжзиіїйклмнопрстуфхцчшщьюя',
];

export type RequirementKey =
  'length' | 'lower' | 'upper' | 'digit' | 'special' | 'personal' | 'common' | 'sequence';

export interface Requirement {
  key: RequirementKey;
  label: string;
  ok: boolean | null;
}

export interface PasswordContext {
  email?: string | null;
  names?: (string | null | undefined)[];
}

const LABELS: Record<RequirementKey, string> = {
  length: `Щонайменше ${PASSWORD_MIN_LENGTH} символів`,
  lower: 'Мала літера',
  upper: 'Велика літера',
  digit: 'Цифра',
  special: 'Спецсимвол (наприклад ! ? # - _ *)',
  personal: 'Без електронної пошти, імені чи прізвища',
  common: 'Не з переліку поширених паролів',
  sequence: 'Без повторів і послідовностей (aaaa, 1234, qwerty)',
};

const ADD: Partial<Record<RequirementKey, string>> = {
  lower: 'малу літеру',
  upper: 'велику літеру',
  digit: 'цифру',
  special: 'спецсимвол',
};

const OTHER: Partial<Record<RequirementKey, string>> = {
  personal: "Пароль не може містити електронну пошту, ім'я чи прізвище",
  common: 'Це поширений пароль — оберіть інший',
  sequence: 'Уникайте повторів і послідовностей (aaaa, 1234, qwerty)',
};

function joinUk(items: string[]): string {
  return items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} й ${items.at(-1)}`;
}

export function passwordMessage(pw: string, failed: readonly RequirementKey[]): string | null {
  if (!failed.length) return null;
  const add = failed.filter((k) => ADD[k]).map((k) => ADD[k] as string);
  const parts: string[] = [];
  if (failed.includes('length')) {
    parts.push(
      pw.length > PASSWORD_MAX_LENGTH
        ? `Не більше ${PASSWORD_MAX_LENGTH} символів`
        : `Щонайменше ${PASSWORD_MIN_LENGTH} символів`,
    );
  }
  if (add.length) parts.push(`${parts.length ? 'додайте' : 'Додайте'} ${joinUk(add)}`);
  if (parts.length) return parts.join('; ');
  const other = failed.find((k) => OTHER[k]);
  return other ? (OTHER[other] as string) : null;
}

export function passwordHint(
  pw: string,
  ctx: PasswordContext | null,
  common: ReadonlySet<string> | null,
): string | null {
  if (!pw) return null;
  const failed = passwordRequirements(pw, ctx, common)
    .filter((r) => r.ok === false)
    .map((r) => r.key);
  return passwordMessage(pw, failed);
}

function hasSequence(pw: string): boolean {
  const low = pw.toLowerCase();
  if (new RegExp(`(.)\\1{${RUN - 1},}`, 'u').test(low)) return true;
  for (const seq of SEQUENCES) {
    for (const line of [seq, [...seq].reverse().join('')]) {
      for (let i = 0; i + RUN <= line.length; i++) {
        if (low.includes(line.slice(i, i + RUN))) return true;
      }
    }
  }
  return false;
}

function personalParts(ctx: PasswordContext): string[] {
  const parts: string[] = [];
  if (ctx.email) {
    const local = ctx.email.split('@')[0].toLowerCase();
    parts.push(local, ...local.split(/[._\-+]/).filter(Boolean));
  }
  for (const n of ctx.names ?? []) if (n && n.trim()) parts.push(n.trim().toLowerCase());
  return parts.filter((p) => p.length >= 3);
}

export function passwordRequirements(
  pw: string,
  ctx: PasswordContext | null,
  common: ReadonlySet<string> | null,
): Requirement[] {
  const low = pw.toLowerCase();
  const core = low.replace(/^[^\p{L}]+|[^\p{L}]+$/gu, ''); // digits and symbols off the ends
  const checks: Record<RequirementKey, boolean | null> = {
    length: pw.length >= PASSWORD_MIN_LENGTH && pw.length <= PASSWORD_MAX_LENGTH,
    lower: /\p{Ll}/u.test(pw),
    upper: /\p{Lu}/u.test(pw),
    digit: /\p{Nd}/u.test(pw),
    special: /[^\p{L}\p{N}\s]/u.test(pw),
    personal: ctx ? !personalParts(ctx).some((p) => low.includes(p)) : null,
    common: common ? !(common.has(low) || (core.length >= 4 && common.has(core))) : null,
    sequence: pw.length > 0 && !hasSequence(pw),
  };
  return (Object.keys(LABELS) as RequirementKey[]).map((key) => ({
    key,
    label: LABELS[key],
    ok: checks[key],
  }));
}

export function passwordStrength(pw: string, reqs: Requirement[]): number {
  if (!pw) return 0;
  const failed = reqs.filter((r) => r.ok === false).length;
  if (failed > 2) return 1;
  if (failed > 0) return 2;
  return pw.length >= 16 ? 4 : 3;
}

export const STRENGTH_LABELS = ['', 'Слабкий', 'Недостатній', 'Надійний', 'Дуже надійний'];

@Injectable({ providedIn: 'root' })
export class CommonPasswords {
  private readonly http = inject(HttpClient);
  readonly list = signal<ReadonlySet<string> | null>(null);
  private requested = false;

  load(): void {
    if (this.requested) return;
    this.requested = true;
    this.http.get('common-passwords.txt', { responseType: 'text' }).subscribe({
      next: (t) =>
        this.list.set(
          new Set(
            t
              .split('\n')
              .map((w) => w.trim().toLowerCase())
              .filter(Boolean),
          ),
        ),
      error: () => (this.requested = false),
    });
  }
}

export function passwordPolicyValidator(
  context: () => PasswordContext | null,
  common: () => ReadonlySet<string> | null,
): ValidatorFn {
  return (c: AbstractControl): ValidationErrors | null => {
    const v = typeof c.value === 'string' ? c.value : '';
    if (!v) return { required: true };
    const failed = passwordRequirements(v, context(), common()).filter((r) => r.ok === false);
    return failed.length ? { policy: failed.map((r) => r.key) } : null;
  };
}

export const passwordsMatch: ValidatorFn = (group: AbstractControl): ValidationErrors | null => {
  const a = group.get('newPassword')?.value;
  const b = group.get('confirmPassword')?.value;
  return a && b && a !== b ? { mismatch: true } : null;
};

export function passwordErrorText(c: AbstractControl): string | null {
  if (c.hasError('required')) return 'Вкажіть пароль';
  const keys = c.getError('policy') as RequirementKey[] | null;
  return keys?.length ? passwordMessage(String(c.value ?? ''), keys) : null;
}
