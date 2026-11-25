import {
  passwordErrorText,
  passwordHint,
  passwordPolicyValidator,
  passwordRequirements,
  passwordStrength,
} from './password';
import { FormControl } from '@angular/forms';

const common = new Set(['password', 'qwerty', 'password123']);
const ctx = { email: 'olena.kovalenko@x.test', names: ['Олена', 'Коваленко', null] };

function failed(pw: string, c = ctx): string[] {
  return passwordRequirements(pw, c, common)
    .filter((r) => r.ok === false)
    .map((r) => r.key);
}

describe('password policy', () => {
  it('accepts a strong password', () => {
    expect(failed('Zx!9mLpR2tq#')).toEqual([]);
    expect(
      passwordStrength('Zx!9mLpR2tq#', passwordRequirements('Zx!9mLpR2tq#', ctx, common)),
    ).toBe(3);
  });

  it('names each unmet requirement', () => {
    expect(failed('Ab1!xyzq')).toEqual(['length']);
    expect(failed('abcxyzmq!9pw')).toContain('upper');
    expect(failed('ABCXYZMQ!9PW')).toContain('lower');
    expect(failed('Abcxyzmq!pwR')).toContain('digit');
    expect(failed('Abcxyzmq9pwR')).toContain('special');
    expect(failed('Password123!')).toContain('common');
    expect(failed('Zx!9aaaaPmLr')).toContain('sequence');
    expect(failed('Zx!9mL1234pr')).toContain('sequence');
    expect(failed('Kovalenko#26x')).toContain('personal');
    expect(failed('Олена#2026xZq')).toContain('personal');
  });

  it('leaves unknown what cannot be checked here', () => {
    const reqs = passwordRequirements('Zx!9mLpR2tq#', null, null);
    expect(reqs.find((r) => r.key === 'personal')?.ok).toBeNull();
    expect(reqs.find((r) => r.key === 'common')?.ok).toBeNull();
  });

  it('the validator gives a concrete message', () => {
    const c = new FormControl('abcxyzmq!9pw', {
      nonNullable: true,
      validators: passwordPolicyValidator(
        () => ctx,
        () => common,
      ),
    });
    expect(passwordErrorText(c)).toBe('Додайте велику літеру');
    c.setValue('');
    expect(passwordErrorText(c)).toBe('Вкажіть пароль');
  });

  it('one short hint: appears after typing, names what is missing, disappears when met', () => {
    expect(passwordHint('', ctx, common)).toBeNull();
    expect(passwordHint('Abcxyzmq9pwR', ctx, common)).toBe('Додайте спецсимвол');
    expect(passwordHint('Abcxyzmqpwrt', ctx, common)).toBe('Додайте цифру й спецсимвол');
    expect(passwordHint('Ab1!xyzq', ctx, common)).toBe('Щонайменше 12 символів');
    expect(passwordHint('abxq', ctx, common)).toBe(
      'Щонайменше 12 символів; додайте велику літеру, цифру й спецсимвол',
    );
    expect(passwordHint('Password123!', ctx, common)).toBe('Це поширений пароль — оберіть інший');
    expect(passwordHint('Zx!9mLpR2tq#', ctx, common)).toBeNull();
  });
});
