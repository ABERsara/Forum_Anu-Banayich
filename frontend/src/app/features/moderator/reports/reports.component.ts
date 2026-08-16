/**
 * Moderator reports dashboard.
 *
 * Shows pending reports for the moderator's assigned cells, sorted by
 * report_count DESC (server-side – see ReportService.getPendingReports()).
 *
 * TODO:
 *   3. "מחיקה" button (VALID decision) + mandatory note
 *   4. "ביטול דיווח" button (INVALID decision) + optional note
 *   5. After decision: remove from list
 *   6. Show history tab: processed reports
 *
 * Important:
 *   - Moderator can NOT see private messages (no DM content shown)
 *   - Moderator can NOT see reporter's identity
 */

import { Component, OnInit, inject, signal } from '@angular/core';

import { ReportWithContent } from '../../../core/models';
import { ReportDecision, REPORT_REASON_LABELS } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const PREVIEW_LENGTH = 200;

@Component({
  selector: 'app-moderator-reports',
  standalone: true,
  imports: [LoadingSpinnerComponent, ErrorDisplayComponent],
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>לוח בקרת מבקר – דיווחים ממתינים</h1>

      @if (isLoading()) {
        <app-loading-spinner message="טוען דיווחים..." />
      }

      <app-error-display [message]="hasError() ? 'שגיאה בטעינת הדיווחים.' : ''" />

      @if (!isLoading() && !hasError() && pendingReports().length === 0) {
        <p>אין דיווחים ממתינים. כל הכבוד!</p>
      }

      @for (report of pendingReports(); track report.id) {
        <div style="border: 1px solid #e5e7eb; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
          <div style="display: flex; justify-content: space-between; align-items: start">
            <h3 style="margin: 0">{{ report.content_title }}</h3>
            <span
              style="background: #fee2e2; color: #991b1b; border-radius: 999px; padding: 0.125rem 0.625rem; font-size: 0.875rem; white-space: nowrap"
            >
              {{ report.report_count }} דיווחים
            </span>
          </div>
          <p>{{ previewOf(report.content_text) }}</p>
          <p><strong>סיבה:</strong> {{ reasonLabels[report.reason] }}</p>
          <p><strong>תיאור:</strong> {{ report.description ?? '–' }}</p>

          <div style="margin-top: 0.5rem">
            <button (click)="decide(report.id, 'valid')">מחיקת ההודעה (מוצדק)</button>
            <button (click)="decide(report.id, 'invalid')" style="margin-right: 0.5rem">
              ביטול הדיווח (שגוי)
            </button>
          </div>
        </div>
      }
    </div>
  `,
})
export class ModeratorReportsComponent implements OnInit {
  private readonly reportService = inject(ReportService);

  pendingReports = signal<ReportWithContent[]>([]);
  isLoading = signal(false);
  hasError = signal(false);
  readonly reasonLabels = REPORT_REASON_LABELS;

  ngOnInit(): void {
    this.isLoading.set(true);
    this.hasError.set(false);
    this.reportService.getPendingReports().subscribe({
      next: (result) => {
        this.pendingReports.set(result.items);
        this.isLoading.set(false);
      },
      error: () => {
        this.hasError.set(true);
        this.isLoading.set(false);
      },
    });
  }

  previewOf(contentText: string): string {
    return contentText.length > PREVIEW_LENGTH
      ? `${contentText.slice(0, PREVIEW_LENGTH)}…`
      : contentText;
  }

  decide(reportId: string, decision: 'valid' | 'invalid'): void {
    void reportId;
    void (decision === 'valid' ? ReportDecision.VALID : ReportDecision.INVALID);
    // TODO: call reportService.decideReport(reportId, { decision: d })
  }
}
