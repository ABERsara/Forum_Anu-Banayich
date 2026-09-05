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
 *   The copy that comes with those lives under `moderator.*` in
 *   he.json/en.json — no hardcoded Hebrew here any more (CONTRIBUTING §6).
 *
 * Important:
 *   - Moderator can NOT see private messages (no DM content shown)
 *   - Moderator can NOT see reporter's identity
 */

import { Component, OnInit, inject, signal } from '@angular/core';
import { TranslocoPipe } from '@jsverse/transloco';

import { ReportWithContent } from '../../../core/models';
import { POST_STATUS_LABELS, ReportDecision, REPORT_REASON_LABELS } from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const PREVIEW_LENGTH = 200;

/**
 * Stands in for a description the reporter left empty.
 *
 * A dash is a glyph, not copy: it reads the same in both languages and is
 * Bidi-neutral, so it stays out of the translation files — the same call the
 * dashboard chevron got in ABF-132.
 */
const NO_DESCRIPTION = '–';

@Component({
  selector: 'app-moderator-reports',
  standalone: true,
  imports: [TranslocoPipe, LoadingSpinnerComponent, ErrorDisplayComponent],
  template: `
    <!-- No direction here: the page inherits it from <html dir>, which
         LocaleService sets from the active language (CONTRIBUTING §6). -->
    <div style="padding: 1rem">
      <h1>{{ 'moderator.reports.title' | transloco }}</h1>

      @if (isLoading()) {
        <app-loading-spinner [message]="'moderator.reports.loading' | transloco" />
      }

      @if (hasError()) {
        <app-error-display [message]="'moderator.errors.load_reports_failed' | transloco" />
      }

      @if (!isLoading() && !hasError() && pendingReports().length === 0) {
        <p>{{ 'moderator.reports.empty' | transloco }}</p>
      }

      @for (report of pendingReports(); track report.id) {
        <div style="border: 1px solid #e5e7eb; margin: 0.5rem 0; padding: 1rem; border-radius: 8px">
          <div style="display: flex; justify-content: space-between; align-items: start">
            <!-- The reported post's title and body are what a user wrote:
                 shown as they were written, in either UI language (ABF-130). -->
            <h3 style="margin: 0">{{ report.content_title }}</h3>
            <span
              style="background: #fee2e2; color: #991b1b; border-radius: 999px; padding: 0.125rem 0.625rem; font-size: 0.875rem; white-space: nowrap"
            >
              {{ 'moderator.reports.report_count' | transloco: { count: report.report_count } }}
            </span>
          </div>
          <p>{{ previewOf(report.content_text) }}</p>
          <p>
            <strong>{{ 'moderator.reports.reason_label' | transloco }}</strong>
            {{ reasonLabels[report.reason] | transloco }}
          </p>
          <p>
            <strong>{{ 'moderator.reports.description_label' | transloco }}</strong>
            {{ report.description ?? noDescription }}
          </p>
          <p>
            <strong>{{ 'moderator.reports.content_status_label' | transloco }}</strong>
            {{ statusLabels[report.content_status] | transloco }}
          </p>

          <div style="margin-top: 0.5rem">
            <button type="button" (click)="decide(report.id, 'valid')">
              {{ 'moderator.reports.decide_valid' | transloco }}
            </button>
            <!-- margin-inline-start, not margin-right: the gap belongs between
                 the two buttons, and which physical side that is depends on the
                 page direction (CONTRIBUTING §6). -->
            <button
              type="button"
              (click)="decide(report.id, 'invalid')"
              style="margin-inline-start: 0.5rem"
            >
              {{ 'moderator.reports.decide_invalid' | transloco }}
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
  readonly statusLabels = POST_STATUS_LABELS;
  readonly noDescription = NO_DESCRIPTION;

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
