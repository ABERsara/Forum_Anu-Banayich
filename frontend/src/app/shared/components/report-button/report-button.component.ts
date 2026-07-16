import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, input, signal } from '@angular/core';

import { REPORT_REASON_LABELS, ReportReason, ReportTargetType } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ErrorDisplayComponent } from '../error-display/error-display.component';

@Component({
  selector: 'app-report-button',
  standalone: true,
  imports: [ErrorDisplayComponent],
  templateUrl: './report-button.component.html',
  styleUrl: './report-button.component.scss',
})
export class ReportButtonComponent {
  private readonly reportService = inject(ReportService);

  contentType = input.required<ReportTargetType>();
  contentId = input.required<string>();

  showDialog = signal(false);
  reason = signal<ReportReason>(ReportReason.HARASSMENT);
  description = signal('');
  isSubmitting = signal(false);
  isSubmitted = signal(false);
  errorMessage = signal<string | null>(null);

  readonly reasonOptions = Object.values(ReportReason);
  readonly reasonLabels = REPORT_REASON_LABELS;

  onOpenClick(): void {
    this.errorMessage.set(null);
    this.showDialog.set(true);
  }

  onCancel(): void {
    this.showDialog.set(false);
  }

  onReasonChange(value: string): void {
    this.reason.set(value as ReportReason);
  }

  onDescriptionChange(value: string): void {
    this.description.set(value);
  }

  onSubmit(): void {
    this.isSubmitting.set(true);
    this.errorMessage.set(null);
    this.reportService
      .fileReport({
        target_type: this.contentType(),
        target_id: this.contentId(),
        reason: this.reason(),
        description: this.description().trim() || undefined,
      })
      .subscribe({
        next: () => {
          this.isSubmitting.set(false);
          this.showDialog.set(false);
          this.isSubmitted.set(true);
        },
        error: (err: HttpErrorResponse) => {
          this.isSubmitting.set(false);
          this.errorMessage.set(
            err.status === 409 ? 'כבר דיווחת על תוכן זה.' : 'אירעה שגיאה בשליחת הדיווח. נסה שוב.',
          );
        },
      });
  }
}
