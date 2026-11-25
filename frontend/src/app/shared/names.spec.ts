import { fullName, shortName } from './names';

describe('names', () => {
  const withMiddle = { firstName: 'Марія', lastName: 'Шевчук', middleName: 'Василівна' };
  const without = { firstName: 'Тарас', lastName: 'Франко', middleName: null };

  it('full name: «Прізвище Ім’я По батькові», without an empty patronymic', () => {
    expect(fullName(withMiddle)).toBe('Шевчук Марія Василівна');
    expect(fullName(without)).toBe('Франко Тарас');
    expect(fullName({ firstName: 'Ім’я', lastName: 'Прізвище' })).toBe('Прізвище Ім’я');
    expect(fullName(null)).toBe('');
  });

  it('short name: «Прізвище І. П.»', () => {
    expect(shortName(withMiddle)).toBe('Шевчук М. В.');
    expect(shortName(without)).toBe('Франко Т.');
    expect(shortName(undefined)).toBe('');
  });
});

describe('administrator without a name', () => {
  it('is shown as «Адміністратор»', () => {
    const admin = { firstName: null, lastName: null, middleName: null };
    expect(fullName(admin)).toBe('Адміністратор');
    expect(shortName(admin)).toBe('Адміністратор');
  });
});
