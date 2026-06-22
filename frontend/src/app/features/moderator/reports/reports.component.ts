/**
 * Moderator reports dashboard.
 *
 * Shows pending reports for the moderator's assigned cells.
 *
 * TODO:
 *   1. On init: call ReportService.getPendingReports()
 *   2. Display reports sorted by report_count DESC:
 *      - Content preview (the reported post/message)
 *      - Report count badge
 *      - Reason(s) reported
 *      - Reporter info (anonymous to moderator – show count only)
 *   3. "מחיקה" button (VALID decision) + mandatory note
 *   4. "ביטול דיווח" button (INVALID decision) + optional note
 *   5. After decision: remove from list
 *   6. Show history tab: processed reports
 *
 * Important:
 *   - Moderator can NOT see private messages (no DM content shown)
 *   - Moderator can NOT see reporter's identity
 */

import { Component, OnInit, inject } from '@angular/core';

import { Report } from '../../../core/models';
import { ReportDecision, REPORT_REASON_LABELS } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';

@Component({
  selector: 'app-moderator-reports',
  standalone: true,
  template: `
    <div style="padding: 1rem; direction: rtl">
      <h1>לוח בקרת מבקר – דיווחים ממתינים</h1>

      @if (pendingReports.length === 0 && !isLoading) {
        <p>אין דיווחים ממתינים. כל הכבוד!</p>
      }

      @for (report of pendingReports; track report.id) {
        <div style="border: 1px solid #e5e7eb; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
          <p><strong>סיבה:</strong> {{ reasonLabels[report.reason] }}</p>
          <p><strong>תיאור:</strong> {{ report.description ?? '–' }}</p>
          <!-- TODO: show the actual reported content preview -->
          <!-- TODO: show report count badge -->

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

  pendingReports: Report[] = [];
  isLoading = false;
  readonly reasonLabels = REPORT_REASON_LABELS;

  ngOnInit(): void {
    this.isLoading = true;
    // TODO: implement
    this.isLoading = false;
  }

  decide(reportId: string, decision: 'valid' | 'invalid'): void {
    void reportId;
    void (decision === 'valid' ? ReportDecision.VALID : ReportDecision.INVALID);
    // TODO: call reportService.decideReport(reportId, { decision: d })
  }
}
