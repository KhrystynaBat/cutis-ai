import { formatPhone, initials, longDate, longDateTime } from './format';

describe('profile formats', () => {
  it('long date with the month in the genitive', () => {
    expect(longDate('1990-12-14')).toBe('14 грудня 1990');
    expect(longDate('1984-03-01')).toBe('1 березня 1984');
    expect(longDate(null)).toBe('');
  });

  it('date and time in Kyiv time', () => {
    expect(longDateTime('2026-11-15T21:31:00Z')).toBe('15 листопада 2026, 23:31');
    expect(longDateTime('2026-07-01T22:05:00Z')).toBe('2 липня 2026, 01:05'); // summer time
  });

  it('Ukrainian phone numbers in groups, others as entered', () => {
    expect(formatPhone('+380 (44) 200-11-01')).toBe('+380 44 200 11 01');
    expect(formatPhone('380442001101')).toBe('+380 44 200 11 01');
    expect(formatPhone('+48 123 456 789')).toBe('+48 123 456 789');
    expect(formatPhone(null)).toBe('');
  });

  it('initials of the first and last name', () => {
    expect(initials('Олена', 'Гончаренко')).toBe('ОГ');
    expect(initials('олена', null)).toBe('О');
    expect(initials(null, null)).toBe('');
  });
});
