import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { ROLE_LABELS, SEX_LABELS } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { NotifyService } from '../../core/notify.service';
import { formatPhone, initials, longDate, longDateTime } from '../../shared/format';
import { fullName } from '../../shared/names';
import { openChangePassword } from './open-change-password';

@Component({
  selector: 'app-profile-page',
  imports: [RouterLink, MatButtonModule, MatIconModule],
  template: `
    @if (auth.user(); as u) {
      <section class="dl-card profile" aria-labelledby="profile-name">
        <header class="head">
          <div class="avatar" aria-hidden="true">
            @if (initialsText()) {
              {{ initialsText() }}
            } @else {
              <mat-icon>person</mat-icon>
            }
          </div>
          <div class="who">
            <h2 id="profile-name">{{ name() }}</h2>
            <div class="sub">{{ roleLabels[u.role] }}</div>
          </div>
          <a mat-flat-button routerLink="/profile/edit">
            <mat-icon>edit</mat-icon> Редагувати профіль
          </a>
        </header>

        <section class="block" aria-labelledby="pb-personal">
          <h3 id="pb-personal">Особисті дані</h3>
          <dl class="fields">
            <div>
              <dt>Прізвище</dt>
              <dd [class.empty]="!u.lastName">{{ u.lastName || notSet }}</dd>
            </div>
            <div>
              <dt>Ім'я</dt>
              <dd [class.empty]="!u.firstName">{{ u.firstName || notSet }}</dd>
            </div>
            <div>
              <dt>По батькові</dt>
              <dd [class.empty]="!u.middleName">{{ u.middleName || notSet }}</dd>
            </div>
            <div>
              <dt>Дата народження</dt>
              <dd [class.empty]="!u.birthDate">{{ longDate(u.birthDate) || notSet }}</dd>
            </div>
            <div>
              <dt>Стать</dt>
              <dd [class.empty]="!u.sex">{{ u.sex ? sexLabels[u.sex] : notSet }}</dd>
            </div>
          </dl>
        </section>

        <section class="block" aria-labelledby="pb-contacts">
          <h3 id="pb-contacts">Контактні дані</h3>
          <dl class="fields">
            <div class="wide">
              <dt>Електронна пошта</dt>
              <dd>
                {{ u.email }}
                @if (u.pendingEmailMasked; as pending) {
                  <span class="pending" role="status">
                    Очікує підтвердження: {{ pending }} ·
                    <button
                      type="button"
                      class="link"
                      (click)="cancelEmailChange()"
                      [disabled]="cancelling()"
                    >
                      Скасувати
                    </button>
                  </span>
                }
              </dd>
            </div>
            <div>
              <dt>Телефон</dt>
              <dd [class.empty]="!u.phone">{{ formatPhone(u.phone) || notSet }}</dd>
            </div>
          </dl>
        </section>

        <section class="block" aria-labelledby="pb-security">
          <h3 id="pb-security">Безпека</h3>
          <dl class="fields single">
            <div>
              <dt>Пароль</dt>
              <dd class="inline-action">
                <span aria-label="Пароль приховано">••••••••</span>
                <button mat-button type="button" (click)="changePassword()">Змінити</button>
              </dd>
            </div>
            <div>
              <dt>Вхід</dt>
              <dd>Підтвердження через електронну пошту</dd>
            </div>
            <div>
              <dt>Останній вхід</dt>
              <dd [class.empty]="!u.lastLoginAt">{{ longDateTime(u.lastLoginAt) || notSet }}</dd>
            </div>
          </dl>
        </section>
      </section>
    }
  `,
  styleUrl: './profile.scss',
})
export class ProfilePage implements OnInit {
  protected readonly auth = inject(AuthService);
  private readonly dialog = inject(MatDialog);
  private readonly notify = inject(NotifyService);

  readonly roleLabels = ROLE_LABELS;
  readonly sexLabels = SEX_LABELS;
  readonly notSet = 'Не вказано';
  readonly longDate = longDate;
  readonly longDateTime = longDateTime;
  readonly formatPhone = formatPhone;
  readonly cancelling = signal(false);
  readonly name = computed(() => fullName(this.auth.user()));
  readonly initialsText = computed(() => {
    const u = this.auth.user();
    return initials(u?.firstName, u?.lastName);
  });

  ngOnInit(): void {
    void this.auth.load();
  }

  changePassword(): void {
    openChangePassword(this.dialog);
  }

  cancelEmailChange(): void {
    this.cancelling.set(true);
    this.auth
      .cancelEmailChange()
      .pipe(finalize(() => this.cancelling.set(false)))
      .subscribe({
        next: () => this.notify.success('Зміну адреси скасовано'),
        error: (e) => this.notify.error(e, 'Не вдалося скасувати зміну адреси'),
      });
  }
}
