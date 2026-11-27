import { OVERLAY_DEFAULT_CONFIG } from '@angular/cdk/overlay';
import { registerLocaleData } from '@angular/common';
import { provideHttpClient, withInterceptors, withXsrfConfiguration } from '@angular/common/http';
import localeUk from '@angular/common/locales/uk';
import {
  ApplicationConfig,
  LOCALE_ID,
  inject,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { MAT_ICON_DEFAULT_OPTIONS } from '@angular/material/icon';
import { MatPaginatorIntl } from '@angular/material/paginator';
import { TitleStrategy, provideRouter, withComponentInputBinding } from '@angular/router';

import { routes } from './app.routes';
import { AppTitleStrategy } from './core/app-title-strategy';
import { AuthService } from './core/auth/auth.service';
import { requestIdInterceptor } from './core/http/request-id.interceptor';
import { sessionExpiredInterceptor } from './core/http/session-expired.interceptor';
import { UkPaginatorIntl } from './shared/paginator-intl';

registerLocaleData(localeUk);

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes, withComponentInputBinding()),
    provideHttpClient(
      withInterceptors([requestIdInterceptor, sessionExpiredInterceptor]),
      withXsrfConfiguration({ cookieName: 'dl_csrf', headerName: 'X-CSRF-Token' }),
    ),
    provideAppInitializer(() => inject(AuthService).load()),
    { provide: TitleStrategy, useClass: AppTitleStrategy },
    { provide: LOCALE_ID, useValue: 'uk' },
    { provide: MatPaginatorIntl, useClass: UkPaginatorIntl },
    { provide: MAT_ICON_DEFAULT_OPTIONS, useValue: { fontSet: 'material-symbols-outlined' } },
    // keep overlays outside the scaled app-root so their positions stay right
    { provide: OVERLAY_DEFAULT_CONFIG, useValue: { usePopover: false } },
  ],
};
