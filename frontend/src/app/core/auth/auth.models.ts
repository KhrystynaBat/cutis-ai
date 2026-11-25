export type Role = 'Admin' | 'Doctor' | 'LabSpecialist';
export type Sex = 'Female' | 'Male';

export const SEX_LABELS: Record<Sex, string> = { Female: 'Жіноча', Male: 'Чоловіча' };

export interface Profile {
  id: string;
  firstName: string | null;
  lastName: string | null;
  middleName?: string | null;
  phone?: string | null;
  birthDate?: string | null;
  sex?: Sex | null;
  email: string;
  role: Role;
  pendingEmailMasked?: string | null;
  /** last successful sign-in (ISO, UTC) */
  lastLoginAt?: string | null;
  greetingName?: string | null;
}

export interface ProfileUpdate {
  firstName: string;
  lastName: string;
  middleName: string | null;
  phone: string | null;
  birthDate: string | null;
  sex: Sex | null;
}

export function greeting(p: Profile | null): string {
  return p?.greetingName ? `Вітаємо, ${p.greetingName}!` : 'Вітаємо!';
}

export interface LoginPending {
  status: 'confirmation_required';
  emailMasked: string;
  expiresInMinutes: number;
}

export function isLoginPending(r: Profile | LoginPending): r is LoginPending {
  return (r as LoginPending).status === 'confirmation_required';
}

export const ROLE_LABELS: Record<Role, string> = {
  Admin: 'Адміністратор',
  Doctor: 'Лікар',
  LabSpecialist: 'Лабораторний спеціаліст',
};

/** Landing page after login. */
export const HOME_BY_ROLE: Record<Role, string> = {
  Admin: '/admin/users',
  Doctor: '/doctor/dashboard',
  LabSpecialist: '/lab/referrals',
};
