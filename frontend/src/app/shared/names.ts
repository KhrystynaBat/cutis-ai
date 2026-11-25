import { Pipe, PipeTransform } from '@angular/core';

export interface PersonName {
  firstName: string | null;
  lastName: string | null;
  middleName?: string | null;
}

/** Shown for an administrator without a name. */
export const NO_NAME = 'Адміністратор';

export function fullName(p: PersonName | null | undefined): string {
  if (!p) return '';
  return [p.lastName, p.firstName, p.middleName].filter(Boolean).join(' ') || NO_NAME;
}

export function shortName(p: PersonName | null | undefined): string {
  if (!p) return '';
  const initials = [p.firstName, p.middleName]
    .filter((x): x is string => !!x)
    .map((x) => `${x.charAt(0)}.`)
    .join(' ');
  return [p.lastName, initials].filter(Boolean).join(' ') || NO_NAME;
}

@Pipe({ name: 'fullName' })
export class FullNamePipe implements PipeTransform {
  transform(p: PersonName | null | undefined): string {
    return fullName(p);
  }
}

@Pipe({ name: 'shortName' })
export class ShortNamePipe implements PipeTransform {
  transform(p: PersonName | null | undefined): string {
    return shortName(p);
  }
}
