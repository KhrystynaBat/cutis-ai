import { MatDialog } from '@angular/material/dialog';

import { ChangePasswordDialog } from './change-password-dialog';

export function openChangePassword(dialog: MatDialog): void {
  dialog.open(ChangePasswordDialog, {
    width: '520px',
    maxWidth: '95vw',
    autoFocus: 'first-tabbable',
  });
}
