import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';

export interface ImageViewerData {
  url: string;
  alt: string;
}

@Component({
  selector: 'app-image-viewer-dialog',
  imports: [MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <div class="viewer">
      <button
        mat-icon-button
        class="close"
        type="button"
        mat-dialog-close
        aria-label="Закрити перегляд"
      >
        <mat-icon>close</mat-icon>
      </button>
      <img [src]="data.url" [alt]="data.alt" />
    </div>
  `,
  styles: `
    .viewer {
      position: relative;
      width: 100%;
      height: 100%;
      display: grid;
      place-items: center;
      background: #111;
    }
    /* fills the screen keeping the photo's proportions (small photos are scaled up too) */
    img {
      width: 100%;
      height: 100%;
      object-fit: contain;
    }
    .close {
      position: absolute;
      top: 8px;
      right: 8px;
      z-index: 1;
      color: #fff;
      background: rgb(0 0 0 / 50%);
    }
  `,
})
export class ImageViewerDialog {
  readonly data = inject<ImageViewerData>(MAT_DIALOG_DATA);
}

export const IMAGE_VIEWER_CONFIG = {
  width: '100vw',
  height: '100vh',
  maxWidth: '100vw',
  maxHeight: '100vh',
  panelClass: 'dl-fullscreen-dialog',
};
