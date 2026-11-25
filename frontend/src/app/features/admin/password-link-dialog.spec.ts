import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA } from '@angular/material/dialog';

import { PasswordLinkData, PasswordLinkDialog } from './password-link-dialog';

describe('PasswordLinkDialog', () => {
  function render(emailQueued: boolean | undefined): string {
    const data: PasswordLinkData = {
      userName: 'Коваленко Олена Петрівна',
      token: {
        token: 'tok-123',
        expiresAt: '2026-11-12T10:00:00Z',
        purpose: 'Invitation',
        emailQueued,
      },
    };
    TestBed.configureTestingModule({
      imports: [PasswordLinkDialog],
      providers: [{ provide: MAT_DIALOG_DATA, useValue: data }],
    });
    const fixture = TestBed.createComponent(PasswordLinkDialog);
    fixture.detectChanges();
    return (fixture.nativeElement as HTMLElement).textContent ?? '';
  }

  it('keeps the link and the copy button, and says it was also e-mailed', () => {
    const text = render(true);
    expect(text).toContain('/set-password#token=tok-123');
    expect(text).toContain('Копіювати');
    expect(text).toContain('Посилання також надіслано на електронну пошту');
  });

  it('without real e-mail shows only the link', () => {
    expect(render(undefined)).not.toContain('надіслано на електронну пошту');
  });
});
