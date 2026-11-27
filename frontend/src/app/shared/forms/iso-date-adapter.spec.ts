import { IsoDateAdapter } from './iso-date-adapter';

describe('IsoDateAdapter', () => {
  const a = new IsoDateAdapter();

  it('parses typed dd.mm.yyyy into yyyy-mm-dd', () => {
    expect(a.parse('7.3.1985')).toBe('1985-03-07');
    expect(a.parse('31.12.2026')).toBe('2026-12-31');
    expect(a.parse('')).toBeNull();
  });

  it('rejects impossible dates', () => {
    expect(a.parse('31.02.2026')).toBe('');
    expect(a.parse('abc')).toBe('');
    expect(a.isValid('2026-02-30')).toBe(false);
  });

  it('shows the value as dd.mm.yyyy', () => {
    expect(a.format('2026-11-05', 'input')).toBe('05.11.2026');
  });

  it('moves between months without overflowing', () => {
    expect(a.addCalendarMonths('2026-01-31', 1)).toBe('2026-02-28');
    expect(a.addCalendarDays('2026-12-31', 1)).toBe('2027-01-01');
    expect(a.addCalendarYears('2024-02-29', 1)).toBe('2025-02-28');
  });

  it('keeps empty form values empty', () => {
    expect(a.deserialize('')).toBeNull();
    expect(a.deserialize('2026-11-27')).toBe('2026-11-27');
  });
});
