export const DISPLAY_TIMEZONE = 'Europe/Kyiv';

const MONTHS_GENITIVE = [
  'січня',
  'лютого',
  'березня',
  'квітня',
  'травня',
  'червня',
  'липня',
  'серпня',
  'вересня',
  'жовтня',
  'листопада',
  'грудня',
];

export function longDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const [y, m, d] = iso.slice(0, 10).split('-').map(Number);
  if (!y || !m || !d) return iso;
  return `${d} ${MONTHS_GENITIVE[m - 1]} ${y}`;
}

export function longDateTime(iso: string | null | undefined, timeZone = DISPLAY_TIMEZONE): string {
  if (!iso) return '';
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone,
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(iso));
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return `${longDate(`${get('year')}-${get('month')}-${get('day')}`)}, ${get('hour')}:${get('minute')}`;
}

export function formatPhone(phone: string | null | undefined): string {
  if (!phone) return '';
  const digits = phone.replace(/\D/g, '');
  const local = digits.startsWith('380') && digits.length === 12 ? digits.slice(3) : null;
  if (!local) return phone;
  return `+380 ${local.slice(0, 2)} ${local.slice(2, 5)} ${local.slice(5, 7)} ${local.slice(7)}`;
}

export function initials(
  first: string | null | undefined,
  last: string | null | undefined,
): string {
  return [first, last]
    .map((x) => x?.trim().charAt(0) ?? '')
    .join('')
    .toLocaleUpperCase('uk');
}
