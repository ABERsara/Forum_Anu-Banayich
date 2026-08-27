/**
 * Moderator reports dashboard (SPEC §7.3).
 *
 * Two tabs over the same queue:
 *   ממתינים  – reports still awaiting a decision in this moderator's cells,
 *              most-reported content first (sorted server-side).
 *   היסטוריה – decisions already made in those cells, newest first, paginated.
 *
 * Deciding is deliberately a two-step action: either button opens a
 * confirmation that will not submit without a note. That note is the
 * moderator's written justification for deleting a bereaved user's post, and
 * once the content is gone it is the only record of why.
 *
 * Important:
 *   - Moderator can NOT see private messages (no DM content shown)
 *   - Moderator can NOT see reporter's identity – the count only
 */

import {
  ChangeDetectionStrategy,
  Component,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { RouterLink } from '@angular/router';

import { ReportWithContent } from '../../../core/models';
import {
  POST_STATUS_LABELS,
  REPORT_DECISION_LABELS,
  REPORT_REASON_LABELS,
  ReportDecision,
} from '../../../core/constants';
import { ReportService } from '../../../core/services/report.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const PREVIEW_LENGTH = 200;

/** Matches the note length the backend enforces on ReportDecideRequest. */
const MIN_NOTE_LENGTH = 5;

type Tab = 'pending' | 'history';

/** The decision awaiting confirmation, held while the dialog is open. */
interface PendingDecision {
  report: ReportWithContent;
  decision: ReportDecision;
}

@Component({
  selector: 'app-moderator-reports',
  standalone: true,
  imports: [
    DatePipe,
    RouterLink,
    ConfirmDialogComponent,
    ErrorDisplayComponent,
    LoadingSpinnerComponent,
  ],
  templateUrl: './reports.component.html',
  styleUrl: './reports.component.scss',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ModeratorReportsComponent implements OnInit {
  private readonly reportService = inject(ReportService);

  readonly activeTab = signal<Tab>('pending');

  pendingReports = signal<ReportWithContent[]>([]);
  isLoading = signal(false);
  hasError = signal(false);

  readonly history = signal<ReportWithContent[]>([]);
  readonly historyPage = signal(1);
  readonly historyPageCount = signal(1);
  readonly isHistoryLoading = signal(false);
  readonly historyError = signal(false);
  /**
   * False until history has been fetched for the queue as it now stands.
   * Every decision made sets it back, so opening the tab shows the decision
   * that was just taken rather than a list from before it.
   */
  private readonly isHistoryFresh = signal(false);

  /** The decision the confirmation dialog is asking about; null when closed. */
  readonly pendingDecision = signal<PendingDecision | null>(null);
  readonly actionError = signal<string | null>(null);

  readonly reasonLabels = REPORT_REASON_LABELS;
  readonly decisionLabels = REPORT_DECISION_LABELS;
  readonly postStatusLabels = POST_STATUS_LABELS;
  readonly minNoteLength = MIN_NOTE_LENGTH;
  readonly decisions = ReportDecision;

  readonly hasPreviousPage = computed(() => this.historyPage() > 1);
  readonly hasNextPage = computed(() => this.historyPage() < this.historyPageCount());

  ngOnInit(): void {
    this.loadPending();
  }

  // ---------------------------------------------------------------------------
  // Tabs
  // ---------------------------------------------------------------------------

  showTab(tab: Tab): void {
    this.activeTab.set(tab);
    if (tab === 'history' && !this.isHistoryFresh()) {
      this.loadHistory(this.historyPage());
    }
  }

  /**
   * Arrow keys move between the two tabs, as the WAI-ARIA tabs pattern
   * expects. Either arrow goes to the other tab — with only two of them
   * there is nowhere else to land, in either reading direction.
   */
  moveToTab(event: KeyboardEvent, tab: Tab, target: HTMLElement): void {
    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return;
    }
    event.preventDefault();
    this.showTab(tab);
    target.focus();
  }

  // ---------------------------------------------------------------------------
  // The pending queue
  // ---------------------------------------------------------------------------

  private loadPending(): void {
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

  // ---------------------------------------------------------------------------
  // Deciding
  // ---------------------------------------------------------------------------

  decide(report: ReportWithContent, decision: ReportDecision): void {
    this.actionError.set(null);
    this.pendingDecision.set({ report, decision });
  }

  cancelDecision(): void {
    this.pendingDecision.set(null);
  }

  confirmDecision(note: string): void {
    const pending = this.pendingDecision();
    if (!pending) {
      return;
    }

    this.reportService
      .decideReport(pending.report.id, { decision: pending.decision, note })
      .subscribe({
        next: () => {
          // The report has left the pending queue on the server, so it leaves
          // this list too – and the history it just joined is now stale.
          this.pendingReports.update((reports) =>
            reports.filter((report) => report.id !== pending.report.id),
          );
          this.isHistoryFresh.set(false);
          this.pendingDecision.set(null);
        },
        error: (err: HttpErrorResponse) => {
          this.actionError.set(this.messageFrom(err, 'אירעה שגיאה בשמירת ההחלטה. נסי שוב.'));
          this.pendingDecision.set(null);
        },
      });
  }

  /** What the confirmation dialog says the decision is about to do. */
  confirmTitle(decision: ReportDecision): string {
    return decision === ReportDecision.VALID ? 'מחיקת ההודעה' : 'ביטול הדיווח';
  }

  confirmMessage(decision: ReportDecision): string {
    return decision === ReportDecision.VALID
      ? 'הדיווח יסומן כמוצדק, ההודעה תוסר מהפורום, וכותב/ת ההודעה יקבלו על כך הודעת מערכת.'
      : 'הדיווח יסומן כשגוי. הודעה שהוסתרה אוטומטית לאחר שני דיווחים תוצג שוב בפורום.';
  }

  // ---------------------------------------------------------------------------
  // History
  // ---------------------------------------------------------------------------

  loadHistory(page: number): void {
    this.isHistoryLoading.set(true);
    this.historyError.set(false);
    this.reportService.getReportHistory(page).subscribe({
      next: (result) => {
        this.history.set(result.items);
        this.historyPage.set(result.page);
        this.historyPageCount.set(Math.max(1, Math.ceil(result.total / result.page_size)));
        this.isHistoryFresh.set(true);
        this.isHistoryLoading.set(false);
      },
      error: () => {
        this.historyError.set(true);
        this.isHistoryLoading.set(false);
      },
    });
  }

  goToPreviousPage(): void {
    if (this.hasPreviousPage()) {
      this.loadHistory(this.historyPage() - 1);
    }
  }

  goToNextPage(): void {
    if (this.hasNextPage()) {
      this.loadHistory(this.historyPage() + 1);
    }
  }

  private messageFrom(err: HttpErrorResponse, fallback: string): string {
    const detail: unknown = err.error?.detail;
    return typeof detail === 'string' ? detail : fallback;
  }
}
