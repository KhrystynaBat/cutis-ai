import { BreakpointObserver } from '@angular/cdk/layout';
import { Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatDividerModule } from '@angular/material/divider';
import { MatIconModule } from '@angular/material/icon';
import { MatListModule } from '@angular/material/list';
import { MatMenuModule } from '@angular/material/menu';
import { MatSidenavModule } from '@angular/material/sidenav';
import { MatToolbarModule } from '@angular/material/toolbar';
import {
  ActivatedRoute,
  NavigationEnd,
  Router,
  RouterLink,
  RouterLinkActive,
  RouterOutlet,
} from '@angular/router';
import { filter, map } from 'rxjs';

import { ROLE_LABELS, Role } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { openChangePassword } from '../../features/profile/open-change-password';
import { NotificationBell } from './notification-bell';
import { InitialsPipe, ShortNamePipe } from '../names';

export interface NavItem {
  label: string;
  icon: string;
  link: string;
}

/** Sidebar navigation per role. */
export const NAV_BY_ROLE: Record<Role, NavItem[]> = {
  Admin: [
    { label: 'Користувачі', icon: 'group', link: '/admin/users' },
    { label: 'Стан системи', icon: 'monitor_heart', link: '/admin/system' },
  ],
  Doctor: [
    { label: 'Головна', icon: 'home', link: '/doctor/dashboard' },
    { label: 'Пацієнти', icon: 'groups', link: '/doctor/patients' },
    { label: 'Випадки', icon: 'clinical_notes', link: '/doctor/cases' },
    { label: 'Направлення', icon: 'send', link: '/doctor/referrals' },
  ],
  LabSpecialist: [{ label: 'Направлення', icon: 'biotech', link: '/lab/referrals' }],
};

@Component({
  selector: 'app-shell',
  imports: [
    ShortNamePipe,
    InitialsPipe,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    MatSidenavModule,
    MatToolbarModule,
    MatListModule,
    MatIconModule,
    MatButtonModule,
    MatMenuModule,
    MatDividerModule,
    NotificationBell,
  ],
  templateUrl: './shell.html',
  styleUrl: './shell.scss',
})
export class Shell {
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  protected readonly auth = inject(AuthService);
  protected readonly roleLabels = ROLE_LABELS;

  readonly isMobile = toSignal(
    inject(BreakpointObserver)
      .observe('(max-width: 959.98px)')
      .pipe(map((s) => s.matches)),
    { initialValue: false },
  );

  readonly navItems = computed(() => {
    const u = this.auth.user();
    return u ? NAV_BY_ROLE[u.role] : [];
  });

  private readonly sectionTitleSig = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map(() => this.currentSectionTitle()),
    ),
    { initialValue: this.currentSectionTitle() },
  );
  readonly sectionTitle = computed(() => this.sectionTitleSig() ?? 'CutisAI');

  private readonly dialog = inject(MatDialog);

  changePassword(): void {
    openChangePassword(this.dialog);
  }

  logout(): void {
    this.auth.logout().subscribe(() => void this.router.navigate(['/login']));
  }

  private currentSectionTitle(): string | undefined {
    let r = this.route.snapshot;
    while (r.firstChild) {
      r = r.firstChild;
    }
    return r.data['sectionTitle'] as string | undefined;
  }
}
