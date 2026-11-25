import { Component } from '@angular/core';

import { ErrorPage } from './error-page';

@Component({
  selector: 'app-forbidden-page',
  imports: [ErrorPage],
  template: `<app-error-page
    code="403"
    icon="block"
    title="Доступ заборонено"
    text="У вас немає прав для перегляду цієї сторінки."
  />`,
})
export class ForbiddenPage {}
