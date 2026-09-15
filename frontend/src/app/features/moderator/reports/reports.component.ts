/**
 * Moderator reports dashboard (SPEC §7.3).
 *
 * Three tabs:
 *   ממתינים  – reports still awaiting a decision in this moderator's cells,
 *              most-reported content first (sorted server-side).
 *   היסטוריה – decisions already made in those cells, newest first, paginated.
 *   הגבלות   – the automatic restrictions §7.2 currently has in force in those
 *              cells (ABF-116). Read-only: this screen shows what the platform
 *              did and until when. Lifting one early is a moderator action
 *              nobody has specified yet, and a button that looked like it
 *              might do so would be worse than none.
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
import { DatePipe, NgTemplateOutlet } from '@angular/common';
import { RouterLink } from '@angular/router';
import { TranslocoPipe } from '@jsverse/transloco';

import { DirectMessageReport, ReportWithContent, RestrictionWithMember } from '../../../core/models';
import {
  POST_STATUS_LABELS,
  REPORT_DECISION_LABELS,
  REPORT_REASON_LABELS,
  RESTRICTION_TYPE_LABELS,
  ReportDecision,
  ReportTargetType,
  RestrictionType,
} from '../../../core/constants';
import { LabelService } from '../../../core/i18n/label.service';
import { NO_ERROR, ScreenError, screenErrorFrom } from '../../../core/i18n/screen-error';
import { ReportService } from '../../../core/services/report.service';
import { utcIso } from '../../../core/utils/utc-date.util';
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

/**
 * The sentence that explains one restriction's `report_count` (SPEC §7.2).
 *
 * Two keys rather than one, because the same number means opposite things on
 * the two kinds of row: a messaging restriction counts reports upheld
 * *against* the member, a reporting one counts her own reports that a
 * moderator dismissed. A single shared sentence told the moderator the
 * opposite of what happened on every row of the second kind.
 *
 * A `Record` keyed by the enum rather than a lookup with a fallback: a third
 * RestrictionType would not compile until it says what its count means.
 */
const RESTRICTION_REASON_KEYS: Record<RestrictionType, string> = {
  [RestrictionType.MESSAGING]: 'moderator.restrictions.reason_value_messaging',
  [RestrictionType.REPORTING]: 'moderator.restrictions.reason_value_reporting',
};

type Tab = 'pending' | 'history' | 'restrictions';

/** The tabs in the order the tablist renders them, for the arrow keys. */
const TAB_ORDER: readonly Tab[] = ['pending', 'history', 'restrictions'];

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
    NgTemplateOutlet,
    RouterLink,
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
  private readonly labels = inject(LabelService);

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

  readonly restrictions = signal<RestrictionWithMember[]>([]);
  readonly isRestrictionsLoading = signal(false);
  readonly restrictionsError = signal(false);
  /**
   * False until restrictions have been fetched for the queue as it now
   * stands. Every decision made sets it back, because a decision is exactly
   * what can have applied one.
   */
  private readonly areRestrictionsFresh = signal(false);

  /** The decision the confirmation dialog is asking about; null when closed. */
  readonly pendingDecision = signal<PendingDecision | null>(null);
  /** Held as a key or a server sentence, never as translated text (ABF-132). */
  readonly actionError = signal<ScreenError>(NO_ERROR);

  /**
   * The DIRECT_MESSAGE report currently expanded, if any (ABF-113) — one at
   * a time, deliberately: fetching several at once would decrypt (and audit
   * a view of) content nobody asked to read yet.
   */
  readonly openReportId = signal<string | null>(null);
  readonly openReportContent = signal<DirectMessageReport | null>(null);
  readonly isContentLoading = signal(false);
  readonly contentError = signal<ScreenError>(NO_ERROR);

  readonly reasonLabels = REPORT_REASON_LABELS;
  readonly decisionLabels = REPORT_DECISION_LABELS;
  readonly postStatusLabels = POST_STATUS_LABELS;
  readonly restrictionTypeLabels = RESTRICTION_TYPE_LABELS;
  readonly minNoteLength = MIN_NOTE_LENGTH;
  readonly emptyValue = EMPTY_VALUE;
  readonly decisions = ReportDecision;
  readonly targetTypes = ReportTargetType;

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
    if (tab === 'restrictions' && !this.areRestrictionsFresh()) {
      this.loadRestrictions();
    }
  }

  /**
   * Arrow keys move between the tabs, as the WAI-ARIA tabs pattern expects.
   *
   * The step is +1 for ArrowRight and -1 for ArrowLeft, wrapping at both
   * ends. Not mirrored for RTL on purpose: the pattern is defined in terms of
   * the *visual* arrows, and in a right-to-left tablist the browser has
   * already laid the tabs out right-to-left — so "the arrow pointing at the
   * next tab on screen" is what the reader presses either way.
   *
   * `tabs` is passed in from the template so the elements to focus and their
   * order come from the same place the tablist renders them; a second list
   * kept here is a second thing to update when a fourth tab arrives.
   */
  moveToTab(event: KeyboardEvent, tabs: readonly HTMLElement[]): void {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (step === 0) return;

    event.preventDefault();
    const current = TAB_ORDER.indexOf(this.activeTab());
    const next = (current + step + TAB_ORDER.length) % TAB_ORDER.length;
    this.showTab(TAB_ORDER[next]);
    tabs[next]?.focus();
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

  /**
   * A display title for the card's heading and its aria-labels alike.
   *
   * A plain string, not a template pipe: `[attr.aria-label]` interpolates
   * this into another translated string (e.g. "moderator.reports.decide_
   * valid_aria"), and a `| transloco` result can't itself be a param to a
   * second `| transloco` in the template — so the DIRECT_MESSAGE fallback is
   * resolved here, once (ABF-113: a DM report has no content_title at all,
   * unlike a FORUM_POST one). Through LabelService, not a bare
   * `TranslocoService.translate()` — that returns the right text once and
   * then goes stale across a language switch (CONTRIBUTING §6, ABF-128).
   */
  reportTitle(report: ReportWithContent): string {
    if (report.target_type === ReportTargetType.FORUM_POST) {
      return report.content_title ?? this.labels.label('moderator.reports.content_gone_title');
    }
    return this.labels.label('moderator.reports.direct_message_title');
  }

  // ---------------------------------------------------------------------------
  // Viewing a DIRECT_MESSAGE report's content (ABF-113)
  // ---------------------------------------------------------------------------

  /** Whether this report is the one currently expanded. */
  isOpen(reportId: string): boolean {
    return this.openReportId() === reportId;
  }

  /**
   * Fetch and expand one DIRECT_MESSAGE report's decrypted content.
   *
   * The server decrypts and audits the read on this exact call (spec
   * §9.1/§9.3) — nothing before this point ever saw the plaintext, including
   * the list this report came from.
   */
  viewContent(report: DirectMessageReport): void {
    this.openReportId.set(report.id);
    this.openReportContent.set(null);
    this.isContentLoading.set(true);
    this.contentError.set(NO_ERROR);

    this.reportService.getReport(report.id).subscribe({
      next: (full) => {
        // A second click may have moved on to another report while this was
        // in flight; that report's own response is what belongs on screen.
        if (!this.isOpen(report.id)) {
          return;
        }
        // The endpoint's response shape follows the id requested, and this
        // method is only ever called with a DIRECT_MESSAGE report's own id
        // (see dmContentViewer in the template) — so this always holds, but
        // it is what lets openReportContent stay typed as DirectMessageReport
        // rather than back to the general union.
        if (full.target_type === ReportTargetType.DIRECT_MESSAGE) {
          this.openReportContent.set(full);
        }
        this.isContentLoading.set(false);
      },
      error: (err: unknown) => {
        if (!this.isOpen(report.id)) {
          return;
        }
        this.contentError.set(screenErrorFrom(err, 'moderator.errors.content_load_failed'));
        this.isContentLoading.set(false);
      },
    });
  }

  closeContent(): void {
    this.openReportId.set(null);
    this.openReportContent.set(null);
    this.contentError.set(NO_ERROR);
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
          // A decision is what applies a restriction, so whatever this tab
          // last showed may already be out of date.
          this.areRestrictionsFresh.set(false);
          // Whatever content was open belongs to a report that just changed
          // decision — closing it means the next look, in History, is a
          // fresh audited fetch rather than this stale one replayed for free.
          this.closeContent();
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

  // ---------------------------------------------------------------------------
  // Restrictions in force (ABF-116)
  // ---------------------------------------------------------------------------

  loadRestrictions(): void {
    this.isRestrictionsLoading.set(true);
    this.restrictionsError.set(false);
    this.reportService.getActiveRestrictions().subscribe({
      next: (result) => {
        this.restrictions.set(result.items);
        this.areRestrictionsFresh.set(true);
        this.isRestrictionsLoading.set(false);
      },
      error: () => {
        this.restrictionsError.set(true);
        this.isRestrictionsLoading.set(false);
      },
    });
  }

  /** A restricted member's name, for the row heading. */
  memberName(restriction: RestrictionWithMember): string {
    return `${restriction.member.first_name} ${restriction.member.last_name}`;
  }

  /**
   * The key that says why this restriction was applied — which is not the
   * same sentence for the two kinds. See RESTRICTION_REASON_KEYS.
   */
  reasonKey(restriction: RestrictionWithMember): string {
    return RESTRICTION_REASON_KEYS[restriction.restriction_type];
  }

  /**
   * When the restriction lifts, as an *instant*.
   *
   * `expires_at` arrives as naive UTC — `2026-07-18T09:30:00`, no offset —
   * and the date pipe reads a string without one as a *local* wall clock, so
   * a moderator in Israel is shown 09:30 for a restriction that in fact runs
   * until 12:30 (see utc-date.util.ts). She is reading this column to know
   * when a member gets her messaging back; three hours out is the difference
   * between answering that question and answering a different one. The chat
   * screen states the same timestamp to the restricted member and converts it
   * the same way, in `restrictionEndsAt()`.
   */
  endsAt(restriction: RestrictionWithMember): string {
    return utcIso(restriction.expires_at);
  }

  /** When it was applied, converted for the same reason as `endsAt()`. */
  appliedAt(restriction: RestrictionWithMember): string {
    return utcIso(restriction.created_at);
  }
}
