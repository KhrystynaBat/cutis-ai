import { Routes } from '@angular/router';

import { authGuard, guestGuard, homeRedirectGuard, roleGuard } from './core/auth/guards';
import { Shell } from './shared/layout/shell';

export const routes: Routes = [
  {
    path: 'email/confirm',
    title: 'Підтвердження нової адреси',
    loadComponent: () =>
      import('./features/profile/email-confirm.page').then((m) => m.EmailConfirmPage),
  },
  {
    path: 'login/confirm',
    title: 'Підтвердження входу',
    canActivate: [guestGuard],
    loadComponent: () =>
      import('./features/auth/login-confirm.page').then((m) => m.LoginConfirmPage),
  },
  {
    path: 'login',
    title: 'Вхід',
    canActivate: [guestGuard],
    loadComponent: () => import('./features/auth/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'set-password',
    title: 'Встановлення пароля',
    loadComponent: () => import('./features/auth/set-password.page').then((m) => m.SetPasswordPage),
  },
  {
    path: '',
    component: Shell,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', canActivate: [homeRedirectGuard], children: [] },
      {
        path: 'admin',
        canActivate: [roleGuard('Admin')],
        children: [
          {
            path: 'users',
            title: 'Користувачі',
            data: { sectionTitle: 'Користувачі' },
            loadComponent: () =>
              import('./features/admin/users-list.page').then((m) => m.UsersListPage),
          },
          {
            path: 'users/new',
            title: 'Новий користувач',
            data: { sectionTitle: 'Новий користувач' },
            loadComponent: () =>
              import('./features/admin/user-form.page').then((m) => m.UserFormPage),
          },
          {
            path: 'users/:id/edit',
            title: 'Редагування користувача',
            data: { sectionTitle: 'Редагування користувача' },
            loadComponent: () =>
              import('./features/admin/user-form.page').then((m) => m.UserFormPage),
          },
          {
            path: 'system',
            title: 'Стан системи',
            data: { sectionTitle: 'Стан системи' },
            loadComponent: () =>
              import('./features/system/system-status.page').then((m) => m.SystemStatusPage),
          },
        ],
      },
      {
        path: 'doctor',
        canActivate: [roleGuard('Doctor')],
        children: [
          {
            path: 'dashboard',
            title: 'Головна',
            data: { sectionTitle: 'Головна' },
            loadComponent: () =>
              import('./features/doctor/dashboard.page').then((m) => m.DoctorDashboardPage),
          },
          {
            path: 'patients',
            title: 'Пацієнти',
            data: { sectionTitle: 'Пацієнти' },
            loadComponent: () =>
              import('./features/doctor/patients-list.page').then((m) => m.PatientsListPage),
          },
          {
            path: 'patients/new',
            title: 'Новий пацієнт',
            data: { sectionTitle: 'Новий пацієнт' },
            loadComponent: () =>
              import('./features/doctor/patient-form.page').then((m) => m.PatientFormPage),
          },
          {
            path: 'patients/:id',
            title: 'Картка пацієнта',
            data: { sectionTitle: 'Картка пацієнта' },
            loadComponent: () =>
              import('./features/doctor/patient-detail.page').then((m) => m.PatientDetailPage),
          },
          {
            path: 'patients/:id/edit',
            title: 'Редагування пацієнта',
            data: { sectionTitle: 'Редагування пацієнта' },
            loadComponent: () =>
              import('./features/doctor/patient-form.page').then((m) => m.PatientFormPage),
          },
          {
            path: 'cases',
            title: 'Випадки',
            data: { sectionTitle: 'Випадки' },
            loadComponent: () =>
              import('./features/doctor/cases-list.page').then((m) => m.CasesListPage),
          },
          {
            path: 'cases/new',
            title: 'Новий випадок',
            data: { sectionTitle: 'Новий випадок' },
            loadComponent: () =>
              import('./features/doctor/case-form.page').then((m) => m.CaseFormPage),
          },
          {
            path: 'cases/:id',
            title: 'Картка випадку',
            data: { sectionTitle: 'Картка випадку' },
            loadComponent: () =>
              import('./features/doctor/case-detail.page').then((m) => m.CaseDetailPage),
          },
          {
            path: 'referrals',
            title: 'Направлення',
            data: { sectionTitle: 'Направлення' },
            loadComponent: () =>
              import('./features/doctor/referrals-list.page').then((m) => m.ReferralsListPage),
          },
          {
            path: 'referrals/:id',
            title: 'Направлення',
            data: { sectionTitle: 'Деталі направлення' },
            loadComponent: () =>
              import('./features/doctor/referral-detail.page').then((m) => m.ReferralDetailPage),
          },
          {
            path: 'notifications',
            title: 'Сповіщення',
            data: { sectionTitle: 'Сповіщення' },
            loadComponent: () =>
              import('./features/doctor/notifications.page').then((m) => m.NotificationsPage),
          },
          {
            path: 'cases/:id/edit',
            title: 'Редагування випадку',
            data: { sectionTitle: 'Редагування випадку' },
            loadComponent: () =>
              import('./features/doctor/case-form.page').then((m) => m.CaseFormPage),
          },
        ],
      },
      {
        path: 'lab',
        canActivate: [roleGuard('LabSpecialist')],
        children: [
          {
            path: 'referrals',
            title: 'Вхідні направлення',
            data: { sectionTitle: 'Вхідні направлення' },
            loadComponent: () =>
              import('./features/lab/lab-referrals-list.page').then((m) => m.LabReferralsListPage),
          },
          {
            path: 'referrals/:id',
            title: 'Опрацювання направлення',
            data: { sectionTitle: 'Опрацювання направлення' },
            loadComponent: () =>
              import('./features/lab/lab-referral-detail.page').then(
                (m) => m.LabReferralDetailPage,
              ),
          },
        ],
      },
      {
        path: 'profile',
        title: 'Мій профіль',
        data: { sectionTitle: 'Мій профіль' },
        loadComponent: () => import('./features/profile/profile.page').then((m) => m.ProfilePage),
      },
      {
        path: 'profile/edit',
        title: 'Редагування профілю',
        data: { sectionTitle: 'Мій профіль' },
        loadComponent: () =>
          import('./features/profile/profile-edit.page').then((m) => m.ProfileEditPage),
      },
    ],
  },
  {
    path: '403',
    title: 'Доступ заборонено',
    loadComponent: () => import('./shared/pages/forbidden.page').then((m) => m.ForbiddenPage),
  },
  {
    path: '**',
    title: 'Сторінку не знайдено',
    loadComponent: () => import('./shared/pages/not-found.page').then((m) => m.NotFoundPage),
  },
];
