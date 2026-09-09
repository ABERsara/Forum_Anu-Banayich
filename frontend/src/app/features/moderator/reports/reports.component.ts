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
 * All of the copy lives under `moderator.*` in he.json/en.json — the screen
 * ABF-134 migrated is the screen this one replaces, so the keys it put there
 * carry on into the tabs, and no hardcoded Hebrew comes back (CONTRIBUTING §6).
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
import { TranslocoPipe } from '@jsverse/transloco';

import { ReportWithContent } from '../../../core/models';
import {
  POST_STATUS_LABELS,
  REPORT_DECISION_LABELS,
  REPORT_REASON_LABELS,
  ReportDecision,
} from '../../../core/constants';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { ReportService } from '../../../core/services/report.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ErrorDisplayComponent } from '../../../shared/components/error-display/error-display.component';
import { LoadingSpinnerComponent } from '../../../shared/components/loading-spinner/loading-spinner.component';

const PREVIEW_LENGTH = 200;

/** Matches the note length the backend enforces on ReportDecideRequest. */
const MIN_NOTE_LENGTH = 5;

/**
 * Stands in for a field the report carries nothing in — the description the
 * reporter left empty, or the note on a decision taken before notes were
 * required.
 *
 * A dash is a glyph, not copy: it reads the same in both languages and is
 * Bidi-neutral, so it stays out of the translation files — the same call the
 * dashboard chevron got in ABF-132 and the description dash got in ABF-134.
 */
const EMPTY_VALUE = '–';

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
    TranslocoPipe,
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
  /** Held as a key or a server sentence, never as translated text (ABF-132). */
  readonly actionError = signal<ScreenError>(NO_ERROR);

  readonly reasonLabels = REPORT_REASON_LABELS;
  readonly decisionLabels = REPORT_DECISION_LABELS;
  readonly postStatusLabels = POST_STATUS_LABELS;
  readonly minNoteLength = MIN_NOTE_LENGTH;
  readonly emptyValue = EMPTY_VALUE;
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
    this.actionError.set(NO_ERROR);
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
        error: (err: unknown) => {
          this.actionError.set(screenErrorFrom(err, 'moderator.errors.decide_failed'));
          this.pendingDecision.set(null);
        },
      });
  }

  /**
   * What the confirmation dialog says the decision is about to do — the *key*,
   * piped by the template. The dialog is a shared component and takes finished
   * text, so the caller is where the pipe belongs (CONTRIBUTING §6, ABF-128).
   */
  confirmTitleKey(decision: ReportDecision): string {
    return decision === ReportDecision.VALID
      ? 'moderator.reports.confirm_valid_title'
      : 'moderator.reports.confirm_invalid_title';
  }

  confirmMessageKey(decision: ReportDecision): string {
    return decision === ReportDecision.VALID
      ? 'moderator.reports.confirm_valid_message'
      : 'moderator.reports.confirm_invalid_message';
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
}
