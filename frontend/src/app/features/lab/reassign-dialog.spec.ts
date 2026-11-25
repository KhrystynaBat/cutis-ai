import { TestBed } from '@angular/core/testing';
import { MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';

import { ReassignData, ReassignDialog } from './reassign-dialog';

describe('ReassignDialog («Передати колезі»)', () => {
  function setup(data: ReassignData) {
    const closed: unknown[] = [];
    TestBed.configureTestingModule({
      imports: [ReassignDialog],
      providers: [
        { provide: MAT_DIALOG_DATA, useValue: data },
        { provide: MatDialogRef, useValue: { close: (v: unknown) => closed.push(v) } },
      ],
    });
    const fixture = TestBed.createComponent(ReassignDialog);
    fixture.detectChanges();
    const el = fixture.nativeElement as HTMLElement;
    const buttons = () => [...el.querySelectorAll('button')].map((b) => b.textContent?.trim());
    return { fixture, closed, el, buttons };
  }

  it('requires a colleague, then closes with their id', () => {
    const { fixture, closed, el } = setup({
      referralNumber: 'REF-2026-000005',
      colleagues: [{ id: 'l2', firstName: 'Ірина', lastName: 'Бондар', middleName: 'Петрівна' }],
    });
    expect(el.textContent).toContain('REF-2026-000005');
    fixture.componentInstance.submit();
    expect(closed).toEqual([]);
    expect(fixture.componentInstance.target.touched).toBe(true);
    fixture.componentInstance.target.setValue('l2');
    fixture.componentInstance.submit();
    expect(closed).toEqual(['l2']);
  });

  it('without other active lab specialists says so and offers no «Передати»', () => {
    const { el, buttons } = setup({ referralNumber: 'REF-1', colleagues: [] });
    expect(el.textContent).toContain('Немає інших активних лаборантів');
    expect(buttons()).toEqual(['Скасувати']);
  });
});
