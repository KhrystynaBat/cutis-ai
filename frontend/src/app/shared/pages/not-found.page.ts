import { Component } from '@angular/core';

import { ErrorPage } from './error-page';

@Component({
  selector: 'app-not-found-page',
  imports: [ErrorPage],
  template: `<app-error-page
    code="404"
    icon="search_off"
    title="Сторінку не знайдено"
    text="Можливо, посилання застаріло або сторінку було переміщено."
  />`,
})
export class NotFoundPage {}
