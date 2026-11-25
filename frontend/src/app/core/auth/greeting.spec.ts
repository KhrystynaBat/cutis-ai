import { greeting } from './auth.models';

describe('greeting', () => {
  it('uses the vocative from the backend', () => {
    expect(
      greeting({
        id: '1',
        firstName: 'Олена',
        lastName: 'Гончаренко',
        email: 'o@x.test',
        role: 'Doctor',
        greetingName: 'Олено Віталіївно',
      }),
    ).toBe('Вітаємо, Олено Віталіївно!');
  });

  it('greets without a name when there is no vocative or no user', () => {
    expect(
      greeting({ id: '1', firstName: null, lastName: null, email: 'a@x.test', role: 'Admin' }),
    ).toBe('Вітаємо!');
    expect(greeting(null)).toBe('Вітаємо!');
  });
});
