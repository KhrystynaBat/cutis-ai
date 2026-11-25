import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Title } from '@angular/platform-browser';
import { Router, TitleStrategy, provideRouter } from '@angular/router';

import { AppTitleStrategy } from './app-title-strategy';

@Component({ template: '' })
class Blank {}

describe('AppTitleStrategy', () => {
  it('«<page> — CutisAI» with a route title, plain «CutisAI» without', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'users', title: 'Користувачі', component: Blank },
          { path: 'plain', component: Blank },
        ]),
        { provide: TitleStrategy, useClass: AppTitleStrategy },
      ],
    });
    const router = TestBed.inject(Router);
    const title = TestBed.inject(Title);
    await router.navigateByUrl('/users');
    expect(title.getTitle()).toBe('Користувачі — CutisAI');
    await router.navigateByUrl('/plain');
    expect(title.getTitle()).toBe('CutisAI');
  });
});
