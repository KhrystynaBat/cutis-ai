import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { passwordLink } from '../../core/api/admin-users-api';
import { Profile, Role } from '../../core/auth/auth.models';
import { AuthService } from '../../core/auth/auth.service';
import { Shell } from './shell';

describe('Shell', () => {
  async function render(role: Role): Promise<HTMLElement> {
    TestBed.configureTestingModule({
      imports: [Shell],
      providers: [provideRouter([]), provideHttpClient(), provideHttpClientTesting()],
    });
    const loaded = TestBed.inject(AuthService).load();
    const user: Profile = { id: '1', firstName: 'Ім', lastName: 'Пр', email: 'x@x.test', role };
    TestBed.inject(HttpTestingController).expectOne('/api/v1/auth/me').flush(user);
    await loaded;
    const fixture = TestBed.createComponent(Shell);
    await fixture.whenStable();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows admin navigation only to admins', async () => {
    const el = await render('Admin');
    expect(el.textContent).toContain('Користувачі');
    expect(el.textContent).toContain('Адміністратор');
  });

  it('does not show admin navigation to a doctor', async () => {
    const el = await render('Doctor');
    expect(el.textContent).not.toContain('Користувачі');
    expect(el.textContent).toContain('Лікар');
  });
});

describe('passwordLink', () => {
  it('puts the token into the URL fragment, not the query string', () => {
    const link = passwordLink('abc+/=', 'https://dl.example');
    expect(link).toBe('https://dl.example/set-password#token=abc%2B%2F%3D');
    expect(link).not.toContain('?');
  });
});
