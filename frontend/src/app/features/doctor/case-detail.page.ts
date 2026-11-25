import { DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, inject, input, signal, viewChild } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatDialog } from '@angular/material/dialog';
import { MatIconModule } from '@angular/material/icon';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatTabsModule } from '@angular/material/tabs';
import { Router, RouterLink } from '@angular/router';
import { finalize } from 'rxjs';

import { parseApiError } from '../../core/api/api-error';
import { CaseDetail, DoctorApi } from '../../core/api/doctor-api';
import { LabResult, ReferralApi } from '../../core/api/referral-api';
import { NotifyService } from '../../core/notify.service';
import { CaseStatusChip } from '../../shared/case-status-chip';
import {
  IMAGE_VIEWER_CONFIG,
  ImageViewerData,
  ImageViewerDialog,
} from '../../shared/dialogs/image-viewer-dialog';
import { PhotoPicker } from '../../shared/forms/photo-picker';
import { LabResultView } from '../../shared/lab-result-view';
import { PdfActions } from '../../shared/pdf-actions';
import { ReferralStatusChip } from '../../shared/referral-status-chip';
import { AnalysisPanel } from './analysis-panel';
import { AssessmentPanel } from './assessment-panel';
import { FullNamePipe } from '../../shared/names';

@Component({
  selector: 'app-case-detail-page',
  imports: [
    FullNamePipe,
    DatePipe,
    DecimalPipe,
    RouterLink,
    MatTabsModule,
    MatButtonModule,
    MatIconModule,
    MatProgressBarModule,
    CaseStatusChip,
    PhotoPicker,
    AnalysisPanel,
    AssessmentPanel,
    LabResultView,
    PdfActions,
    ReferralStatusChip,
  ],
  templateUrl: './case-detail.page.html',
  styleUrl: './case-detail.page.scss',
})
export class CaseDetailPage implements OnInit {
  readonly id = input.required<string>();

  private readonly api = inject(DoctorApi);
  private readonly referrals = inject(ReferralApi);
  private readonly router = inject(Router);
  private readonly notify = inject(NotifyService);
  private readonly dialog = inject(MatDialog);
  protected readonly picker = viewChild(PhotoPicker);

  readonly caseData = signal<CaseDetail | null>(null);
  readonly newPhoto = signal<File | null>(null);
  readonly uploading = signal(false);
  readonly imageFailed = signal(false);
  readonly labResult = signal<LabResult | null>(null);

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.api.getCase(this.id()).subscribe({
      next: (c) => {
        this.caseData.set(c);
        this.imageFailed.set(false);
        this.loadLabResult(c);
      },
      error: (e) => {
        this.notify.error(e, 'Випадок не знайдено');
        void this.router.navigate(['/doctor/cases']);
      },
    });
  }

  onChanged(c: CaseDetail): void {
    this.caseData.set(c);
    this.loadLabResult(c);
  }

  private loadLabResult(c: CaseDetail): void {
    const ref = c.referral;
    if (!ref || ref.status !== 'Completed') {
      this.labResult.set(null);
      return;
    }
    this.referrals.getLabResult(ref.id).subscribe({
      next: (r) => this.labResult.set(r),
      error: (e) => this.notify.error(e, 'Не вдалося завантажити результат лабораторії'),
    });
  }

  openPhoto(url: string, location: string): void {
    this.dialog.open<ImageViewerDialog, ImageViewerData>(ImageViewerDialog, {
      ...IMAGE_VIEWER_CONFIG,
      data: { url, alt: `Дерматоскопічне фото ураження, локалізація: ${location}` },
    });
  }

  shortId(id: string): string {
    return id.slice(0, 8);
  }

  uploadPhoto(): void {
    const file = this.newPhoto();
    const picker = this.picker();
    if (!file || picker?.blocksSave()) return;
    this.uploading.set(true);
    this.api
      .uploadImage(this.id(), file, picker?.confirmNonDermoscopic() ?? false)
      .pipe(finalize(() => this.uploading.set(false)))
      .subscribe({
        next: () => {
          this.notify.success('Фото завантажено');
          this.newPhoto.set(null);
          this.picker()?.reset();
          this.load();
        },
        error: (e) => {
          if (parseApiError(e).code === 'IMAGE_NOT_DERMOSCOPIC') picker?.showWarning();
          else this.notify.error(e, 'Не вдалося завантажити фото');
        },
      });
  }
}
